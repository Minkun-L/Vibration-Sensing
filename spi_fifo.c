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

/* ── FIFO per-sample read: one SPI_IOC_MESSAGE(1) per FIFO byte ──── */
/*    KX132 BUF_READ auto-increments when CS is held low across       */
/*    multiple bytes (reads ADP_CNTL registers instead of FIFO data). */
/*    Each FIFO byte therefore requires its own separated CS cycle:   */
/*    one ioctl(SPI_IOC_MESSAGE(1)) per byte guarantees CS toggles.   */
/*    Using cs_change=1 in a batched SPI_IOC_MESSAGE(6) is NOT        */
/*    reliable on spi-bcm2835 — under load CS may not actually toggle,*/
/*    causing auto-increment and returning garbage register data.      */

int spi_fifo_read_samples(uint16_t n_samples, uint8_t *out_buf)
{
    uint8_t tx[2] = { 0x63 | 0x80, 0x00 };  /* BUF_READ with read bit */
    uint8_t rx[2];
    struct spi_ioc_transfer tr;

    memset(&tr, 0, sizeof(tr));
    tr.tx_buf   = (unsigned long)tx;
    tr.rx_buf   = (unsigned long)rx;
    tr.len      = 2;
    tr.cs_change = 0;  /* normal: CS deasserts after each 2-byte transfer */

    for (uint16_t i = 0; i < n_samples; i++) {
        for (int j = 0; j < 6; j++) {
            if (ioctl(spi_fd, SPI_IOC_MESSAGE(1), &tr) < 0) {
                perror("fifo sample read");
                return -1;
            }
            out_buf[i * 6 + j] = rx[1];
        }
    }
    return 0;
}
