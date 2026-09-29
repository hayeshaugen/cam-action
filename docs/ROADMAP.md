# Roadmap

## Working on macOS ARM64

- R-T160 bulk USB acquisition and model validation.
- K-table retrieval and commanded shutter-reference correction.
- Relative thermal preview, rotation, and three display palettes.
- Local control API and H.264 RTSP publishing through FFmpeg/MediaMTX.
- User-confirmed OBS/YouTube workflow.

## Next: dependable acquisition

- Move to asynchronous USB reads / bounded acquisition queues to reduce frame loss.
- Decode sequence and shutter-state metadata instead of relying on elapsed-time windows.
- Test physical unplug/replug, endpoint recovery, multiple cameras, and long-duration drift.
- Preserve settings and make calibration failures more useful in the UI.
- Add a deliberate recording/replay format with timestamps, calibration metadata and privacy-aware fixtures.

## Platform validation

- Windows **10 and 11**: validate WinUSB binding, libusb packaging and process cleanup on real hardware.
- Linux: udev permissions, headless deployments, Frigate/container integration.
- Android: implement a USB host adapter and share the protocol specification/test vectors; native app packaging remains separate work.
- iOS/iPadOS: low priority; investigate permitted hardware access before committing to an implementation.

## Thermal measurements

- Independently recover and validate temperature conversion.
- Bad-pixel correction, drift compensation and robust reference selection.
- Separate radiometric data and alarm events from rendered video.
- Validate against references and document accuracy limits before presenting Celsius values.

## Additional outputs and cameras

- Native macOS/Windows/Linux virtual-camera adapters.
- Additional camera adapters using the same processing/output boundaries.
- Windows 10 is in scope for RTSP; choosing a native virtual-camera API is a separate decision.

This roadmap is intended direction, not a claim that these features are implemented.
