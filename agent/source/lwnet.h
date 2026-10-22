// lwnet: the wired network (eth.c's ASIX driver + lwIP with DHCP), and BSD-style socket calls on it with libogc's
// conventions (result >= 0, or -errno), so netx.c can route the launcher's net_* calls here. Plain C types only:
// lwIP's headers and libogc's network.h can't be mixed in one file.
#ifndef LWNET_H
#define LWNET_H

#define LWNET_FD_BASE 1000                   // lwIP socket fds start here (LWIP_SOCKET_OFFSET); IOS ones are small

int lwnet_start(char *msg, int size);        // open the adapter, start lwIP + DHCP (once); 0 = started
unsigned int lwnet_ip(void);                 // our address once DHCP is bound (network order), else 0
int lwnet_link(void);                        // 1 = cable link up
void lwnet_status(char *out, int size);      // one line: link, address, gateway, driver counters
void lwnet_sniff_hook(void (*fn)(const unsigned char *frame, int len));

int lw_socket(int domain, int type, int protocol);
int lw_bind(int s, const void *addr, int addrlen);
int lw_listen(int s, int backlog);
int lw_accept(int s, void *addr, unsigned int *addrlen);
int lw_connect(int s, const void *addr, int addrlen);
int lw_send(int s, const void *buf, int len, int flags);
int lw_recv(int s, void *buf, int len, int flags);
int lw_sendto(int s, const void *buf, int len, int flags, const void *to, int tolen);
int lw_close(int s);
int lw_get_nonblock(int s);
int lw_set_nonblock(int s, int on);

#endif
