# R-T160 protocol notes

Recovered through static analysis of Camera+ and validated against one physical R-T160. The repository contains independently written code and factual observations; it does not contain vendor APKs, libraries, or decompiled code.

## Observed hardware

| Field | Value |
|---|---|
| VID:PID | `04b4:000a` |
| Product | Thermal Camera |
| Model in frame metadata | `R-T160` |
| Firmware tested | `1.10.2025070715` |
| USB interface | 0, alternate setting 1, class ff/subclass f0 |
| Stream input | Bulk `82`, maximum packet 512 |
| Command output | Bulk `06`, maximum packet 512 |

Interface 1 has other endpoints but is unused. The Android attachment filter's `3474:6015` is not the identity observed on this camera. Do not assume all products using Camera+ share this protocol.

## Frames

Read into a 14,848-byte buffer (29 × 512). A complete logical transfer is 14,348 bytes. Unaligned receive sizes caused overflow/stalls on the tested Mac. Seven logical transfers form a 100,436-byte envelope.

- Byte 0: header length `0c`.
- Byte 6: `01` for image data; `02` for K-table data.
- First six image transfers: byte 1 is consistently `8c` or `8d`.
- Seventh: `8e` or `8f`, respectively.
- Strip each 12-byte header to obtain 100,352 payload bytes.
- Interpret as little-endian uint16, 256 columns × 196 rows.
- Extract rows 36–155 and columns 48–207: 160 × 120.
- Envelope offset 98,948: 16-byte firmware string.
- Envelope offset 98,980: 16-byte model string.

This describes transport layout, not a 256×196 physical detector. The adapter rejects models other than R-T160. Other header fields/sequence counters are not fully decoded, so framing checks cannot prove lossless acquisition.

## Commands and calibration

Send two bytes, most significant byte first, on OUT 06:

| Bytes | Observed purpose |
|---|---|
| `80 81` | Request K calibration table |
| `80 00` | Trigger normal shutter calibration |

For K, concatenate 192 chunks of 512 bytes at transfer offset 12. Interpret as a 256×192 uint16 table, apply the image crop, and scale by 1/16384.

The current relative signal is `(scene - shutter_reference) * K / 16384`. This is not a complete implementation of vendor radiometry or temperature conversion. Shutter reference collection currently uses measured timing and a signal-excursion check; neither is a substitute for a decoded shutter-state flag.

## Optional development capture format

Each record contains little-endian float64 seconds, little-endian uint32 payload length, then transfer bytes. The optional regression test expects the development recording whose shutter command was at 3.004 seconds. This is a fixture-specific test, not a general capture/replay API. Do not commit recordings of private scenes.
