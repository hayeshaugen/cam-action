# Validation record

## Initial hardware work (2026-09-28)

- macOS ARM64, R-T160, USB 04b4:000a, firmware 1.10.2025070715.
- Retrieved all 192 K-table chunks.
- Captured and decoded real scene/shutter frames without executing vendor libraries.
- User verified a recognizable thermal face capture and subsequently reported the streaming workflow working.
- Independently decoded H.264 from RTSP with FFmpeg; 640×480 output, 25 fps clock, approximately 19–22 fresh frames/second.
- Exercised startup, manual, and scheduled shutter calibration, palettes, and restart through the launcher.

## Repository preparation (2026-09-29)

- Nine unittest cases passed locally with the optional private recording enabled.
- Ordinary no-hardware run: eight passed, one optional recording test skipped.
- Ruff lint and formatting checks passed.
- Editable installation and CLI help succeeded in an isolated environment.
- Source distribution and wheel built; contents inspected to exclude recordings, vendor binaries and runtime files.
- GitHub Actions matrix prepared for Python 3.10/3.13 on macOS, Linux and Windows. It has not run until the repository is pushed.

## Not yet validated

Physical disconnect/reconnect recovery, extended unattended use, Windows/Linux USB access, Android integration, absolute temperatures, or full native vendor processing. Tests of framing do not prove that no USB frames are lost.
