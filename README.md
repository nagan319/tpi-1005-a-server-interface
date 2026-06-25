# TPI-1005-A RF Signal Generator Server Configuration 

This is a server config that allows for interfacing with the TPI-1005-A RF signal generator directly over LAN, without having to use the built-in GUI through a local USB.

## How to Use


## Files

### tpi-serial-commands.md

This file contains useful information extracted from `AN-2_TPI_User_Command_Structure_rev1.27.pdf`. The packet structure and port parameters are listed. However, not much is explained about how the protocol works so I'll do it here.

**Serial Properties**
Some properties for the serial UART connection between the chip and the device.

The generator uses the FTDI FT230X chip. VID (vendor ID) and PID (product ID) are 0403 and 6015 respectively. SER (serial number) DK0CXI2S. These can be used to identify the chip over a serial connection (when scanning ports).
The baud rate is 3 million. This is just the number of times the voltage switches per second.
The 'data bits' i.e. the number of bits that encode a character is 8. There is also a single 'stop bit' after each 8 character bits that lets the port know the previous one is finished. There's no extra 'parity bit'.
RTS means the chip needs to agree before information is sent onto it (`rtscts=True`).

**Binary Packet Structure**
The file explains this pretty well:

```
0xAA  0x55  <len_hi>  <len_lo>  [body bytes...]  <checksum>
```

- `0xAA 0x55` — two-byte frame marker (resync anchor)
- `len_hi:len_lo` — 16-bit big-endian count of body bytes
    (this just says how long the body is)
- `checksum` = `(0xFF - (len_hi + len_lo + sum(body))) & 0xFF`
    (makes it apparent if package is corrupt)

First byte of body:
- `0x07` = **read** command
- `0x08` = **write** command

Second byte of body = command code.

*finish this after tpi.py and other stuff*

### tpi.py

The serial driver for the TPI-1005-A, which uses the commands listed in `tpi-serial-commands.md`.

### probe.py

CLI wrapper for `tpi.py`. In practice both `probe.py` and `gui.py` are useful for locally testing the serial driver but not actually necessary if using the server configuration.

Used as `.venv/bin/python probe.py [port]`. Omitting the port argument defaults to `/dev/ttyUSB0`.

### gui.py

GUI wrapper for `tpi.py`. Same as `probe.py` just graphic.

### server.py

ngl I haven't used this one

