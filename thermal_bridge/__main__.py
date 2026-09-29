import argparse
import logging
import signal
import threading
from pathlib import Path

from .camera import RT160
from .control import server
from .output import RtspOutput
from .service import Acquisition, State
from .transport import LibusbTransport


def main():
    ap = argparse.ArgumentParser(description="R-T160 thermal camera to RTSP and local preview")
    ap.add_argument("--rtsp", default="rtsp://127.0.0.1:18554/thermal")
    ap.add_argument("--ffmpeg", default="ffmpeg")
    ap.add_argument("--libusb")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--calibration-interval", type=float, default=90)
    ap.add_argument("--runtime", type=Path, default=Path("runtime"))
    args = ap.parse_args()
    args.runtime.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    stop = threading.Event()
    state = State()
    http = server(state, args.port)
    output = RtspOutput(state, stop, args.rtsp, args.ffmpeg, args.runtime / "ffmpeg.log")
    acquire = Acquisition(
        lambda: RT160(LibusbTransport(**RT160.USB, library=args.libusb)),
        state,
        stop,
        args.calibration_interval,
    )
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    threads = [
        threading.Thread(target=acquire.run, name="camera", daemon=True),
        threading.Thread(target=output.run, name="publisher", daemon=True),
        threading.Thread(target=http.serve_forever, name="control", daemon=True),
    ]
    for t in threads:
        t.start()
    logging.info("Preview http://127.0.0.1:%d ; RTSP %s", args.port, args.rtsp)
    try:
        while not stop.wait(1):
            pass
    finally:
        output.close()
        http.shutdown()
        http.server_close()
        for t in threads:
            t.join(3)


if __name__ == "__main__":
    main()
