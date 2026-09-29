"""Hardware adapter: all R-T160-specific IDs, framing, commands and crop geometry."""

from dataclasses import dataclass
from typing import Protocol

import numpy as np

from .transport import Transport


@dataclass
class SensorFrame:
    pixels: np.ndarray
    model: str
    firmware: str


class Camera(Protocol):
    shutter_timing: tuple[float, float, float]
    bad_packets: int

    def request_calibration_table(self) -> None: ...
    def trigger_shutter(self) -> None: ...
    def next_event(self) -> SensorFrame | np.ndarray | None: ...
    def close(self) -> None: ...


class RT160:
    shutter_timing = (0.30, 0.75, 1.30)  # reference start/end, scene resume seconds
    USB = dict(vid=0x04B4, pid=0x000A, interface=0, alternate=1)

    def __init__(self, transport: Transport):
        self.transport = transport
        self.parts = []
        self.kparts = None
        self.bad_packets = 0
        self.frames = 0

    def request_calibration_table(self):
        self.kparts = []
        self.parts = []
        self.transport.write(0x06, b"\x80\x81", 1000)

    def trigger_shutter(self):
        self.parts = []
        self.transport.write(0x06, b"\x80\x00", 1000)

    def next_event(self):
        return self.accept(self.transport.read(0x82, 14848, 500))

    def accept(self, p):
        if not p:
            self.parts = []
            return None
        if len(p) < 12 or p[0] != 12:
            self.parts = []
            self.bad_packets += 1
            return None
        if p[6] == 2:
            self.parts = []
            if self.kparts is not None and len(p) >= 524:
                self.kparts.append(p[12:524])
                if len(self.kparts) == 192:
                    raw = b"".join(self.kparts)
                    self.kparts = None
                    k = (
                        np.frombuffer(raw, dtype="<u2")
                        .reshape(192, 256)[36:156, 48:208]
                        .astype(np.float32)
                        / 16384
                    )
                    if not np.all((k > 0.25) & (k < 4)):
                        raise ValueError("Implausible calibration table")
                    return k
            return None
        if len(p) != 14348 or p[6] != 1:
            self.parts = []
            self.bad_packets += 1
            return None
        m = p[1]
        if m in (0x8C, 0x8D):
            if self.parts and (len(self.parts) >= 6 or self.parts[0][1] != m):
                self.parts = []
                self.bad_packets += 1
            self.parts.append(p)
        elif m in (0x8E, 0x8F) and len(self.parts) == 6 and m == self.parts[0][1] + 2:
            self.parts.append(p)
            envelope = b"".join(self.parts)
            payload = b"".join(x[12:] for x in self.parts)
            self.parts = []
            model = envelope[98980:98996].split(b"\0")[0].decode("ascii", errors="replace").strip()
            firmware = (
                envelope[98948:98964].split(b"\0")[0].decode("ascii", errors="replace").strip()
            )
            if model != "R-T160":
                raise ValueError(f"Unsupported model {model!r}; refusing guessed geometry")
            self.frames += 1
            return SensorFrame(
                np.frombuffer(payload, dtype="<u2")
                .reshape(196, 256)[36:156, 48:208]
                .astype(np.float32),
                model,
                firmware,
            )
        else:
            self.parts = []
            self.bad_packets += 1
        return None

    def close(self):
        self.transport.close()
