# TPI-1005-A — Serial Protocol Reference

Source: **Application Note AN-2 rev 1.27** — "User Command Structure for TPI-1001, TPI-1002, & TPI-1005"
(Extracted from TPI-Link v2.025 embedded resources. Full PDF: `AN-2_TPI_User_Command_Structure_rev1.27.pdf`)

---

## Serial Port Parameters

| Parameter    | Value                                            |
|--------------|--------------------------------------------------|
| Device       | `/dev/ttyUSB0`                                   |
| Chip         | FTDI FT230X (VID:PID 0403:6015, SER DK0CXI2S)  |
| Baud rate    | **3,000,000** (3 Mbaud)                          |
| Data bits    | 8                                                |
| Stop bits    | 1                                                |
| Parity       | None                                             |
| Flow control | RTS (hardware, `rtscts=True` in pySerial)        |

---

## Binary Protocol (primary interface)

All communication uses length-framed binary packets. No prior configuration needed.

### Packet Structure

```
0xAA  0x55  <len_hi>  <len_lo>  [body bytes...]  <checksum>
```

- `0xAA 0x55` — two-byte frame marker (resync anchor)
- `len_hi:len_lo` — 16-bit big-endian count of body bytes
- `checksum` = `(0xFF - (len_hi + len_lo + sum(body))) & 0xFF`

First byte of body:
- `0x07` = **read** command
- `0x08` = **write** command

Second byte of body = command code.

### Python helpers

```python
import struct, serial

def build_packet(body):
    body = bytes(body)
    n = len(body)
    len_hi, len_lo = (n >> 8) & 0xFF, n & 0xFF
    cs = (0xFF - (len_hi + len_lo + sum(body))) & 0xFF
    return bytes([0xAA, 0x55, len_hi, len_lo]) + body + bytes([cs])

def parse_packet(data):
    """Extract body from a raw received packet."""
    if len(data) < 5 or data[0] != 0xAA or data[1] != 0x55:
        return None
    n = (data[2] << 8) | data[3]
    return data[4:4 + n] if len(data) >= 4 + n + 1 else None
```

---

## Essential Commands (body bytes only)

> Surround each body with `build_packet(body)` and send the result.
> Device echoes the first two body bytes in every write response.

### 2.1 User Control — must enable first, once per session

```
Enable:  write 0x08 0x01   → responds 0x08 0x01
Read:    write 0x07 0x01   → responds 0x07 0x01 n  (n=1 if enabled)
```

Full enable packet: `AA 55 00 02 08 01 F4`

### 2.2–2.5 Device Info

| Command      | Body (send)  | Response body               |
|--------------|--------------|-----------------------------|
| Model number | `07 02`      | `07 02` + 16-byte ASCII     |
| Serial number| `07 03`      | `07 03` + 16-byte ASCII     |
| HW version   | `07 04`      | `07 04` + 16-byte ASCII     |
| FW version   | `07 05`      | `07 05` + 16-byte ASCII     |

### 2.9 Frequency

```python
# Read: 0x07 0x09 → body: 07 09 n0 n1 n2 n3 (32-bit LE, kHz)
# Write: 0x08 0x09 + struct.pack('<I', freq_khz)

freq_khz = int(round(freq_mhz * 1000))   # range 35000–4400000
body = [0x08, 0x09] + list(struct.pack('<I', freq_khz))
# Response: 08 09
```

### 2.10 RF Output Level

```python
# Read: 0x07 0x0A → body: 07 0A n (signed byte, dBm)
# Write: 0x08 0x0A n (signed byte; clamped to device min/max)

body = [0x08, 0x0A, dbm & 0xFF]  # signed: -10 → 0xF6
# Response: 08 0A n (actual level set)
```

### 2.11 RF Output On/Off

```python
# Read: 0x07 0x0B → body: 07 0B n (0=off, 1=on)
# Write: 0x08 0x0B n

body = [0x08, 0x0B, 0x01]  # RF on
body = [0x08, 0x0B, 0x00]  # RF off
# Response: 08 0B
```

### 2.7 Supply Voltages (diagnostic)

```python
# 0x07 0x07 → 26 body bytes: 07 07 + six IEEE-754 floats (32-bit LE)
# Labels: RF, VCO, MCU, OSC, PA, DET/USB
import struct
volts = [struct.unpack_from('<f', body, 2 + i*4)[0] for i in range(6)]
```

### 2.56 Error Notification (device → host, unsolicited)

Body: `07 FF n` where n is error number:

| n  | Error                        |
|----|------------------------------|
| 1  | Checksum error               |
| 2  | Undefined command type       |
| 3  | Undefined command            |
| 4  | Data out of range            |
| 7  | Requested RF level < −90 dBm |
| 27 | Comm watchdog timeout        |

---

## Minimal Python Session

```python
import serial, struct, time

ser = serial.Serial('/dev/ttyUSB0', 3_000_000, rtscts=True, timeout=0.5)

def build_packet(body):
    body = bytes(body)
    n = len(body)
    cs = (0xFF - ((n >> 8) + (n & 0xFF) + sum(body))) & 0xFF
    return bytes([0xAA, 0x55, (n >> 8), n & 0xFF]) + body + bytes([cs])

def send(body):
    ser.write(build_packet(body))
    time.sleep(0.1)
    return ser.read(ser.in_waiting or 1)

# 1. Enable user control
send([0x08, 0x01])

# 2. Set 433.920 MHz
send([0x08, 0x09] + list(struct.pack('<I', 433920)))

# 3. Set −10 dBm
send([0x08, 0x0A, (-10) & 0xFF])

# 4. RF on
send([0x08, 0x0B, 0x01])

# 5. RF off
send([0x08, 0x0B, 0x00])
```

---

## ASCII Commands (optional — must be enabled first)

ASCII mode must be enabled once via TPI-Link: System tab → "Enable ASCII Control".
The device remembers this setting. Then send ASCII strings at 3 Mbaud:

```
#RF=ON\n          → responds "RF = ON"
#RF=OFF\n         → responds "RF = OFF"
#RF=?\n           → "RF = ON" or "RF = OFF"
#FREQ=433.920\n   → responds "FREQ = 433.920 MHz"
#FREQ=?\n         → returns current frequency
#LEVEL=-10\n      → responds "LEVEL = -10 dBm"
#LEVEL=?\n        → returns current level
#DET=?\n          → detector level in dBm (TPI-1005 only)
```

> Note: `rfon`/`rfoff`/`setfreq`/`setpwr` are **control script** commands stored in EEPROM — NOT the ASCII wire protocol.

---

## SCPI Commands (optional — must be enabled first)

Enable once via TPI-Link: System tab → "SCPI Control". Requires firmware ≥ 1.074.

```
*RST                          — stop all modes, RF off
SOURce:FREQuency <MHz>        — set frequency (≤ 3 decimal places)
SOURce:FREQuency?             — query (returns "n.nnn MHz")
SOURce:POWer <integer>        — set level in dBm
SOURce:POWer?                 — query (returns "n dBm")
SOURce:OUTPut:STATe ON|OFF    — RF on/off
SOURce:OUTPut:STATe?          — query (returns "ON" or "OFF")
```

---

## Device Specifications

| Parameter          | TPI-1005-A      |
|--------------------|-----------------|
| Frequency range    | 35–4400 MHz     |
| Output level range | +10 to −90 dBm  |
| Frequency step     | 1 kHz           |
| Level step         | 1 dB            |
| USB chip           | FTDI FT230X     |
| MCU                | Atmel           |
| Power              | +5 V USB        |
