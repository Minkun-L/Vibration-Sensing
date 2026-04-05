CC = gcc
CFLAGS = -shared -fPIC -O2 -Wall
TARGET = libspi_fifo.so
SRC = spi_fifo.c

all: $(TARGET)

$(TARGET): $(SRC)
	$(CC) $(CFLAGS) -o $@ $<

clean:
	rm -f $(TARGET)
