"""Sensor-domain correction and display rendering; no USB or streaming dependencies."""

import struct
import zlib

import numpy as np


class Calibration:
    # Timing is a hardware-adapter policy, not a detected firmware flag.
    def __init__(self, gain, timing=(0.30, 0.75, 1.30)):
        self.timing = timing
        self.gain = gain
        self.reference = None
        self.start = None
        self.samples = []
        self.baseline = None
        self.state = "needs calibration"
        self.last_mean = None

    def begin(self, now):
        self.start = now
        self.samples = []
        self.baseline = self.last_mean
        self.state = "calibrating"

    def apply(self, pixels, now):
        self.last_mean = float(pixels.mean())
        if self.start is not None:
            age = now - self.start
            if self.timing[0] <= age <= self.timing[1]:
                self.samples.append(pixels.copy())
            if age < self.timing[2]:
                return None
            self.start = None
            if len(self.samples) < 4:
                self.state = "calibration failed: insufficient frames"
                return None
            ref = np.mean(self.samples, axis=0)
            # Verify shutter excursion followed by a return toward the pre-shutter scene.
            delta = abs(float(ref.mean()) - self.baseline) if self.baseline is not None else 0
            returned = abs(float(ref.mean()) - self.last_mean)
            if delta < 20 or returned < max(10, delta * 0.3):
                self.state = "calibration failed: shutter transition not confirmed"
                return None
            self.reference = ref
            self.state = "streaming"
        if self.reference is None or self.state.startswith("calibration failed"):
            return None
        return (pixels - self.reference) * self.gain


class Renderer:
    def __init__(self):
        self.bounds = None

    def render(self, signal, rotation=180, palette="gray"):
        lo, hi = np.percentile(signal, [1, 99])
        hi = max(hi, lo + 1)
        if self.bounds is None:
            self.bounds = (lo, hi)
        else:
            self.bounds = tuple(0.9 * a + 0.1 * b for a, b in zip(self.bounds, (lo, hi)))
        lo, hi = self.bounds
        x = np.clip((signal - lo) / (hi - lo), 0, 1)
        x = np.rot90(x, rotation // 90)
        if palette == "iron":
            anchors = np.array(
                [
                    [0, 0, 0],
                    [35, 0, 85],
                    [150, 20, 85],
                    [235, 85, 10],
                    [255, 210, 70],
                    [255, 255, 255],
                ]
            )
            rgb = np.stack(
                [np.interp(x, np.linspace(0, 1, len(anchors)), anchors[:, c]) for c in range(3)],
                axis=-1,
            ).astype(np.uint8)
        else:
            if palette == "blackhot":
                x = 1 - x
            rgb = np.repeat((x * 255).astype(np.uint8)[..., None], 3, axis=2)
        # Fixed output canvas, even when rotating 90 degrees.
        h, w = rgb.shape[:2]
        scale = min(640 // w, 480 // h)
        enlarged = rgb.repeat(scale, 0).repeat(scale, 1)
        out = np.zeros((480, 640, 3), dtype=np.uint8)
        y = (480 - enlarged.shape[0]) // 2
        xx = (640 - enlarged.shape[1]) // 2
        out[y : y + enlarged.shape[0], xx : xx + enlarged.shape[1]] = enlarged
        return out


def png(rgb):
    h, w, _ = rgb.shape

    def chunk(t, b):
        return struct.pack(">I", len(b)) + t + b + struct.pack(">I", zlib.crc32(t + b) & 0xFFFFFFFF)

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"".join(b"\0" + r.tobytes() for r in rgb), 1))
        + chunk(b"IEND", b"")
    )
