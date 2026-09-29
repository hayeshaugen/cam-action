# Architecture

Cam Action is organized around a one-way flow of data and a single owner for
the physical camera:

```text
Transport -> Camera adapter -> Acquisition -> Processing -> Output
     ^             ^               ^             ^           ^
  libusb      device facts      USB owner      arrays    RTSP/other
```

The control server sits beside the flow. It changes display options or puts a
command in the acquisition queue; it never reaches around the queue to call a
USB method.

## Boundaries

### Transport

`cam_action.transport` owns the native libusb library, USB handle, interface,
alternate setting, and bulk transfers. It reports bytes and transport errors.
It does not know what `80 81` means or how many pixels are in a frame.

The `Transport` protocol makes this boundary testable. A fake transport can
feed a camera adapter recorded packets without loading libusb.

### Camera adapter

`cam_action.camera` is the R-T160 implementation. It contains the device IDs,
endpoints, command bytes, transfer sizes, marker validation, metadata offsets,
calibration-table layout, and crop geometry. It converts complete protocol
events into a `SensorFrame` or a calibration table.

Unsupported model metadata raises an error rather than silently applying the
R-T160 geometry to another device. A future device should implement the same
`Camera` protocol in a separate module.

### Acquisition owner

`cam_action.service.Acquisition` is the only component allowed to operate the
camera during a live run. It obtains the K table, schedules shutter reference
updates, handles reconnects, and forwards corrected images to the current
renderer. Keeping ownership here prevents the browser, output thread, and USB
transport from racing each other.

`State` contains the latest rendered frame, status fields, display options, and
a bounded command queue. Frames older than two seconds become black output so
a disconnected camera cannot look live forever.

### Processing

`cam_action.processing` accepts NumPy arrays and has no USB or network imports.
`Calibration` collects shutter-reference frames and applies the currently
recovered relative correction. `Renderer` performs contrast scaling, palette
mapping, orientation, and fixed-size output. It intentionally does not claim
to convert the signal to Celsius; absolute thermometry belongs in a future
validated module.

### Outputs and controls

`cam_action.output` feeds RGB frames to FFmpeg and reconnects its publisher if
the process exits. MediaMTX is a separate RTSP server started by `run.py`.

`cam_action.control` serves the local page, status JSON, and a small validated
POST API. It only accepts the known rotation, palette, and shutter command
values. The default loopback binding is a security boundary, not an
authentication system; LAN exposure requires explicit MediaMTX and firewall
configuration.

## Extension strategy

New cameras should add:

1. A hardware adapter implementing the camera protocol.
2. Protocol fixtures and malformed-input tests.
3. A short protocol note describing evidence and untested assumptions.

New delivery mechanisms should add an output adapter. RTSP, native virtual
cameras, recordings, and analysis consumers should not change USB framing or
camera commands. Platform-specific USB access can implement `Transport` while
leaving the camera and processing layers unchanged.
