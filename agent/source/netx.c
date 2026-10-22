// See netx.h.
#define NETX_IMPL
#include <gccore.h>
#include <fcntl.h>
#include <errno.h>
#include "netx.h"

#define LW(s) ((s) >= LWNET_FD_BASE)
#define NONBLOCK_BIT 0x04                    // IOS_O_NONBLOCK, what main.c and update.c pass

volatile int netx_wired;

s32 x_socket(u32 domain, u32 type, u32 protocol) {
    return netx_wired ? lw_socket(domain, type, protocol) : net_socket(domain, type, protocol);
}
s32 x_bind(s32 s, struct sockaddr *name, socklen_t namelen) {
    return LW(s) ? lw_bind(s, name, namelen) : net_bind(s, name, namelen);
}
s32 x_listen(s32 s, u32 backlog) { return LW(s) ? lw_listen(s, backlog) : net_listen(s, backlog); }
s32 x_accept(s32 s, struct sockaddr *addr, socklen_t *addrlen) {
    if (!LW(s)) return net_accept(s, addr, addrlen);
    unsigned int l = addrlen ? *addrlen : 0;
    s32 r = lw_accept(s, addr, addrlen ? &l : NULL);
    if (addrlen) *addrlen = l;
    return r;
}
s32 x_connect(s32 s, struct sockaddr *addr, socklen_t addrlen) {
    return LW(s) ? lw_connect(s, addr, addrlen) : net_connect(s, addr, addrlen);
}
s32 x_send(s32 s, const void *data, s32 size, u32 flags) {
    return LW(s) ? lw_send(s, data, size, flags) : net_send(s, data, size, flags);
}
s32 x_sendto(s32 s, const void *data, s32 len, u32 flags, struct sockaddr *to, socklen_t tolen) {
    return LW(s) ? lw_sendto(s, data, len, flags, to, tolen) : net_sendto(s, data, len, flags, to, tolen);
}
s32 x_recv(s32 s, void *mem, s32 len, u32 flags) {
    return LW(s) ? lw_recv(s, mem, len, flags) : net_recv(s, mem, len, flags);
}
s32 x_close(s32 s) { return LW(s) ? lw_close(s) : net_close(s); }
s32 x_fcntl(s32 s, u32 cmd, u32 flags) {
    if (!LW(s)) return net_fcntl(s, cmd, flags);
    if (cmd == F_GETFL) { s32 r = lw_get_nonblock(s); return r < 0 ? r : r ? NONBLOCK_BIT : 0; }
    if (cmd == F_SETFL) return lw_set_nonblock(s, (flags & NONBLOCK_BIT) != 0);
    return -EINVAL;
}
