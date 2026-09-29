import os
import struct
import unittest
from pathlib import Path

import numpy as np

from thermal_bridge.camera import RT160, SensorFrame
from thermal_bridge.processing import Calibration, Renderer


class Fake:
    def write(self, *a):
        pass

    def close(self):
        pass


class ProtocolTests(unittest.TestCase):
    def test_recorded_hardware_and_shutter(self):
        fixture_name = os.environ.get("THERMAL_BRIDGE_TEST_CAPTURE")
        if not fixture_name:
            self.skipTest("Set THERMAL_BRIDGE_TEST_CAPTURE for optional hardware recording")
        fixture = Path(fixture_name)
        data = fixture.read_bytes()
        cam = RT160(Fake())
        cam.request_calibration_table()
        off = 0
        cal = None
        frames = 0
        rendered = 0
        triggered = False
        while off < len(data):
            t, n = struct.unpack_from("<dI", data, off)
            off += 12
            event = cam.accept(data[off : off + n])
            off += n
            if isinstance(event, np.ndarray):
                cal = Calibration(event)
            elif isinstance(event, SensorFrame) and cal:
                frames += 1
                if not triggered and t >= 3.004:
                    cal.begin(3.004)
                    triggered = True
                corrected = cal.apply(event.pixels, t)
                if 3.004 <= t < 4.304:
                    self.assertIsNone(corrected)
                if corrected is not None:
                    rendered += 1
        self.assertGreater(frames, 150)
        self.assertGreater(rendered, 50)
        self.assertEqual(cal.state, "streaming")
        self.assertEqual(cal.reference.shape, (120, 160))

    def test_reject_malformed_and_wrong_marker(self):
        cam = RT160(Fake())

        def packet(marker):
            b = bytearray(14348)
            b[0] = 12
            b[1] = marker
            b[6] = 1
            return bytes(b)

        for _ in range(6):
            cam.accept(packet(140))
        self.assertIsNone(cam.accept(packet(143)))
        self.assertEqual(cam.parts, [])
        for _ in range(6):
            cam.accept(packet(140))
        cam.accept(b"bad")
        self.assertIsNone(cam.accept(packet(142)))
        self.assertEqual(cam.frames, 0)

    def test_missing_shutter_does_not_calibrate(self):
        cal = Calibration(np.ones((120, 160)))
        cal.last_mean = 6000
        cal.begin(0)
        for t in [0.31, 0.4, 0.5, 0.6, 1.4]:
            self.assertIsNone(cal.apply(np.full((120, 160), 6000.0), t))
        self.assertIsNone(cal.reference)
        self.assertTrue(cal.state.startswith("calibration failed"))

    def test_render_fixed_canvas(self):
        r = Renderer()
        a = np.arange(160 * 120).reshape(120, 160)
        for rotation in [0, 90, 180, 270]:
            for palette in ["gray", "blackhot", "iron"]:
                out = r.render(a, rotation, palette)
                self.assertEqual(out.shape, (480, 640, 3))
                self.assertEqual(out.dtype, np.uint8)


class SyntheticHardwareTests(unittest.TestCase):
    @staticmethod
    def image_packets(model="R-T160"):
        payload = np.arange(256 * 196, dtype="<u2").tobytes()
        parts = []
        for i in range(7):
            header = bytearray(12)
            header[0] = 12
            header[1] = 140 if i < 6 else 142
            header[6] = 1
            parts.append(header + payload[i * 14336 : (i + 1) * 14336])
        frame = bytearray(b"".join(parts))
        frame[98980:98996] = model.encode().ljust(16, b"\0")
        frame[98948:98964] = b"test-fw".ljust(16, b"\0")
        return [bytes(frame[i * 14348 : (i + 1) * 14348]) for i in range(7)]

    def test_decodes_known_geometry_and_metadata(self):
        cam = RT160(Fake())
        frame = None
        for p in self.image_packets():
            frame = cam.accept(p)
        self.assertIsInstance(frame, SensorFrame)
        self.assertEqual(frame.model, "R-T160")
        self.assertEqual(frame.firmware, "test-fw")
        self.assertEqual(frame.pixels.shape, (120, 160))
        self.assertEqual(frame.pixels[0, 0], 36 * 256 + 48)
        self.assertEqual(frame.pixels[-1, -1], 155 * 256 + 207)

    def test_unknown_model_rejected(self):
        cam = RT160(Fake())
        with self.assertRaisesRegex(ValueError, "Unsupported model"):
            for p in self.image_packets("R-T256"):
                cam.accept(p)

    def test_timeout_drops_partial_frame(self):
        cam = RT160(Fake())
        packets = self.image_packets()
        for p in packets[:6]:
            cam.accept(p)
        cam.accept(b"")
        self.assertIsNone(cam.accept(packets[-1]))
        self.assertEqual(cam.frames, 0)
        for p in packets:
            result = cam.accept(p)
        self.assertIsInstance(result, SensorFrame)

    def test_gain_requires_complete_table(self):
        cam = RT160(Fake())
        cam.request_calibration_table()
        header = bytearray(12)
        header[0] = 12
        header[6] = 2
        p = bytes(header) + np.full(256, 16384, dtype="<u2").tobytes()
        for _ in range(191):
            self.assertIsNone(cam.accept(p))
        gain = cam.accept(p)
        np.testing.assert_array_equal(gain, np.ones((120, 160)))
        self.assertIsNone(cam.accept(p))

    def test_successful_shutter_and_incomplete_reference(self):
        cal = Calibration(np.full((120, 160), 1.5))
        cal.last_mean = 6000
        cal.begin(0)
        for t in [0.31, 0.4, 0.5, 0.6]:
            self.assertIsNone(cal.apply(np.full((120, 160), 6500.0), t))
        result = cal.apply(np.full((120, 160), 6100.0), 1.4)
        np.testing.assert_array_equal(result, np.full((120, 160), -600.0))
        cal.begin(2)
        self.assertIsNone(cal.apply(np.full((120, 160), 6500.0), 2.4))
        self.assertIsNone(cal.apply(np.full((120, 160), 6100.0), 3.4))
        self.assertIn("insufficient frames", cal.state)


if __name__ == "__main__":
    unittest.main()
