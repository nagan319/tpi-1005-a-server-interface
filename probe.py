#!/usr/bin/env python3
"""Interactive probe for TPI-1005-A over /dev/ttyUSB0.

Binary protocol (AN-2 rev 1.27):
  Packet: 0xAA 0x55 <len_hi> <len_lo> [body...] <checksum>
  checksum = 0xFF - ((len_hi + len_lo + sum(body)) & 0xFF)
  First body byte: 0x07 = read, 0x08 = write

Usage:
    .venv/bin/python probe.py [port]
"""

import sys
import time
import struct
import serial

PORT = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
BAUD = 3_000_000


def build_packet(body: bytes | list) -> bytes:
    body = bytes(body)
    n = len(body)
    len_hi = (n >> 8) & 0xFF
    len_lo = n & 0xFF
    cs = (0xFF - (len_hi + len_lo + sum(body))) & 0xFF
    return bytes([0xAA, 0x55, len_hi, len_lo]) + body + bytes([cs])


def parse_packet(data: bytes) -> bytes | None:
    """Parse one packet from data; return body bytes or None on failure."""
    if len(data) < 5:
        return None
    if data[0] != 0xAA or data[1] != 0x55:
        return None
    n = (data[2] << 8) | data[3]
    if len(data) < 4 + n + 1:
        return None
    body = data[4:4 + n]
    cs_expected = (0xFF - (data[2] + data[3] + sum(body))) & 0xFF
    cs_actual = data[4 + n]
    if cs_expected != cs_actual:
        print(f"  [checksum error: expected 0x{cs_expected:02x}, got 0x{cs_actual:02x}]")
    return body


def read_response(ser: serial.Serial, timeout: float = 0.5) -> bytes:
    deadline = time.monotonic() + timeout
    buf = b""
    while time.monotonic() < deadline:
        chunk = ser.read(ser.in_waiting or 1)
        if chunk:
            buf += chunk
            deadline = time.monotonic() + 0.1
    return buf


def send_and_recv(ser: serial.Serial, body: list | bytes, label: str = "") -> bytes | None:
    pkt = build_packet(body)
    if label:
        print(f"  [{label}]")
    print(f"  sent: {pkt.hex(' ')}")
    ser.write(pkt)
    raw = read_response(ser)
    if not raw:
        print("  recv: (no response)")
        return None
    print(f"  recv: {raw.hex(' ')}")
    return parse_packet(raw)


HELP = """
Commands:
  :ctrl        — enable user control (must send first)
  :id          — read model, serial, hardware, firmware version
  :state       — read current unit state
  :freq?       — read current frequency
  :freq N      — set frequency to N MHz (e.g. :freq 433.920)
  :pwr?        — read current output level (dBm)
  :pwr N       — set output level to N dBm (e.g. :pwr -10)
  :rf?         — read RF output on/off state
  :rf on       — turn RF output on
  :rf off      — turn RF output off
  :volts       — read supply voltages
  :raw <hex>   — send raw body bytes (hex), e.g. :raw 07 02
  :pkt <hex>   — send raw full packet bytes
  Ctrl-C to quit.
"""


