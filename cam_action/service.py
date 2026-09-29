"""Application orchestration.

One acquisition thread owns the camera. Other threads receive the latest
rendered frame or enqueue a command; they never touch USB directly.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections.abc import Callable

import numpy as np

from .camera import Camera, SensorFrame
from .processing import Calibration, Renderer


class State:
    """Thread-safe status, latest frame, display options, and command queue."""

    def __init__(self):
        self.lock = threading.Lock()
        self.commands = queue.Queue(maxsize=8)
        self.info = {
            "camera": "connecting",
            "publisher": "starting",
            "frames": 0,
            "rotation": 180,
            "palette": "gray",
            "units": "relative signal, not Celsius",
        }
        self.frame = np.zeros((480, 640, 3), dtype=np.uint8)
        self.updated = 0

    def update(self, **kw: object) -> None:
        with self.lock:
            self.info.update(kw)

    def snapshot(self) -> dict[str, object]:
        with self.lock:
            return dict(
                self.info,
                frame_age_seconds=round(time.monotonic() - self.updated, 2)
                if self.updated
                else None,
            )

    def options(self) -> tuple[int, str]:
        with self.lock:
            return self.info["rotation"], self.info["palette"]

    def set_frame(self, frame: np.ndarray) -> None:
        with self.lock:
            self.frame = frame
            self.updated = time.monotonic()

    def video_frame(self) -> np.ndarray:
        with self.lock:
            # Never present indefinitely stale images as live: black after 2 seconds.
            if not self.updated or time.monotonic() - self.updated > 2:
                return np.zeros_like(self.frame)
            return self.frame.copy()


class Acquisition:
    """Run a camera adapter, schedule calibration, and publish rendered frames."""

    def __init__(
        self,
        factory: Callable[[], Camera],
        state: State,
        stop: threading.Event,
        calibration_interval: float = 90,
    ):
        self.factory = factory
        self.state = state
        self.stop = stop
        self.interval = calibration_interval

    def run(self):
        while not self.stop.is_set():
            cam = None
            try:
                self.state.update(camera="connecting")
                cam = self.factory()
                cam.request_calibration_table()
                deadline = time.monotonic() + 6
                self.state.update(camera="reading calibration table")
                correction = None
                renderer = Renderer()
                last_cal = 0
                last_data = time.monotonic()
                count = 0
                fps_start = last_data
                while not self.stop.is_set():
                    event = cam.next_event()
                    now = time.monotonic()
                    if event is None:
                        if now - last_data > 3:
                            raise OSError("No complete frames for three seconds")
                        if correction is None and now > deadline:
                            raise OSError("Calibration table timeout")
                        continue
                    last_data = now
                    if isinstance(event, np.ndarray):
                        correction = Calibration(event, cam.shutter_timing)
                        self.state.update(camera="waiting for calibration baseline")
                        continue
                    if not isinstance(event, SensorFrame):
                        continue
                    count += 1
                    self.state.update(
                        frames=self.state.snapshot()["frames"] + 1,
                        model=event.model,
                        firmware=event.firmware,
                        input_fps=round(count / max(0.01, now - fps_start), 1),
                        bad_packets=cam.bad_packets,
                    )
                    if correction is None:
                        continue
                    manual = False
                    try:
                        while True:
                            if self.state.commands.get_nowait() == "calibrate":
                                manual = True
                    except queue.Empty:
                        pass
                    if correction.start is None and (
                        not last_cal
                        or manual
                        or (self.interval > 0 and now - last_cal >= self.interval)
                    ):
                        correction.last_mean = float(event.pixels.mean())
                        cam.trigger_shutter()
                        correction.begin(time.monotonic())
                        last_cal = now
                        logging.info("Shutter calibration requested")
                        self.state.update(camera=correction.state)
                        continue
                    signal = correction.apply(event.pixels, now)
                    self.state.update(camera=correction.state)
                    if signal is not None:
                        rotation, palette = self.state.options()
                        self.state.set_frame(renderer.render(signal, rotation, palette))
            except Exception as e:
                logging.exception("Camera session failed")
                self.state.update(camera=f"reconnecting: {e}")
            finally:
                if cam:
                    try:
                        cam.close()
                    except Exception:
                        logging.exception("Camera cleanup failed")
            self.stop.wait(2)
