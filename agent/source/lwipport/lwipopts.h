// lwIP settings for the launcher's wired network (our ASIX driver, eth.c): IPv4, DHCP, TCP/UDP sockets, threads on
// libogc LWP (sys_arch.c). Socket fds start at 1000 so netx.c can tell them from IOS (Wi-Fi) sockets.
#ifndef LWIPOPTS_H
#define LWIPOPTS_H

#define NO_SYS                          0
#define SYS_LIGHTWEIGHT_PROT            1
#define LWIP_TCPIP_CORE_LOCKING         1
#define LWIP_SOCKET                     1
#define LWIP_NETCONN                    1
#define LWIP_COMPAT_SOCKETS             0
#define LWIP_POSIX_SOCKETS_IO_NAMES     0
#define LWIP_SOCKET_OFFSET              1000
#define LWIP_SOCKET_POLL                0
#define LWIP_SO_RCVTIMEO                1
#define LWIP_SO_SNDTIMEO                1
#define SO_REUSE                        1
#define LWIP_ERRNO_STDINCLUDE           1
#define LWIP_TIMEVAL_PRIVATE            0

#define LWIP_IPV4                       1
#define LWIP_IPV6                       0
#define LWIP_ARP                        1
#define LWIP_ETHERNET                   1
#define LWIP_ICMP                       1
#define LWIP_RAW                        0
#define LWIP_IGMP                       0
#define LWIP_DHCP                       1
#define LWIP_DHCP_DOES_ACD_CHECK        0
#define LWIP_ACD                        0
#define LWIP_AUTOIP                     0
#define LWIP_DNS                        0
#define LWIP_UDP                        1
#define LWIP_TCP                        1
#define LWIP_NETIF_HOSTNAME             1
#define LWIP_NETIF_STATUS_CALLBACK      1
#define LWIP_NETIF_LINK_CALLBACK        1
#define LWIP_STATS                      0
#define LWIP_CHKSUM_ALGORITHM           3

#define MEM_ALIGNMENT                   4
#define MEM_SIZE                        (512 * 1024)
#define MEMP_NUM_PBUF                   64
#define PBUF_POOL_SIZE                  128
#define MEMP_NUM_TCP_PCB                10
#define MEMP_NUM_TCP_PCB_LISTEN         4
#define MEMP_NUM_UDP_PCB                6
#define MEMP_NUM_NETCONN                16
#define MEMP_NUM_TCP_SEG                256
#define MEMP_NUM_NETBUF                 32
#define MEMP_NUM_TCPIP_MSG_INPKT        64
#define TCP_MSS                         1460
#define TCP_WND                         (16 * TCP_MSS)
#define TCP_SND_BUF                     (16 * TCP_MSS)
#define TCP_SND_QUEUELEN                (4 * TCP_SND_BUF / TCP_MSS)
#define LWIP_WND_SCALE                  0

#define TCPIP_THREAD_NAME               "tcpip"
#define TCPIP_THREAD_STACKSIZE          (32 * 1024)
#define TCPIP_THREAD_PRIO               64
#define TCPIP_MBOX_SIZE                 128
#define DEFAULT_THREAD_STACKSIZE        (16 * 1024)
#define DEFAULT_THREAD_PRIO             50
#define DEFAULT_RAW_RECVMBOX_SIZE       16
#define DEFAULT_UDP_RECVMBOX_SIZE       16
#define DEFAULT_TCP_RECVMBOX_SIZE       64
#define DEFAULT_ACCEPTMBOX_SIZE         8

#endif