def main():
    print(f"Opening {PORT} at {BAUD} baud, 8N1, RTS...")
    try:
        ser = serial.Serial(
            port=PORT,
            baudrate=BAUD,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            rtscts=True,
            timeout=0.1,
        )
    except serial.SerialException as e:
        print(f"Error: {e}")
        sys.exit(1)

    print(f"Connected. RTS={ser.rts}, CTS={ser.cts}")
    print(HELP)

    time.sleep(0.1)
    ser.reset_input_buffer()

    try:
        while True:
            try:
                cmd = input(">> ").strip()
            except EOFError:
                break
            if not cmd:
                continue

            if cmd == ":ctrl":
                body = send_and_recv(ser, [0x08, 0x01], "enable user control")
                if body and len(body) >= 2 and body[0] == 0x08 and body[1] == 0x01:
                    print("  user control enabled")

            elif cmd == ":id":
                for code, label in [(0x02, "model"), (0x03, "serial"), (0x04, "hw ver"), (0x05, "fw ver")]:
                    body = send_and_recv(ser, [0x07, code], label)
                    if body and len(body) >= 3:
                        text = body[2:].decode("ascii", errors="replace").strip("\x00 ")
                        print(f"  {label}: {text!r}")

            elif cmd == ":state":
                body = send_and_recv(ser, [0x07, 0x08], "read state")
                if body and len(body) >= 4:
                    states = {0: "generator", 1: "sq wave mod", 2: "beacon mod", 3: "script mod", 4: "scanning", 5: "script running"}
                    print(f"  state: {states.get(body[2], f'unknown 0x{body[2]:02x}')} n1=0x{body[3]:02x}")

            elif cmd == ":freq?":
                body = send_and_recv(ser, [0x07, 0x09], "read freq")
                if body and len(body) >= 6:
                    freq_khz = struct.unpack_from("<I", body, 2)[0]
                    print(f"  frequency: {freq_khz / 1000:.3f} MHz")

            elif cmd.startswith(":freq "):
                try:
                    mhz = float(cmd[6:])
                    khz = int(round(mhz * 1000))
                    if not (35000 <= khz <= 4400000):
                        print(f"  error: {mhz} MHz out of range (35–4400 MHz)")
                        continue
                    body_bytes = [0x08, 0x09] + list(struct.pack("<I", khz))
                    body = send_and_recv(ser, body_bytes, f"set freq {mhz} MHz")
                    if body and len(body) >= 2 and body[0] == 0x08 and body[1] == 0x09:
                        print(f"  frequency set to {mhz} MHz")
                except ValueError:
                    print("  usage: :freq <MHz>")

            elif cmd == ":pwr?":
                body = send_and_recv(ser, [0x07, 0x0A], "read level")
                if body and len(body) >= 3:
                    dbm = struct.unpack_from("b", body, 2)[0]
                    print(f"  level: {dbm} dBm")

            elif cmd.startswith(":pwr "):
                try:
                    dbm = int(cmd[5:])
                    if not (-90 <= dbm <= 10):
                        print(f"  warning: {dbm} dBm may be out of range for TPI-1005-A (−90 to +10)")
                    body_bytes = [0x08, 0x0A, dbm & 0xFF]
                    body = send_and_recv(ser, body_bytes, f"set level {dbm} dBm")
                    if body and len(body) >= 3:
                        actual = struct.unpack_from("b", body, 2)[0]
                        print(f"  level set to {actual} dBm")
                except ValueError:
                    print("  usage: :pwr <dBm>")

            elif cmd == ":rf?":
                body = send_and_recv(ser, [0x07, 0x0B], "read RF state")
                if body and len(body) >= 3:
                    print(f"  RF output: {'ON' if body[2] else 'OFF'}")

            elif cmd in (":rf on", ":rf off"):
                on = cmd.endswith("on")
                body_bytes = [0x08, 0x0B, 0x01 if on else 0x00]
                body = send_and_recv(ser, body_bytes, f"RF {'on' if on else 'off'}")
                if body and len(body) >= 2 and body[0] == 0x08 and body[1] == 0x0B:
                    print(f"  RF output turned {'ON' if on else 'OFF'}")

            elif cmd == ":volts":
                body = send_and_recv(ser, [0x07, 0x07], "read voltages")
                if body and len(body) >= 26:
                    labels = ["RF", "VCO", "MCU", "OSC", "PA", "DET/USB"]
                    for i, label in enumerate(labels):
                        v = struct.unpack_from("<f", body, 2 + i * 4)[0]
                        print(f"  {label}: {v:.3f} V")

            elif cmd.startswith(":raw "):
                try:
                    body_bytes = bytes.fromhex(cmd[5:].replace(" ", ""))
                    body = send_and_recv(ser, body_bytes, "raw body")
                    if body:
                        print(f"  body: {body.hex(' ')}  {list(body)}")
                except ValueError as e:
                    print(f"  error: {e}")

            elif cmd.startswith(":pkt "):
                try:
                    raw = bytes.fromhex(cmd[5:].replace(" ", ""))
                    print(f"  sent: {raw.hex(' ')}")
                    ser.write(raw)
                    resp = read_response(ser)
                    if resp:
                        print(f"  recv: {resp.hex(' ')}")
                    else:
                        print("  recv: (nothing)")
                except ValueError as e:
                    print(f"  error: {e}")

            elif cmd == "?":
                print(HELP)

            else:
                print(f"  unknown command: {cmd!r}  (type ? for help)")

    except KeyboardInterrupt:
        print("\nBye.")
    finally:
        ser.close()


if __name__ == "__main__":
    main()
