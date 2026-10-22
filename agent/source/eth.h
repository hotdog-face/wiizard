// eth: our own driver for ASIX AX88772/AX88772A/AX88772B USB LAN adapters (VID 0b95), over IOS's /dev/usb/ven.
// IOS's network stack only runs the adapters it knows (cab1's TRENDnet TU2-ET100, an AX88772B 0b95:772b, never even
// powers its PHY up there), so the launcher drives the chip itself and feeds raw Ethernet frames to its own stack.
#ifndef ETH_H
#define ETH_H
#include <gctypes.h>

typedef void (*eth_rx_fn)(const u8 *frame, int len);

int eth_present(u16 *pid);                  // an ASIX adapter is plugged in (USB device list)
int eth_open(char *msg, int size);          // open + reset + PHY up + autonegotiation; 0 = ok, msg says what happened
int eth_is_open(void);
void eth_mac(u8 mac[6]);
int eth_link(int *mbps, int *full);         // 1 = link up (PHY), with the negotiated speed/duplex
int eth_apply_link(void);                   // set the MAC's medium mode to what the PHY negotiated; 1 = link up
int eth_send(const void *frame, int len);   // one Ethernet frame (no FCS); 0 = sent
void eth_start_rx(eth_rx_fn fn);            // receive thread: fn(frame, len) per frame
int eth_close(void);                        // before an IOS reload: stop all transfers; ms waited for rx (-1: timeout)
void eth_stats(char *out, int size);        // counters and register dump, one line
int eth_mdio_read(int reg);
int eth_vendor(int in, int cmd, int value, int index, int len, u8 *data);   // raw vendor request (ETH CMD)

#endif
