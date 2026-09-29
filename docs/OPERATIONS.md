# Thermal Bridge

A working macOS prototype that reads the REVASRI R-T160 directly and publishes thermal video over RTSP. Includes a local live preview and controls for shutter calibration, rotation, white-hot, black-hot, and iron palettes. No vendor library executes in this application.

**Preview:** http://127.0.0.1:8787
**RTSP:** rtsp://127.0.0.1:18554/thermal

Images show relative corrected sensor signal, **not calibrated Celsius temperatures**. The 160×120 input is enlarged to a 640×480 output without invented detail. A 25 fps output clock repeats the latest image when no new camera frame is available. In the first live test about 19–22 fresh frames/second were decoded; lossless capture is not yet achieved.

## Start on this Mac

In this directory:

```sh
/opt/homebrew/bin/python3 run.py --ffmpeg /opt/homebrew/bin/ffmpeg
```

The original development workspace has a checksum-verified official MediaMTX v1.21.1 macOS ARM64 binary in ignored `bin/`, with its license. Fresh clones must install MediaMTX separately. The launcher starts both MediaMTX and the bridge and stops both on Ctrl-C. It refuses to start a duplicate on occupied ports. Run it in a terminal for an ordinary session; no login item or system service is installed.

Dependencies: Python 3.10+, numpy, libusb 1.0, FFmpeg with libx264, and MediaMTX. Use a virtual environment if installing Python packages:

```sh
python -m venv .venv
# macOS/Linux: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python run.py --mediamtx /path/to/mediamtx --ffmpeg /path/to/ffmpeg
```

Any existing local development binary in `bin/` is only for ARM64 macOS. Obtain the matching official release for other systems. Set `LIBUSB_LIBRARY` to the complete library path if automatic discovery fails. RTSP/server ports are localhost-only by default. The control page's stream text assumes the default RTSP URL.

## OBS

Add a **Media Source**, uncheck **Local File**, and enter:

```text
rtsp://127.0.0.1:18554/thermal
```

Use RTSP-over-TCP if the client exposes that choice. If automatic transport selection fails, set the FFmpeg option `rtsp_transport=tcp`. No virtual webcam driver is required. The RTSP output was independently verified with FFprobe and decoded to an image with FFmpeg; OBS UI playback has not yet been verified.

## Frigate

For Frigate on the same host without container isolation, the local URL can be used directly. A different machine or a container needs an address it can reach; `127.0.0.1` inside a container refers to the container itself.

To deliberately expose the video on your trusted LAN, change `rtspAddress` in `mediamtx.yml` to the host's LAN IP plus `:18554`, and restart. To also retain loopback publishing, use `:18554` (all interfaces) and configure MediaMTX authentication/firewall rules for the intended clients. The supplied config has no RTSP authentication because it is bound to loopback. Keep the control server on loopback; it does not need to be exposed to Frigate.

Example Frigate input after enabling LAN access:

```yaml
cameras:
  thermal:
    ffmpeg:
      inputs:
        - path: rtsp://CAMERA_HOST_IP:18554/thermal
          input_args: preset-rtsp-restream
          roles:
            - detect
    detect:
      width: 640
      height: 480
      fps: 5
```

This provides video ingestion. It does not establish that an ordinary visible-light object detector will perform well on this low-resolution thermal image. Absolute temperature alarms will need a separate data channel once radiometry is validated.

## Architecture and hardware adapter boundary

| Module | Responsibility |
|---|---|
| `transport.py` | libusb resource ownership, interface selection, bulk reads/writes; no camera command meanings or image geometry |
| `camera.py` | R-T160 adapter: VID/PID, endpoints, two-byte commands, frame assembly, model validation, K-table decoding, image crop and shutter timing policy |
| `processing.py` | Relative per-pixel correction, shutter reference validation, display scaling/palettes/rotation; no USB access |
| `service.py` | Single acquisition owner, reconnect loop, calibration scheduling, latest-frame state and queued commands |
| `output.py` | FFmpeg H.264 publishing; independent of USB and camera protocol |
| `control.py` | Local HTTP preview and validated control API; no direct hardware operations |
| `run.py` | Process lifecycle for bridge plus the external MediaMTX server |

