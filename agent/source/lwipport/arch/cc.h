// lwIP compiler/platform glue for the Wii (PowerPC, big-endian, newlib).
#ifndef LWIP_ARCH_CC_H
#define LWIP_ARCH_CC_H
#ifndef FD_SETSIZE
#define FD_SETSIZE 1088                      // newlib's fd_set must cover lwIP's fds (1000 + MEMP_NUM_NETCONN)
#endif
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <sys/time.h>

#ifndef BYTE_ORDER
#define BYTE_ORDER BIG_ENDIAN
#endif

void lwip_port_log(const char *fmt, ...);
void lwip_port_assert(const char *msg, const char *file, int line);
#define LWIP_PLATFORM_DIAG(x) do { lwip_port_log x; } while (0)
#define LWIP_PLATFORM_ASSERT(x) lwip_port_assert(x, __FILE__, __LINE__)
#define LWIP_RAND() ((u32_t)rand())

#endif
