// lwIP OS layer types for libogc LWP threads (implemented in sys_arch.c). Opaque pointers: NULL = invalid.
#ifndef LWIP_ARCH_SYS_ARCH_H
#define LWIP_ARCH_SYS_ARCH_H

typedef struct lw_sem *sys_sem_t;
typedef struct lw_mutex *sys_mutex_t;
typedef struct lw_mbox *sys_mbox_t;
typedef unsigned int sys_thread_t;
typedef unsigned int sys_prot_t;

#define sys_sem_valid(s) ((s) != NULL && *(s) != NULL)
#define sys_sem_set_invalid(s) do { if (s) *(s) = NULL; } while (0)
#define sys_mutex_valid(m) ((m) != NULL && *(m) != NULL)
#define sys_mutex_set_invalid(m) do { if (m) *(m) = NULL; } while (0)
#define sys_mbox_valid(m) ((m) != NULL && *(m) != NULL)
#define sys_mbox_set_invalid(m) do { if (m) *(m) = NULL; } while (0)

#define SYS_MBOX_NULL NULL
#define SYS_SEM_NULL NULL

#endif
