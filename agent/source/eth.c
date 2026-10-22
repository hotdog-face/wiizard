// ASIX AX88772(A/B) USB LAN adapter driver over IOS's /dev/usb/ven (see eth.h). The reset sequence follows Linux's
// drivers/net/usb/asix_devices.c (ax88772_hw_reset): the chip comes up with its internal PHY powered down (IPPD),
// which is why a driver that doesn't know it (IOS's) never gets a link light.
#include <gccore.h>
#include <ogc/usb.h>
#include <ogc/lwp_watchdog.h>
#include <malloc.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include "eth.h"

#define ASIX_VID 0x0b95

#define AX_CMD_SET_SW_MII        0x06
#define AX_CMD_READ_MII_REG      0x07
#define AX_CMD_WRITE_MII_REG     0x08
#define AX_CMD_SET_HW_MII        0x0a
#define AX_CMD_WRITE_RX_CTL      0x10
#define AX_CMD_WRITE_IPG0        0x12
#define AX_CMD_READ_NODE_ID      0x13
#define AX_CMD_WRITE_NODE_ID     0x14
#define AX_CMD_READ_PHY_ID       0x19
#define AX_CMD_READ_MEDIUM       0x1a
#define AX_CMD_WRITE_MEDIUM      0x1b
#define AX_CMD_WRITE_GPIOS       0x1f
#define AX_CMD_SW_RESET          0x20
#define AX_CMD_SW_PHY_SELECT     0x22

#define AX_SWRESET_CLEAR 0x00
#define AX_SWRESET_PRL   0x08
#define AX_SWRESET_PRTE  0x04
#define AX_SWRESET_IPRL  0x20
#define AX_SWRESET_IPPD  0x40                // internal PHY power down

#define AX_GPIO_GPO2EN 0x10
#define AX_GPIO_GPO_2  0x20
#define AX_GPIO_RSE    0x80

#define AX_MEDIUM_FD  0x0002
#define AX_MEDIUM_AC  0x0004
#define AX_MEDIUM_RFC 0x0010
#define AX_MEDIUM_TFC 0x0020
#define AX_MEDIUM_RE  0x0100
#define AX_MEDIUM_PS  0x0200                 // 100 Mbit/s
#define AX_RX_CTL_AB  0x0008                 // accept broadcast
#define AX_RX_CTL_AM  0x0010                 // accept multicast (in the hash; we leave the hash empty)
#define AX_RX_CTL_SO  0x0080                 // start operation
#define AX88772_IPG0 0x15
#define AX88772_IPG1 0x0c
#define AX88772_IPG2 0x12

#define MII_BMCR 0
#define MII_BMSR 1
#define MII_PHYSID1 2
#define MII_ADVERTISE 4
#define MII_LPA 5
#define BMCR_RESET 0x8000
#define BMCR_ANENABLE 0x1000
#define BMCR_ANRESTART 0x0200
#define BMSR_LSTATUS 0x0004
#define BMSR_ANEGCOMPLETE 0x0020
#define ADVERTISE_ALL_CSMA 0x01e1            // 10/100 half/full + CSMA

#define RX_BUF 2048
#define RX_STREAM (RX_BUF * 2 + 1600)

static s32 fd = -1;                          // IOS ven: the handle is the device id, which may be negative
static int opened;
static u8 ep_in, ep_out, phy_id;
static u16 maxpkt_out = 64;
static u8 mac[6];
static u8 *cbuf, *txbuf, *rxbuf;             // 32-byte aligned for IOS
static mutex_t tx_lock = LWP_MUTEX_NULL;
static mutex_t ctrl_lock = LWP_MUTEX_NULL;     // control transfers (cbuf, the MII mode): link watcher vs. ETH STAT
static volatile u32 rx_frames, rx_bytes, rx_bad, tx_frames, tx_err, rx_err;
static volatile s32 last_rx_err;
static lwp_t rx_thread = LWP_THREAD_NULL;
static volatile int closing;                  // eth_close: no new transfers on fd (ax_* refuse; eth_open clears it)
static volatile int rx_done;                  // rx_loop has returned
static eth_rx_fn rx_fn;
static u16 dev_pid;
static char steps[512];                      // every reset step's result, for the log (eth_open's msg)
static int steps_n;
static void step(const char *name, s32 r) {
    if (steps_n < (int)sizeof steps - 24) steps_n += snprintf(steps + steps_n, sizeof steps - steps_n, " %s=%d", name, (int)r);
}

