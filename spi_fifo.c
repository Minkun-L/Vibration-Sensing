/*
 * spi_fifo.c — KX132 SPI helper via direct ioctl
 *
 * Provides:
 *   spi_open()          — open /dev/spidevX.Y, configure mode & speed
 *   spi_close()         — close fd
 *   spi_write_reg()     — single register write
 *   spi_read_reg()      — single register read (small, ≤256 bytes)
 *   spi_fifo_burst()    — burst read N samples from BUF_READ (0x63)
 *                         in one ioctl call with CS held low
 *
 * Compile:
 *   gcc -shared -fPIC -O2 -o libspi_fifo.so spi_fifo.c
 */

#include <fcntl.h>
#include <unistd.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>
#include <sys/ioctl.h>
#include <linux/spi/spidev.h>

static int spi_fd = -1;

/* ── open & configure ────────────────────────────────── */

int spi_open(const char *device, uint32_t speed_hz, uint8_t mode)
{
    spi_fd = open(device, O_RDWR);
    if (spi_fd < 0) { perror("spi open"); return -1; }

    if (ioctl(spi_fd, SPI_IOC_WR_MODE, &mode) < 0)
    { perror("set mode"); close(spi_fd); spi_fd = -1; return -1; }

    uint8_t bits = 8;
    if (ioctl(spi_fd, SPI_IOC_WR_BITS_PER_WORD, &bits) < 0)
    { perror("set bits"); close(spi_fd); spi_fd = -1; return -1; }

    if (ioctl(spi_fd, SPI_IOC_WR_MAX_SPEED_HZ, &speed_hz) < 0)
    { perror("set speed"); close(spi_fd); spi_fd = -1; return -1; }

    return 0;
}

void spi_close(void)
{
    if (spi_fd >= 0) { close(spi_fd); spi_fd = -1; }
}

/* ── single register write (2 bytes) ───────────────── */

int spi_write_reg(uint8_t reg, uint8_t value)
{
    uint8_t tx[2] = { reg & 0x7F, value };
    struct spi_ioc_transfer tr = {
        .tx_buf = (unsigned long)tx,
        .rx_buf = 0,
        .len    = 2,
    };
    return ioctl(spi_fd, SPI_IOC_MESSAGE(1), &tr);
}

/* ── single register read (1 + length bytes) ────────── */

int spi_read_reg(uint8_t reg, uint8_t *buf, uint16_t length)
{
    uint8_t tx[257];
    uint8_t rx[257];
    uint16_t total = 1 + length;
    if (total > 257) return -1;

    memset(tx, 0, total);
    tx[0] = reg | 0x80;

    struct spi_ioc_transfer tr = {
        .tx_buf = (unsigned long)tx,
        .rx_buf = (unsigned long)rx,
        .len    = total,
    };
    int ret = ioctl(spi_fd, SPI_IOC_MESSAGE(1), &tr);
    if (ret < 0) return ret;

    memcpy(buf, rx + 1, length);
    return 0;
}

/* ── FIFO per-sample read: 6 × 2-byte SPI transactions per sample ── */
/*    KX132 BUF_READ auto-increments address in multi-byte reads,     */
/*    so each FIFO byte must be a separate 2-byte SPI transaction:    */
/*    [0xE3, 0x00] → rx[1] = one FIFO byte.                          */
/*    We batch 6 transfers per ioctl using cs_change flag.            */

int spi_fifo_read_samples(uint16_t n_samples, uint8_t *out_buf)
{
    uint8_t tx[6][2];
    uint8_t rx[6][2];
    struct spi_ioc_transfer tr[6];

    /* Pre-fill the tx buffers and zero the transfer structs */
    memset(tr, 0, sizeof(tr));
    for (int j = 0; j < 6; j++) {
        tx[j][0] = 0x63 | 0x80;   /* BUF_READ command */
        tx[j][1] = 0x00;
        tr[j].tx_buf        = (unsigned long)tx[j];
        tr[j].rx_buf        = (unsigned long)rx[j];
        tr[j].len           = 2;
        tr[j].cs_change     = 1;  /* deassert CS after each transfer */
    }
    /* Last transfer: cs_change=0 → CS deasserts normally at end */
    tr[5].cs_change = 0;

    for (uint16_t i = 0; i < n_samples; i++) {
        int ret = ioctl(spi_fd, SPI_IOC_MESSAGE(6), tr);
        if (ret < 0) { perror("fifo sample read"); return ret; }
        for (int j = 0; j < 6; j++) {
            out_buf[i * 6 + j] = rx[j][1];
        }
    }
    return 0;
}
