// netx: the launcher's net_* socket calls, routed to the active network: IOS (Wi-Fi) or lwnet (wired, our own
// driver). New sockets go to the stack in use (netx_wired); calls on an existing socket go by its fd (lwIP's start
// at LWNET_FD_BASE). Include after <network.h>: the macros below point main.c's and update.c's calls here.
#ifndef NETX_H
#define NETX_H
#include <network.h>
#include "lwnet.h"

extern volatile int netx_wired;              // 1 = the wired network is the one in use

s32 x_socket(u32 domain, u32 type, u32 protocol);
s32 x_bind(s32 s, struct sockaddr *name, socklen_t namelen);
s32 x_listen(s32 s, u32 backlog);
s32 x_accept(s32 s, struct sockaddr *addr, socklen_t *addrlen);
s32 x_connect(s32 s, struct sockaddr *addr, socklen_t addrlen);
s32 x_send(s32 s, const void *data, s32 size, u32 flags);
s32 x_sendto(s32 s, const void *data, s32 len, u32 flags, struct sockaddr *to, socklen_t tolen);
s32 x_recv(s32 s, void *mem, s32 len, u32 flags);
s32 x_close(s32 s);
s32 x_fcntl(s32 s, u32 cmd, u32 flags);

#ifndef NETX_IMPL
#define net_socket x_socket
#define net_bind x_bind
#define net_listen x_listen
#define net_accept x_accept
#define net_connect x_connect
#define net_send x_send
#define net_sendto x_sendto
#define net_recv x_recv
#define net_close x_close
#define net_fcntl x_fcntl
#endif
#endif