static void msleep(int ms) { usleep(ms * 1000); }

static s32 ax_write(u8 cmd, u16 value, u16 index, u16 size, const void *data) {
    LWP_MutexLock(ctrl_lock);
    if (closing) { LWP_MutexUnlock(ctrl_lock); return -1; }
    if (size) memcpy(cbuf, data, size);
    DCFlushRange(cbuf, 64);                  // IOS reads memory, not our cache (control transfers aren't flushed for us)
    s32 r = USB_WriteCtrlMsg(fd, USB_CTRLTYPE_DIR_HOST2DEVICE | USB_CTRLTYPE_TYPE_VENDOR | USB_CTRLTYPE_REC_DEVICE,
                             cmd, value, index, size, size ? cbuf : NULL);
    LWP_MutexUnlock(ctrl_lock);
    return r;
}
static s32 ax_read(u8 cmd, u16 value, u16 index, u16 size, void *data) {
    LWP_MutexLock(ctrl_lock);
    if (closing) { LWP_MutexUnlock(ctrl_lock); return -1; }
    DCFlushRange(cbuf, 64);                  // nothing dirty may land on top of what the adapter sends
    s32 r = USB_ReadCtrlMsg(fd, USB_CTRLTYPE_DIR_DEVICE2HOST | USB_CTRLTYPE_TYPE_VENDOR | USB_CTRLTYPE_REC_DEVICE,
                            cmd, value, index, size, cbuf);
    DCInvalidateRange(cbuf, 64);             // ...and read what it sent, not our cache (0.10.3 read stale bytes)
    if (r >= 0) memcpy(data, cbuf, size);
    LWP_MutexUnlock(ctrl_lock);
    return r;
}

int eth_vendor(int in, int cmd, int value, int index, int len, u8 *data) {
    if (!opened || len < 0 || len > 32) return -1;
    return in ? ax_read(cmd, value, index, len, data) : ax_write(cmd, value, index, len, data);
}

int eth_mdio_read(int reg) {
    u8 b[2];
    if (!opened) return -1;
    LWP_MutexLock(ctrl_lock);                // (recursive: ax_* lock it again)
    ax_write(AX_CMD_SET_SW_MII, 0, 0, 0, NULL);
    s32 r = ax_read(AX_CMD_READ_MII_REG, phy_id, reg, 2, b);
    ax_write(AX_CMD_SET_HW_MII, 0, 0, 0, NULL);
    LWP_MutexUnlock(ctrl_lock);
    return r < 0 ? -1 : b[0] | b[1] << 8;
}
static void mdio_write(int reg, u16 val) {
    u8 b[2] = { val & 0xff, val >> 8 };
    LWP_MutexLock(ctrl_lock);
    ax_write(AX_CMD_SET_SW_MII, 0, 0, 0, NULL);
    ax_write(AX_CMD_WRITE_MII_REG, phy_id, reg, 2, b);
    ax_write(AX_CMD_SET_HW_MII, 0, 0, 0, NULL);
    LWP_MutexUnlock(ctrl_lock);
}

int eth_present(u16 *pid) {
    static usb_device_entry devs[8] ATTRIBUTE_ALIGN(32);
    u8 cnt = 0;
    if (USB_GetDeviceList(devs, 8, 0, &cnt) < 0) return 0;
    for (int i = 0; i < cnt; i++)
        if (devs[i].vid == ASIX_VID) { if (pid) *pid = devs[i].pid; return 1; }
    return 0;
}

int eth_is_open(void) { return opened; }
void eth_mac(u8 out[6]) { memcpy(out, mac, 6); }

