"""Start the local RTSP server and camera bridge together; Ctrl-C stops both."""

import argparse
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mediamtx")
    parser.add_argument("--ffmpeg")
    args, extra = parser.parse_known_args()
    if "--help" in extra:
        return
    bundled = ROOT / "bin" / ("mediamtx.exe" if os.name == "nt" else "mediamtx")
    mtx = args.mediamtx or shutil.which("mediamtx") or (str(bundled) if bundled.exists() else None)
    ffmpeg = args.ffmpeg or shutil.which("ffmpeg")
    if not mtx or not ffmpeg:
        parser.error("Install FFmpeg and MediaMTX, or supply --ffmpeg and --mediamtx paths")
    for port in [18554, 8787]:
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                parser.error(f"Port {port} already in use; stop the existing bridge/server first")
    (ROOT / "runtime").mkdir(exist_ok=True)
    children = []
    stopping = False

    def stop(*_):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        children.append(subprocess.Popen([mtx, str(ROOT / "mediamtx.yml")], cwd=ROOT))
        time.sleep(0.5)
        if children[0].poll() is not None:
            raise RuntimeError("MediaMTX failed; see its log above")
        children.append(
            subprocess.Popen(
                [sys.executable, "-m", "thermal_bridge", "--ffmpeg", ffmpeg, *extra], cwd=ROOT
            )
        )
        print(
            "Preview: http://127.0.0.1:8787\nRTSP: rtsp://127.0.0.1:18554/thermal\nCtrl-C stops both processes.",
            flush=True,
        )
        while not stopping:
            if any(p.poll() is not None for p in children):
                raise RuntimeError("A bridge process exited")
            time.sleep(0.3)
    finally:
        for p in reversed(children):
            if p.poll() is None:
                p.terminate()
                try:
                    p.wait(8)
                except subprocess.TimeoutExpired:
                    p.kill()
                    p.wait()


if __name__ == "__main__":
    main()
