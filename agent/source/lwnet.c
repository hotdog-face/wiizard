// The wired network: eth.c's ASIX driver as an lwIP netif, DHCP, a link watcher, and socket calls (see lwnet.h).
#include "lwip/opt.h"
#include "lwip/tcpip.h"
#include "lwip/netif.h"
#include "lwip/dhcp.h"
#include "lwip/etharp.h"
#include "lwip/sockets.h"
#include "lwip/pbuf.h"
#include "netif/ethernet.h"
#include "eth.h"
#include "lwnet.h"

static struct netif nif;
static volatile int started, link_up;
static void (*sniff)(const unsigned char *frame, int len);

void lwnet_sniff_hook(void (*fn)(const unsigned char *frame, int len)) { sniff = fn; }

static err_t low_output(struct netif *n, struct pbuf *p) {
    static u8_t frame[1536] __attribute__((aligned(32)));
    u16_t len = pbuf_copy_partial(p, frame, sizeof frame, 0);
    if (len < 60) { memset(frame + len, 0, 60 - len); len = 60; }   // minimum Ethernet frame
    return eth_send(frame, len) ? ERR_IF : ERR_OK;
}

static void rx(const u8 *frame, int len) {
    if (sniff) sniff(frame, len);
    struct pbuf *p = pbuf_alloc(PBUF_RAW, len, PBUF_POOL);
    if (!p) return;
    pbuf_take(p, frame, len);
    if (nif.input(p, &nif) != ERR_OK) pbuf_free(p);
}

static err_t nif_init(struct netif *n) {
    n->name[0] = 'e';
    n->name[1] = 'n';
    n->output = etharp_output;
    n->linkoutput = low_output;
    n->mtu = 1500;
    n->hwaddr_len = 6;
    eth_mac(n->hwaddr);
    n->flags = NETIF_FLAG_BROADCAST | NETIF_FLAG_ETHARP | NETIF_FLAG_ETHERNET;
    n->hostname = "garage-arcade";
    return ERR_OK;
}

static void link_watch(void *unused) {
    for (;;) {
        int up = eth_link(NULL, NULL);
        if (up != link_up) {
            if (up) eth_apply_link();
            link_up = up;
            LOCK_TCPIP_CORE();
            if (up) netif_set_link_up(&nif); else netif_set_link_down(&nif);
            UNLOCK_TCPIP_CORE();
        }
        sys_msleep(500);
    }
}

static void tcpip_ready(void *sem) { sys_sem_signal((sys_sem_t *)sem); }

int lwnet_start(char *msg, int size) {
    if (started) { snprintf(msg, size, "already running"); return 0; }
    char dmsg[640];
    if (eth_open(dmsg, sizeof dmsg) < 0) { snprintf(msg, size, "adapter: %s", dmsg); return -1; }
    sys_sem_t ready;
    sys_sem_new(&ready, 0);
    tcpip_init(tcpip_ready, &ready);
    sys_arch_sem_wait(&ready, 0);
    sys_sem_free(&ready);
    LOCK_TCPIP_CORE();
    netif_add(&nif, IP4_ADDR_ANY4, IP4_ADDR_ANY4, IP4_ADDR_ANY4, NULL, nif_init, tcpip_input);
    netif_set_default(&nif);
    netif_set_up(&nif);
    dhcp_start(&nif);
    UNLOCK_TCPIP_CORE();
    eth_start_rx(rx);
    sys_thread_new("link", link_watch, NULL, 8 * 1024, 55);
    started = 1;
    snprintf(msg, size, "%s", dmsg);
    return 0;
}

unsigned int lwnet_ip(void) {
    if (!started || !link_up || !dhcp_supplied_address(&nif)) return 0;
    return ip4_addr_get_u32(netif_ip4_addr(&nif));
}

int lwnet_link(void) { return link_up; }

void lwnet_status(char *out, int size) {
    char st[256];
    eth_stats(st, sizeof st);
    if (!started) { snprintf(out, size, "not started; %s", st); return; }
    char a[16], g[16];
    ip4addr_ntoa_r(netif_ip4_addr(&nif), a, sizeof a);
    ip4addr_ntoa_r(netif_ip4_gw(&nif), g, sizeof g);
    snprintf(out, size, "ip=%s gw=%s dhcp=%s %s", a, g, dhcp_supplied_address(&nif) ? "bound" : "waiting", st);
}

static int res(int r) { return r < 0 ? (errno ? -errno : -EIO) : r; }

int lw_socket(int domain, int type, int protocol) { return res(lwip_socket(domain, type, protocol)); }
int lw_bind(int s, const void *addr, int addrlen) { return res(lwip_bind(s, addr, addrlen)); }
int lw_listen(int s, int backlog) { return res(lwip_listen(s, backlog)); }
int lw_accept(int s, void *addr, unsigned int *addrlen) {
    socklen_t l = addrlen ? *addrlen : 0;
    int r = res(lwip_accept(s, addr, addrlen ? &l : NULL));
    if (addrlen) *addrlen = l;
    return r;
}
int lw_connect(int s, const void *addr, int addrlen) { return res(lwip_connect(s, addr, addrlen)); }
int lw_send(int s, const void *buf, int len, int flags) { return res(lwip_send(s, buf, len, flags)); }
int lw_recv(int s, void *buf, int len, int flags) { return res(lwip_recv(s, buf, len, flags)); }
int lw_sendto(int s, const void *buf, int len, int flags, const void *to, int tolen) {
    return res(lwip_sendto(s, buf, len, flags, to, tolen));
}
int lw_close(int s) { return res(lwip_close(s)); }
int lw_get_nonblock(int s) { int f = lwip_fcntl(s, F_GETFL, 0); return f < 0 ? res(f) : (f & O_NONBLOCK) != 0; }
int lw_set_nonblock(int s, int on) {
    int f = lwip_fcntl(s, F_GETFL, 0);
    if (f < 0) return res(f);
    return res(lwip_fcntl(s, F_SETFL, on ? (f | O_NONBLOCK) : (f & ~O_NONBLOCK)));
}