int eth_open(char *msg, int size) {
    if (opened) { snprintf(msg, size, "already open"); return 0; }
    closing = 0;
    if (!cbuf) {
        // In MEM2 (an IPC heap): control replies written to a MEM1 buffer never showed up (0.10.4 read the bytes it
        // had written itself, every time).
        s32 heap = iosCreateHeap(64 + 1664 + RX_BUF + 256);
        if (heap >= 0) {
            cbuf = iosAlloc(heap, 64);
            txbuf = iosAlloc(heap, 1664);
            rxbuf = iosAlloc(heap, RX_BUF);
        }
        if (!cbuf || !txbuf || !rxbuf) { snprintf(msg, size, "no IPC heap for USB buffers (%d)", (int)heap); return -1; }
        LWP_MutexInit(&tx_lock, false);
        LWP_MutexInit(&ctrl_lock, true);
    }
    static usb_device_entry devs[8] ATTRIBUTE_ALIGN(32);
    u8 cnt = 0;
    s32 r = USB_GetDeviceList(devs, 8, 0, &cnt);
    if (r < 0) { snprintf(msg, size, "USB_GetDeviceList %d", (int)r); return -1; }
    int i;
    for (i = 0; i < cnt && devs[i].vid != ASIX_VID; i++) ;
    if (i == cnt) { snprintf(msg, size, "no ASIX adapter on USB (%d devices)", cnt); return -1; }
    dev_pid = devs[i].pid;
    r = USB_OpenDevice(devs[i].device_id, devs[i].vid, devs[i].pid, &fd);
    if (r < 0) {
        snprintf(msg, size, "USB_OpenDevice(id %d, %04x:%04x) = %d", (int)devs[i].device_id, devs[i].vid, devs[i].pid, (int)r);
        fd = -1;
        return -1;
    }

    usb_devdesc dd;
    memset(&dd, 0, sizeof dd);
    r = USB_GetDescriptors(fd, &dd);
    if (r < 0) { snprintf(msg, size, "USB_GetDescriptors %d", (int)r); USB_CloseDevice(&fd); fd = -1; return -1; }
    ep_in = ep_out = 0;
    if (dd.configurations && dd.configurations->interfaces) {
        usb_interfacedesc *ifc = dd.configurations->interfaces;
        for (int e = 0; e < ifc->bNumEndpoints; e++) {
            usb_endpointdesc *ep = &ifc->endpoints[e];
            if ((ep->bmAttributes & 3) != 2) continue;          // bulk only
            if (ep->bEndpointAddress & 0x80) ep_in = ep->bEndpointAddress;
            else { ep_out = ep->bEndpointAddress; maxpkt_out = ep->wMaxPacketSize; }
        }
    }
    USB_FreeDescriptors(&dd);
    if (!ep_in || !ep_out) { ep_in = 0x82; ep_out = 0x03; }   // the AX88772 layout

    u8 b[8] = { 0 };
    opened = 1;
    steps_n = 0;
    steps[0] = 0;
    step("open", r);
    step("handle", fd);
    step("cfg", USB_SetConfiguration(fd, 1));
    r = ax_write(AX_CMD_WRITE_GPIOS, AX_GPIO_RSE | AX_GPIO_GPO_2 | AX_GPIO_GPO2EN, 0, 0, NULL);
    step("gpio", r);
    msleep(5);
    if (r < 0) {
        snprintf(msg, size, "vendor requests refused (handle %d):%s", (int)fd, steps);
        opened = 0;
        USB_CloseDevice(&fd); fd = -1; return -1;
    }
    r = ax_read(AX_CMD_READ_PHY_ID, 0, 0, 2, b);
    step("phyid", r);
    step("phyid0", b[0]);
    step("phyid1", b[1]);
    // Every AX88772/A/B has its PHY inside at address 0x10. cab1's AX88772B answers 0x03 here, and taking that for
    // an external PHY powered the internal one down (the "ext" reset): no link lights.
    phy_id = 0x10;
    int embd = 1;
    step("physel", ax_write(AX_CMD_SW_PHY_SELECT, embd, 0, 0, NULL));
    if (embd) {
        step("ippd", ax_write(AX_CMD_SW_RESET, AX_SWRESET_IPPD, 0, 0, NULL));
        msleep(10);
        step("clear", ax_write(AX_CMD_SW_RESET, AX_SWRESET_CLEAR, 0, 0, NULL));   // PHY powered up
        msleep(60);
        step("iprl", ax_write(AX_CMD_SW_RESET, AX_SWRESET_IPRL | AX_SWRESET_PRL, 0, 0, NULL));
    } else {
        step("ext", ax_write(AX_CMD_SW_RESET, AX_SWRESET_IPPD | AX_SWRESET_PRL, 0, 0, NULL));
    }
    msleep(150);
    step("rxoff", ax_write(AX_CMD_WRITE_RX_CTL, 0, 0, 0, NULL));
    step("ipg", ax_write(AX_CMD_WRITE_IPG0, AX88772_IPG0 | AX88772_IPG1 << 8, AX88772_IPG2, 0, NULL));
    step("mac", ax_read(AX_CMD_READ_NODE_ID, 0, 0, 6, mac));
    step("setmac", ax_write(AX_CMD_WRITE_NODE_ID, 0, 0, 6, mac));
    step("bmcr0", eth_mdio_read(MII_BMCR));
    mdio_write(MII_BMCR, BMCR_RESET);
    for (int t = 0; t < 50 && (eth_mdio_read(MII_BMCR) & BMCR_RESET); t++) msleep(10);
    mdio_write(MII_ADVERTISE, ADVERTISE_ALL_CSMA);
    mdio_write(MII_BMCR, BMCR_ANENABLE | BMCR_ANRESTART);
    step("adv", eth_mdio_read(MII_ADVERTISE));
    step("bmcr", eth_mdio_read(MII_BMCR));
    step("medium", ax_write(AX_CMD_WRITE_MEDIUM, AX_MEDIUM_FD | AX_MEDIUM_AC | AX_MEDIUM_RFC | AX_MEDIUM_TFC | AX_MEDIUM_RE |
                            AX_MEDIUM_PS, 0, 0, NULL));
    step("rxon", ax_write(AX_CMD_WRITE_RX_CTL, AX_RX_CTL_SO | AX_RX_CTL_AB, 0, 0, NULL));
    snprintf(msg, size, "pid %04x phy 0x%02x%s mac %02x:%02x:%02x:%02x:%02x:%02x ep in 0x%02x out 0x%02x/%u physid %04x;%s",
             dev_pid, phy_id, embd ? " (internal)" : "", mac[0], mac[1], mac[2], mac[3], mac[4], mac[5], ep_in, ep_out,
             maxpkt_out, eth_mdio_read(MII_PHYSID1) & 0xffff, steps);
    return 0;
}

