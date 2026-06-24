"""FastAPI server for TPI-1005-A signal generator.

Usage:
    .venv/bin/python server.py [--port PORT] [--device /dev/ttyUSBx]

Endpoints:
    GET  /status           — current device state
    GET  /health           — server liveness
    POST /rf               — {"on": true|false}
    POST /freq             — {"mhz": 433.920}
    POST /level            — {"dbm": -10}
"""

import argparse
import contextlib
import logging
import sys

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, field_validator

from tpi import TPI1005A, TPIError, find_device

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

_device: TPI1005A | None = None


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    global _device
    port = app.state.device_port
    log.info("Opening %s …", port)
    try:
        _device = TPI1005A(port).open()
        log.info("Device ready: %s", _device.get_model())
    except Exception as e:
        log.error("Failed to open device: %s", e)
        _device = None
    yield
    if _device:
        _device.close()
        log.info("Device closed.")


app = FastAPI(title="TPI-1005-A server", version="0.1.0", lifespan=lifespan)


def _dev() -> TPI1005A:
    if _device is None:
        raise HTTPException(503, "Device not available")
    return _device


# ---------------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------------

class RFRequest(BaseModel):
    on: bool


class FreqRequest(BaseModel):
    mhz: float

    @field_validator("mhz")
    @classmethod
    def check_range(cls, v):
        if not (35.0 <= v <= 4400.0):
            raise ValueError(f"frequency {v} MHz out of range (35–4400)")
        return v


class LevelRequest(BaseModel):
    dbm: int

    @field_validator("dbm")
    @classmethod
    def check_range(cls, v):
        if not (-90 <= v <= 10):
            raise ValueError(f"level {v} dBm out of range (−90 to +10)")
        return v


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok", "device": _device is not None}


@app.get("/status")
def status():
    dev = _dev()
    try:
        return {
            "model": dev.get_model(),
            "serial": dev.get_serial(),
            "firmware": dev.get_firmware(),
            "freq_mhz": dev.get_freq(),
            "level_dbm": dev.get_level(),
            "rf_on": dev.get_rf(),
        }
    except TPIError as e:
        raise HTTPException(500, str(e))


@app.post("/rf")
def set_rf(req: RFRequest):
    dev = _dev()
    try:
        dev.set_rf(req.on)
        return {"rf_on": req.on}
    except TPIError as e:
        raise HTTPException(500, str(e))


@app.post("/freq")
def set_freq(req: FreqRequest):
    dev = _dev()
    try:
        dev.set_freq(req.mhz)
        actual = dev.get_freq()
        return {"freq_mhz": actual}
    except (TPIError, ValueError) as e:
        raise HTTPException(400, str(e))


@app.post("/level")
def set_level(req: LevelRequest):
    dev = _dev()
    try:
        dev.set_level(req.dbm)
        actual = dev.get_level()
        return {"level_dbm": actual}
    except TPIError as e:
        raise HTTPException(500, str(e))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="TPI-1005-A HTTP server")
    parser.add_argument("--port", type=int, default=8765, help="HTTP port (default 8765)")
    parser.add_argument("--device", default=None, help="Serial port (auto-detected if omitted)")
    args = parser.parse_args()

    device_port = args.device or find_device()
    if not device_port:
        print("ERROR: TPI-1005-A not found. Connect the device or pass --device /dev/ttyUSBx",
              file=sys.stderr)
        sys.exit(1)

    print(f"Using device: {device_port}")
    app.state.device_port = device_port
    uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
