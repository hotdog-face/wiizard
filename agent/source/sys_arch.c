// lwIP's OS layer on libogc LWP threads: semaphores and mailboxes are a mutex + condition variable each (libogc's
// own semaphores have no timed wait), lightweight protection disables interrupts (one CPU: no thread switch).
#include <gccore.h>
#include <ogc/lwp_watchdog.h>
#include <ogc/machine/processor.h>
#include <ogc/cond.h>
#include <stdarg.h>
#include <time.h>
#include "lwip/sys.h"
#include "lwip/opt.h"

struct lw_sem { mutex_t m; cond_t c; u32 count; };
struct lw_mutex { mutex_t m; };
struct lw_mbox { mutex_t m; cond_t not_empty, not_full; int size, head, count; void **msgs; };

void lwip_port_log(const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    vprintf(fmt, ap);
    va_end(ap);
}
void lwip_port_assert(const char *msg, const char *file, int line) {
    printf("lwip assert %s at %s:%d\n", msg, file, line);
}

void sys_init(void) {}

u32_t sys_now(void) { return (u32_t)ticks_to_millisecs(gettime()); }

sys_prot_t sys_arch_protect(void) {
    u32 level;
    _CPU_ISR_Disable(level);
    return level;
}
void sys_arch_unprotect(sys_prot_t level) { _CPU_ISR_Restore(level); }

// Waits on c (m held) for up to ms (0 = forever); returns 1 on timeout.
static int timed_wait(cond_t c, mutex_t m, u32_t ms) {
    if (!ms) { LWP_CondWait(c, m); return 0; }
    struct timespec ts = { .tv_sec = ms / 1000, .tv_nsec = (ms % 1000) * 1000000 };
    return LWP_CondTimedWait(c, m, &ts) != 0;   // (callers re-check their condition)
}

err_t sys_sem_new(sys_sem_t *sem, u8_t count) {
    struct lw_sem *s = calloc(1, sizeof *s);
    if (!s) return ERR_MEM;
    LWP_MutexInit(&s->m, false);
    LWP_CondInit(&s->c);
    s->count = count;
    *sem = s;
    return ERR_OK;
}
void sys_sem_free(sys_sem_t *sem) {
    struct lw_sem *s = *sem;
    if (!s) return;
    LWP_CondDestroy(s->c);
    LWP_MutexDestroy(s->m);
    free(s);
    *sem = NULL;
}
void sys_sem_signal(sys_sem_t *sem) {
    struct lw_sem *s = *sem;
    LWP_MutexLock(s->m);
    s->count++;
    LWP_CondSignal(s->c);
    LWP_MutexUnlock(s->m);
}
u32_t sys_arch_sem_wait(sys_sem_t *sem, u32_t timeout) {
    struct lw_sem *s = *sem;
    u32_t start = sys_now();
    LWP_MutexLock(s->m);
    while (!s->count) {
        u32_t waited = sys_now() - start;
        if (timeout && waited >= timeout) { LWP_MutexUnlock(s->m); return SYS_ARCH_TIMEOUT; }
        if (timed_wait(s->c, s->m, timeout ? timeout - waited : 0) && !s->count) {
            LWP_MutexUnlock(s->m);
            return SYS_ARCH_TIMEOUT;
        }
    }
    s->count--;
    LWP_MutexUnlock(s->m);
    return sys_now() - start;
}

err_t sys_mutex_new(sys_mutex_t *mutex) {
    struct lw_mutex *x = calloc(1, sizeof *x);
    if (!x) return ERR_MEM;
    LWP_MutexInit(&x->m, false);
    *mutex = x;
    return ERR_OK;
}
void sys_mutex_free(sys_mutex_t *mutex) {
    if (!*mutex) return;
    LWP_MutexDestroy((*mutex)->m);
    free(*mutex);
    *mutex = NULL;
}
void sys_mutex_lock(sys_mutex_t *mutex) { LWP_MutexLock((*mutex)->m); }
void sys_mutex_unlock(sys_mutex_t *mutex) { LWP_MutexUnlock((*mutex)->m); }

