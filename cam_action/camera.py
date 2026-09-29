"""Camera-specific adapter for the REVASRI R-T160 bulk USB protocol.

The rest of Cam Action sees only :class:`SensorFrame` objects and calibration
tables. USB endpoint numbers, packet markers, command bytes, and crop geometry
stay here so another camera can be added without changing processing or output.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, TypeAlias

import numpy as np

from .transport import Transport

CalibrationTable: TypeAlias = np.ndarray


@dataclass(frozen=True)
class SensorFrame:
    """One decoded sensor image and the metadata carried by its envelope."""

    pixels: np.ndarray
    model: str
    firmware: str


CameraEvent: TypeAlias = SensorFrame | CalibrationTable | None


class Camera(Protocol):
    """Interface consumed by the acquisition service."""

    shutter_timing: tuple[float, float, float]
    bad_packets: int

    def request_calibration_table(self) -> None: ...
    def trigger_shutter(self) -> None: ...
    def next_event(self) -> CameraEvent: ...
    def close(self) -> None: ...


class RT160:
    """Adapter for the R-T160 device observed during protocol recovery."""

    VENDOR_ID = 0x04B4
    PRODUCT_ID = 0x000A
    USB = {"vid": VENDOR_ID, "pid": PRODUCT_ID, "interface": 0, "alternate": 1}

    INPUT_ENDPOINT = 0x82
    OUTPUT_ENDPOINT = 0x06
    RECEIVE_BUFFER_SIZE = 14_848  # 29 USB high-speed packets of 512 bytes.
    TRANSFER_SIZE = 14_348
    FRAME_TRANSFER_COUNT = 7
    FRAME_HEADER_SIZE = 12
    FRAME_PAYLOAD_SIZE = TRANSFER_SIZE - FRAME_HEADER_SIZE

    IMAGE_COLUMNS = 256
    IMAGE_ROWS = 196
    CROP_LEFT = 48
    CROP_TOP = 36
    OUTPUT_WIDTH = 160
    OUTPUT_HEIGHT = 120

    FIRMWARE_OFFSET = 98_948
    MODEL_OFFSET = 98_980
    METADATA_LENGTH = 16

    CALIBRATION_PACKET_COUNT = 192
    CALIBRATION_CHUNK_SIZE = 512
    CALIBRATION_SCALE = 16_384.0

    IMAGE_MARKER_STARTS = (0x8C, 0x8D)
    IMAGE_MARKER_ENDS = (0x8E, 0x8F)
    IMAGE_PACKET_TYPE = 1
    CALIBRATION_PACKET_TYPE = 2

    # Start/end of reference collection and time at which normal frames resume.
    # These are observed timing values, not a decoded device state flag.
    shutter_timing = (0.30, 0.75, 1.30)

    def __init__(self, transport: Transport):
        self.transport = transport
        self._frame_parts: list[bytes] = []
        self._calibration_parts: list[bytes] | None = None
        self.bad_packets = 0
        self.frames = 0

    def request_calibration_table(self) -> None:
        """Ask the device to send its 192-part K table."""

        self._calibration_parts = []
        self._frame_parts.clear()
        self.transport.write(self.OUTPUT_ENDPOINT, b"\x80\x81", 1000)

    def trigger_shutter(self) -> None:
        """Move the calibration shutter and start a reference sequence."""

        self._frame_parts.clear()
        self.transport.write(self.OUTPUT_ENDPOINT, b"\x80\x00", 1000)

    def next_event(self) -> CameraEvent:
        """Read and decode the next USB transfer."""

        packet = self.transport.read(self.INPUT_ENDPOINT, self.RECEIVE_BUFFER_SIZE, 500)
        return self.accept(packet)

    @property
    def pending_transfers(self) -> int:
        """Number of image transfers currently held for frame assembly."""

        return len(self._frame_parts)

    def accept(self, packet: bytes) -> CameraEvent:
        """Consume one transfer, returning a completed table or image when ready."""

        if not packet:
            self._frame_parts.clear()
            return None
        if len(packet) < self.FRAME_HEADER_SIZE or packet[0] != self.FRAME_HEADER_SIZE:
            self._discard_packet()
            return None

        if packet[6] == self.CALIBRATION_PACKET_TYPE:
            return self._accept_calibration(packet)
        if len(packet) != self.TRANSFER_SIZE or packet[6] != self.IMAGE_PACKET_TYPE:
            self._discard_packet()
            return None
        return self._accept_image(packet)

    def _accept_calibration(self, packet: bytes) -> CalibrationTable | None:
        self._frame_parts.clear()
        if (
            self._calibration_parts is None
            or len(packet) < self.FRAME_HEADER_SIZE + self.CALIBRATION_CHUNK_SIZE
        ):
            return None
        self._calibration_parts.append(
            packet[self.FRAME_HEADER_SIZE : self.FRAME_HEADER_SIZE + self.CALIBRATION_CHUNK_SIZE]
        )
        if len(self._calibration_parts) != self.CALIBRATION_PACKET_COUNT:
            return None

        raw = b"".join(self._calibration_parts)
        self._calibration_parts = None
        table = np.frombuffer(raw, dtype="<u2").reshape(192, 256)
        gain = table[
            self.CROP_TOP : self.CROP_TOP + self.OUTPUT_HEIGHT,
            self.CROP_LEFT : self.CROP_LEFT + self.OUTPUT_WIDTH,
        ].astype(np.float32)
        gain /= self.CALIBRATION_SCALE
        if not np.all((gain > 0.25) & (gain < 4.0)):
            raise ValueError("camera returned an implausible R-T160 calibration table")
        return gain

    def _accept_image(self, packet: bytes) -> SensorFrame | None:
        marker = packet[1]
        if marker in self.IMAGE_MARKER_STARTS:
            if self._frame_parts and (
                len(self._frame_parts) >= self.FRAME_TRANSFER_COUNT - 1
                or self._frame_parts[0][1] != marker
            ):
                self._discard_packet()
            self._frame_parts.append(packet)
            return None

        if (
            marker not in self.IMAGE_MARKER_ENDS
            or len(self._frame_parts) != self.FRAME_TRANSFER_COUNT - 1
            or marker != self._frame_parts[0][1] + 2
        ):
            self._discard_packet()
            return None

        self._frame_parts.append(packet)
        envelope = b"".join(self._frame_parts)
        payload = b"".join(part[self.FRAME_HEADER_SIZE :] for part in self._frame_parts)
        self._frame_parts.clear()

        model = self._metadata(envelope, self.MODEL_OFFSET)
        firmware = self._metadata(envelope, self.FIRMWARE_OFFSET)
        if model != "R-T160":
            raise ValueError(f"unsupported camera model {model!r}; refusing guessed geometry")

        self.frames += 1
        pixels = np.frombuffer(payload, dtype="<u2").reshape(self.IMAGE_ROWS, self.IMAGE_COLUMNS)
        pixels = pixels[
            self.CROP_TOP : self.CROP_TOP + self.OUTPUT_HEIGHT,
            self.CROP_LEFT : self.CROP_LEFT + self.OUTPUT_WIDTH,
        ].astype(np.float32)
        return SensorFrame(pixels=pixels, model=model, firmware=firmware)

    def _metadata(self, envelope: bytes, offset: int) -> str:
        return (
            envelope[offset : offset + self.METADATA_LENGTH]
            .split(b"\0", 1)[0]
            .decode("ascii", errors="replace")
            .strip()
        )

    def _discard_packet(self) -> None:
        self._frame_parts.clear()
        self.bad_packets += 1

    def close(self) -> None:
        self.transport.close()
