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

/* ── FIFO per-sample read: N separate SPI transactions ─ */
/*    Each transaction: [0xE3, 0,0,0,0,0,0] → 6 data bytes */
/*    CS toggles between each sample, advancing FIFO ptr    */

int spi_fifo_read_samples(uint16_t n_samples, uint8_t *out_buf)
{
    uint8_t tx[7] = { 0x63 | 0x80, 0, 0, 0, 0, 0, 0 };
    uint8_t rx[7];

    for (uint16_t i = 0; i < n_samples; i++) {
        struct spi_ioc_transfer tr = {
            .tx_buf        = (unsigned long)tx,
            .rx_buf        = (unsigned long)rx,
            .len           = 7,
            .speed_hz      = 0,
            .bits_per_word = 0,
            .cs_change     = 0,
            .delay_usecs   = 0,
        };
        int ret = ioctl(spi_fd, SPI_IOC_MESSAGE(1), &tr);
        if (ret < 0) { perror("fifo sample read"); return ret; }
        memcpy(out_buf + i * 6, rx + 1, 6);
    }
    return 0;
}