err_t sys_mbox_new(sys_mbox_t *mbox, int size) {
    struct lw_mbox *b = calloc(1, sizeof *b);
    if (!b) return ERR_MEM;
    b->size = size > 0 ? size : 32;
    b->msgs = calloc(b->size, sizeof(void *));
    if (!b->msgs) { free(b); return ERR_MEM; }
    LWP_MutexInit(&b->m, false);
    LWP_CondInit(&b->not_empty);
    LWP_CondInit(&b->not_full);
    *mbox = b;
    return ERR_OK;
}
void sys_mbox_free(sys_mbox_t *mbox) {
    struct lw_mbox *b = *mbox;
    if (!b) return;
    LWP_CondDestroy(b->not_empty);
    LWP_CondDestroy(b->not_full);
    LWP_MutexDestroy(b->m);
    free(b->msgs);
    free(b);
    *mbox = NULL;
}
static void put(struct lw_mbox *b, void *msg) {
    b->msgs[(b->head + b->count) % b->size] = msg;
    b->count++;
    LWP_CondSignal(b->not_empty);
}
void sys_mbox_post(sys_mbox_t *mbox, void *msg) {
    struct lw_mbox *b = *mbox;
    LWP_MutexLock(b->m);
    while (b->count == b->size) LWP_CondWait(b->not_full, b->m);
    put(b, msg);
    LWP_MutexUnlock(b->m);
}
err_t sys_mbox_trypost(sys_mbox_t *mbox, void *msg) {
    struct lw_mbox *b = *mbox;
    LWP_MutexLock(b->m);
    if (b->count == b->size) { LWP_MutexUnlock(b->m); return ERR_MEM; }
    put(b, msg);
    LWP_MutexUnlock(b->m);
    return ERR_OK;
}
err_t sys_mbox_trypost_fromisr(sys_mbox_t *mbox, void *msg) { return sys_mbox_trypost(mbox, msg); }
u32_t sys_arch_mbox_fetch(sys_mbox_t *mbox, void **msg, u32_t timeout) {
    struct lw_mbox *b = *mbox;
    u32_t start = sys_now();
    LWP_MutexLock(b->m);
    while (!b->count) {
        u32_t waited = sys_now() - start;
        if (timeout && waited >= timeout) { LWP_MutexUnlock(b->m); return SYS_ARCH_TIMEOUT; }
        if (timed_wait(b->not_empty, b->m, timeout ? timeout - waited : 0) && !b->count) {
            LWP_MutexUnlock(b->m);
            return SYS_ARCH_TIMEOUT;
        }
    }
    void *m = b->msgs[b->head];
    b->head = (b->head + 1) % b->size;
    b->count--;
    LWP_CondSignal(b->not_full);
    LWP_MutexUnlock(b->m);
    if (msg) *msg = m;
    return sys_now() - start;
}
u32_t sys_arch_mbox_tryfetch(sys_mbox_t *mbox, void **msg) {
    struct lw_mbox *b = *mbox;
    LWP_MutexLock(b->m);
    if (!b->count) { LWP_MutexUnlock(b->m); return SYS_MBOX_EMPTY; }
    void *m = b->msgs[b->head];
    b->head = (b->head + 1) % b->size;
    b->count--;
    LWP_CondSignal(b->not_full);
    LWP_MutexUnlock(b->m);
    if (msg) *msg = m;
    return 0;
}

struct thread_start { lwip_thread_fn fn; void *arg; };
static void *thread_tramp(void *p) {
    struct thread_start st = *(struct thread_start *)p;
    free(p);
    st.fn(st.arg);
    return NULL;
}
sys_thread_t sys_thread_new(const char *name, lwip_thread_fn thread, void *arg, int stacksize, int prio) {
    struct thread_start *st = malloc(sizeof *st);
    lwp_t t = LWP_THREAD_NULL;
    if (!st) return 0;
    st->fn = thread;
    st->arg = arg;
    if (LWP_CreateThread(&t, thread_tramp, st, NULL, stacksize > 0 ? stacksize : DEFAULT_THREAD_STACKSIZE,
                         prio > 0 && prio < 128 ? prio : DEFAULT_THREAD_PRIO) < 0) { free(st); return 0; }
    return t;
}