int eth_link(int *mbps, int *full) {
    int bmsr = eth_mdio_read(MII_BMSR);
    bmsr = eth_mdio_read(MII_BMSR);          // latched-low link bit: the second read is the current state
    if (bmsr < 0 || !(bmsr & BMSR_LSTATUS)) return 0;
    int lpa = eth_mdio_read(MII_LPA) & eth_mdio_read(MII_ADVERTISE);
    if (mbps) *mbps = lpa & 0x0180 ? 100 : 10;
    if (full) *full = lpa & 0x0100 ? 1 : lpa & 0x0080 ? 0 : (lpa & 0x0040) ? 1 : 0;
    return 1;
}

int eth_apply_link(void) {
    int mbps = 100, full = 1;
    if (!eth_link(&mbps, &full)) return 0;
    u16 mode = AX_MEDIUM_AC | AX_MEDIUM_RE | (full ? AX_MEDIUM_FD | AX_MEDIUM_RFC | AX_MEDIUM_TFC : 0) |
               (mbps == 100 ? AX_MEDIUM_PS : 0);
    ax_write(AX_CMD_WRITE_MEDIUM, mode, 0, 0, NULL);
    return 1;
}

int eth_send(const void *frame, int len) {
    if (!opened || len <= 0 || len > 1514) return -1;
    LWP_MutexLock(tx_lock);
    if (!opened) { LWP_MutexUnlock(tx_lock); return -1; }   // closed while we waited for the lock
    u32 hdr = (u32)len | ((u32)(len ^ 0xffff) << 16);
    txbuf[0] = hdr; txbuf[1] = hdr >> 8; txbuf[2] = hdr >> 16; txbuf[3] = hdr >> 24;   // little-endian header
    memcpy(txbuf + 4, frame, len);
    int total = len + 4;
    if (total % maxpkt_out == 0) {           // a transfer that ends on a packet boundary needs this pad
        txbuf[total] = 0; txbuf[total + 1] = 0; txbuf[total + 2] = 0xff; txbuf[total + 3] = 0xff;
        total += 4;
    }
    DCFlushRange(txbuf, (total + 31) & ~31);
    s32 r = USB_WriteBlkMsg(fd, ep_out, total, txbuf);
    if (r < 0) tx_err++; else tx_frames++;
    LWP_MutexUnlock(tx_lock);
    return r < 0 ? -1 : 0;
}