The `Transport` and `Camera` protocols are the extension seams. A new model gets its own camera adapter; a new platform can implement transport or output adapters. Calibration is sensor-domain processing; absolute thermometry will be an additional module, not a video-output concern. The first prototype uses Python/numpy; Android can reuse the specification and tests, but its Android USB transport/native integration is not implemented here.

## Controls and calibration behavior

```sh
curl http://127.0.0.1:8787/status
curl -X POST -H 'Content-Type: application/json' \
  -d '{"command":"calibrate"}' http://127.0.0.1:8787/control
curl -X POST -H 'Content-Type: application/json' \
  -d '{"rotation":180,"palette":"iron"}' http://127.0.0.1:8787/control
```

The bridge requests the device's K table after connecting, then commands shutter calibration. It repeats calibration every 90 seconds (set `--calibration-interval 0` to disable periodic requests). Commands run on the acquisition thread, so the control UI never competes with it for USB access.

Reference frames are collected 0.30–0.75 seconds after the shutter command; scene rendering resumes after 1.30 seconds. These are provisional timings observed on this unit, not decoded firmware shutter-state flags. The reference is accepted only if enough frames arrive and the mean signal shows an excursion and return. Scenes close to shutter temperature can fail this conservative check; the status page reports that and allows a manual retry. Motion during calibration can still affect this heuristic.

During normal calibration the output holds the last valid image briefly. After two seconds without a valid image it outputs black, rather than silently freezing indefinitely. Status reports calibration/disconnection separately. Reconnect invalidates calibration and obtains a fresh reference. Native bad-pixel removal, drift compensation and absolute temperature conversion are not fully reproduced.

## Platform status

- **macOS ARM64:** live hardware and RTSP tested here.
- **Windows 10/11:** intended service targets; not hardware-tested. Use a compatible Python/FFmpeg/MediaMTX build and matching libusb DLL architecture. libusb typically needs the camera interface bound to WinUSB; verify the exact camera interface before changing any driver binding. This may affect the vendor app. No Windows drivers were changed here.
- **Linux:** intended target; not hardware-tested. Install libusb/FFmpeg/MediaMTX and arrange USB permissions (udev) for 04b4:000a. Container USB access is a deployment concern separate from RTSP delivery.
- **Android:** future host app/transport integration; not implemented.
- **iOS:** low-priority investigation; not implemented.
- **Native virtual cameras:** future output adapters. RTSP does not depend on Windows 11's newer virtual-camera API, so Windows 10 remains in scope.

## Validation

```sh
python -m unittest discover -s tests -v
ffprobe -v error -rtsp_transport tcp -show_entries stream=codec_name,width,height,r_frame_rate \
  -of json rtsp://127.0.0.1:18554/thermal
```

Tests exercise a recorded hardware session through the new adapter and calibration pipeline, malformed frame resynchronization, rejection of missing shutter transitions, and all rendering orientations/palettes. Set `THERMAL_BRIDGE_TEST_CAPTURE` to a local development fixture to enable the optional hardware-recording test. Private fixtures are not distributed. Live testing confirmed K-table acquisition, startup/manual/periodic calibration, continuous RTSP decoding and palette control. Reconnect logic is implemented but physical unplug/replug and Windows/Linux behavior still require validation.

Sources: [MediaMTX installation](https://mediamtx.org/docs/kickoff/install), [configuration](https://mediamtx.org/docs/references/configuration-file), [Windows virtual camera API requirements](https://learn.microsoft.com/en-us/windows/win32/api/mfvirtualcamera/nf-mfvirtualcamera-mfcreatevirtualcamera).
