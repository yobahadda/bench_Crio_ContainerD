/* Minimal pod sandbox process: sleeps until told to stop. */
#include <signal.h>
#include <unistd.h>

static void stop(int sig) { (void)sig; _exit(0); }

int main(void) {
    signal(SIGTERM, stop);
    signal(SIGINT, stop);
    for (;;) pause();
}