// Bulk-in transfers carry frames back to back, each after a 4-byte header (11-bit length, then its complement),
// padded to an even length; a frame may continue in the next transfer, so this works on a byte stream.
static void *rx_loop(void *unused) {
    static u8 stream[RX_STREAM] ATTRIBUTE_ALIGN(32);
    int have = 0;
    while (opened) {
        DCInvalidateRange(rxbuf, RX_BUF);
        s32 n = USB_ReadBlkMsg(fd, ep_in, RX_BUF, rxbuf);
        DCInvalidateRange(rxbuf, RX_BUF);
        if (!opened) break;                  // eth_close: no further transfer (and no error sleep)
        if (n < 0) { rx_err++; last_rx_err = n; msleep(n == -7022 ? 1000 : 20); continue; }
        if (n == 0) continue;
        if (have + n > RX_STREAM) have = 0;  // lost sync
        memcpy(stream + have, rxbuf, n);
        have += n;
        int off = 0;
        while (have - off >= 4) {
            u32 h = stream[off] | stream[off + 1] << 8 | stream[off + 2] << 16 | (u32)stream[off + 3] << 24;
            int len = h & 0x7ff;
            if (len != (int)((~h >> 16) & 0x7ff) || len < 14) { rx_bad++; off = have; break; }   // resync on next transfer
            if (have - off - 4 < len) break; // rest in the next transfer
            rx_frames++;
            rx_bytes += len;
            if (rx_fn) rx_fn(stream + off + 4, len);
            off += 4 + ((len + 1) & ~1);
        }
        if (off) { memmove(stream, stream + off, have - off); have -= off; }
    }
    rx_done = 1;
    return NULL;
}

// Before the launcher reloads IOS (exec, System Menu, restart, power off): no USB transfer may be in flight or start
// during the reload (a transfer issued into ES's IOS relaunch can wedge the console; suspected in the mdgaxe2/GKQE01
// hangs, 2026-10-22). Both locks are taken so no control (link watcher MDIO) or bulk-out (eth_send) transfer is
// running; closing the handle completes the pending bulk-in read, and rx_loop then exits. Bounded: never blocks exec.
// Returns the ms waited for rx_loop (-1: it didn't exit in time).
int eth_close(void) {
    if (!opened) return 0;
    LWP_MutexLock(ctrl_lock);
    LWP_MutexLock(tx_lock);
    closing = 1;
    opened = 0;
    LWP_MutexUnlock(tx_lock);
    LWP_MutexUnlock(ctrl_lock);
    USB_CloseDevice(&fd);
    int ms = 0;
    while (rx_thread != LWP_THREAD_NULL && !rx_done && ms < 200) { usleep(10 * 1000); ms += 10; }
    return rx_thread == LWP_THREAD_NULL || rx_done ? ms : -1;
}

void eth_start_rx(eth_rx_fn fn) {
    rx_fn = fn;
    if (opened && rx_thread == LWP_THREAD_NULL) LWP_CreateThread(&rx_thread, rx_loop, NULL, NULL, 16 * 1024, 60);
}

void eth_stats(char *out, int size) {
    if (!opened) { snprintf(out, size, "closed"); return; }
    u8 m[2] = { 0, 0 };
    ax_read(AX_CMD_READ_MEDIUM, 0, 0, 2, m);
    int bmsr = eth_mdio_read(MII_BMSR);
    bmsr = eth_mdio_read(MII_BMSR);
    int mbps = 0, full = 0, up = eth_link(&mbps, &full);
    snprintf(out, size, "link=%s%s bmcr=%04x bmsr=%04x lpa=%04x medium=%04x rx=%u/%uB bad=%u rxerr=%u(%d) tx=%u txerr=%u",
             up ? (mbps == 100 ? "100" : "10") : "down", up ? (full ? "FD" : "HD") : "", eth_mdio_read(MII_BMCR) & 0xffff,
             bmsr & 0xffff, eth_mdio_read(MII_LPA) & 0xffff, m[0] | m[1] << 8, (unsigned)rx_frames, (unsigned)rx_bytes,
             (unsigned)rx_bad, (unsigned)rx_err, (int)last_rx_err, (unsigned)tx_frames, (unsigned)tx_err);
}
