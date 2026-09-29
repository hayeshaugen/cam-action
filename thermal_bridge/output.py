"""Video output adapter. FFmpeg publishes H.264; an external RTSP server fans it out."""

import subprocess
import time
from pathlib import Path


class RtspOutput:
    def __init__(self, state, stop, url, ffmpeg, log):
        self.state = state
        self.stop = stop
        self.url = url
        self.ffmpeg = ffmpeg
        self.log = Path(log)
        self.process = None

    def run(self):
        while not self.stop.is_set():
            try:
                with self.log.open("ab", buffering=0) as err:
                    self.process = subprocess.Popen(
                        [
                            self.ffmpeg,
                            "-hide_banner",
                            "-loglevel",
                            "warning",
                            "-f",
                            "rawvideo",
                            "-pixel_format",
                            "rgb24",
                            "-video_size",
                            "640x480",
                            "-framerate",
                            "25",
                            "-i",
                            "pipe:0",
                            "-an",
                            "-c:v",
                            "libx264",
                            "-preset",
                            "ultrafast",
                            "-tune",
                            "zerolatency",
                            "-pix_fmt",
                            "yuv420p",
                            "-g",
                            "25",
                            "-bf",
                            "0",
                            "-crf",
                            "20",
                            "-f",
                            "rtsp",
                            "-rtsp_transport",
                            "tcp",
                            self.url,
                        ],
                        stdin=subprocess.PIPE,
                        stderr=err,
                    )
                    process = self.process
                    due = time.monotonic()
                    while not self.stop.is_set():
                        frame = self.state.video_frame()
                        process.stdin.write(frame.tobytes())
                        process.stdin.flush()
                        self.state.update(publisher="running")
                        due += 0.04
                        if due < time.monotonic() - 0.08:
                            due = time.monotonic()
                        self.stop.wait(max(0, due - time.monotonic()))
            except (OSError, ValueError) as e:
                self.state.update(publisher=f"retrying: {e}")
            finally:
                self.close()
            self.stop.wait(2)

    def close(self):
        p = self.process
        if p and p.poll() is None:
            p.terminate()
            try:
                p.wait(3)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()
        self.process = None
