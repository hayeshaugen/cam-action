# Operations

This document covers running the working R-T160 adapter and connecting its
standard RTSP output to other software.

## Local run

Install Python 3.10+, NumPy, libusb 1.0, FFmpeg with H.264 encoding, and
[MediaMTX](https://mediamtx.org/docs/kickoff/install). Then run from the
repository root:

```sh
python -m venv .venv
# Activate .venv using your shell's normal command.
python -m pip install -e .
python run.py --mediamtx /path/to/mediamtx --ffmpeg /path/to/ffmpeg
```

The launcher starts both processes and stops both on Ctrl-C. It refuses to
start when either default port is already occupied.

- Preview and controls: <http://127.0.0.1:8787>
- RTSP: `rtsp://127.0.0.1:18554/thermal`
- Status JSON: <http://127.0.0.1:8787/status>

To run just the service against an existing RTSP server, use
`cam-action --rtsp URL`. If libusb is not found automatically, set
`LIBUSB_LIBRARY` to its full path. On macOS Homebrew's library is usually
`/opt/homebrew/lib/libusb-1.0.dylib`.

## Controls

The browser page exposes the safe controls. The same API can be scripted:

```sh
curl http://127.0.0.1:8787/status
curl -X POST -H 'Content-Type: application/json' \
  -d '{"command":"calibrate"}' http://127.0.0.1:8787/control
curl -X POST -H 'Content-Type: application/json' \
  -d '{"rotation":180,"palette":"iron"}' http://127.0.0.1:8787/control
```

Commands are queued for the acquisition thread. The HTTP handler never opens
the camera, so USB access stays serialized. The service requests the K table
after connection and repeats shutter calibration every 90 seconds. Disable
periodic calibration with `--calibration-interval 0`.

Reference frames are collected 0.30–0.75 seconds after the shutter command;
normal rendering resumes after 1.30 seconds. These timings are provisional
measurements for this unit, not decoded shutter-state flags. The service
requires enough frames and a measurable signal excursion before accepting a
reference. It reports a calibration failure rather than silently presenting an
unreferenced image.

## OBS and YouTube

In OBS, add a Media Source, disable Local File, and enter:

```text
rtsp://127.0.0.1:18554/thermal
```

Choose RTSP over TCP when available. OBS can record the scene or publish it to
YouTube using its YouTube/RTMPS settings. Cam Action does not need a public
port for YouTube because OBS makes the outbound connection.

## Frigate

For Frigate on the same host, use the local URL. For a container or another
machine, expose MediaMTX deliberately on an address that the client can reach;
`127.0.0.1` inside a container means the container itself.

After configuring MediaMTX authentication and firewall rules, a Frigate input
can look like:

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

This supplies video. It does not imply that visible-light detection models
will work well on this low-resolution thermal image. Temperature alarms need a
separate radiometry layer once temperature conversion is validated.

## Platform notes

### macOS ARM64

The R-T160 USB and RTSP path was tested here. No vendor executable or native
vendor library is required.

### Windows 10 and 11

RTSP is the first target and does not depend on Windows 11's virtual-camera
API. Install matching Python, FFmpeg, MediaMTX, and libusb builds. The camera
interface will typically need WinUSB access; verify the device in Device
Manager before changing any driver binding because that can affect the vendor
application. Windows has not yet had a hardware run in this project.

### Linux

Install libusb, FFmpeg, and MediaMTX. Add a udev rule for USB device
`04b4:000a` rather than running the service as root. Container USB permissions
are a separate deployment concern.

### Android and iOS

Android needs a USB-host transport and app packaging. iOS/iPadOS is low
priority because this proprietary device is not UVC; neither integration is
implemented yet.

## Security

The default RTSP and HTTP listeners bind to loopback and have no authentication
because they are local development services. Keep the control API local. If
you expose RTSP on a LAN, add MediaMTX authentication, restrict the firewall,
and never forward the control port or RTSP port directly to the public
Internet.
