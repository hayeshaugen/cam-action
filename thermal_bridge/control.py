"""Local companion UI and command API; no direct hardware access."""

import json
import queue
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .processing import png

PAGE = """<!doctype html><meta charset="utf-8"><title>Thermal Bridge</title>
<style>body{background:#15191f;color:#eef;font:17px system-ui;max-width:800px;margin:32px auto}img{width:100%;image-rendering:pixelated}button,select{font:inherit;padding:8px;margin:8px}pre{white-space:pre-wrap;color:#acc}code{color:#fba}</style>
<h1>Thermal Bridge</h1><p>Live thermal image · relative signal, not calibrated temperatures</p>
<img id="preview" width="640" height="480" alt="Thermal preview">
<p><button onclick="send({command:'calibrate'})">Calibrate shutter</button>
<select onchange="send({rotation:+this.value})"><option value="180">Rotate 180°</option value="0">Rotate 0°</option><option value="90">Rotate 90°</option><option value="270">Rotate 270°</option></select>
<select onchange="send({palette:this.value})"><option value="gray">White hot</option><option value="blackhot">Black hot</option><option value="iron">Iron</option></select></p>
<p>OBS: Media Source → disable Local File → <code>rtsp://127.0.0.1:18554/thermal</code></p>
<pre id="status"></pre><script>
async function send(body){let r=await fetch('/control',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});if(!r.ok)alert(await r.text())}
async function tick(){try{let s=await(await fetch('/status')).json();document.getElementById('status').textContent=JSON.stringify(s,null,2);document.getElementById('preview').src='/snapshot.png?t='+Date.now()}catch(e){}setTimeout(tick,200)}tick();
</script>"""


def server(state, port):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, status, data, kind):
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/":
                self.reply(200, PAGE.encode(), "text/html; charset=utf-8")
            elif path == "/status":
                self.reply(200, json.dumps(state.snapshot()).encode(), "application/json")
            elif path == "/snapshot.png":
                self.reply(200, png(state.video_frame()), "image/png")
            else:
                self.reply(404, b"Not found", "text/plain")

        def do_POST(self):
            if self.path != "/control":
                return self.reply(404, b"Not found", "text/plain")
            # Reject cross-origin browser commands. Server listens only on loopback.
            origin = self.headers.get("Origin")
            if origin and origin not in (f"http://127.0.0.1:{port}", f"http://localhost:{port}"):
                return self.reply(403, b"Origin rejected", "text/plain")
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 1024:
                    raise ValueError("Invalid body length")
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict) or set(body) - {"command", "rotation", "palette"}:
                    raise ValueError("Unknown control")
                if "rotation" in body and body["rotation"] not in (0, 90, 180, 270):
                    raise ValueError("Invalid rotation")
                if "palette" in body and body["palette"] not in ("gray", "blackhot", "iron"):
                    raise ValueError("Invalid palette")
                if "command" in body and body["command"] != "calibrate":
                    raise ValueError("Invalid command")
                if body.get("command") == "calibrate":
                    state.commands.put_nowait("calibrate")
                state.update(**{k: v for k, v in body.items() if k != "command"})
                self.reply(200, b'{"ok":true}', "application/json")
            except (ValueError, queue.Full):
                self.reply(400, b"Invalid control or command queue full", "text/plain")

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)
