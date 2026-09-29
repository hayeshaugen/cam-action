"""Only this module knows libusb. No camera commands or pixel interpretation."""

import ctypes as C
import ctypes.util
import os
from typing import Protocol


class Transport(Protocol):
    def read(self, endpoint: int, size: int, timeout_ms: int) -> bytes: ...
    def write(self, endpoint: int, data: bytes, timeout_ms: int) -> None: ...
    def close(self) -> None: ...


class UsbError(OSError):
    pass


class LibusbTransport:
    def __init__(self, vid, pid, interface, alternate, library=None):
        path = library or os.environ.get("LIBUSB_LIBRARY") or ctypes.util.find_library("usb-1.0")
        if not path and os.path.exists("/opt/homebrew/lib/libusb-1.0.dylib"):
            path = "/opt/homebrew/lib/libusb-1.0.dylib"
        if not path:
            raise UsbError("libusb not found; set LIBUSB_LIBRARY to its full path")
        self.lib = C.CDLL(path)
        signatures = {
            "libusb_init": ([C.POINTER(C.c_void_p)], C.c_int),
            "libusb_exit": ([C.c_void_p], None),
            "libusb_open_device_with_vid_pid": ([C.c_void_p, C.c_uint16, C.c_uint16], C.c_void_p),
            "libusb_close": ([C.c_void_p], None),
            "libusb_claim_interface": ([C.c_void_p, C.c_int], C.c_int),
            "libusb_release_interface": ([C.c_void_p, C.c_int], C.c_int),
            "libusb_set_interface_alt_setting": ([C.c_void_p, C.c_int, C.c_int], C.c_int),
            "libusb_bulk_transfer": (
                [C.c_void_p, C.c_ubyte, C.c_void_p, C.c_int, C.POINTER(C.c_int), C.c_uint],
                C.c_int,
            ),
            "libusb_clear_halt": ([C.c_void_p, C.c_ubyte], C.c_int),
            "libusb_error_name": ([C.c_int], C.c_char_p),
        }
        for name, (args, ret) in signatures.items():
            fn = getattr(self.lib, name)
            fn.argtypes = args
            fn.restype = ret
        self.ctx = C.c_void_p()
        self.handle = None
        self.claimed = False
        self.interface = interface
        self._check(self.lib.libusb_init(C.byref(self.ctx)))
        try:
            self.handle = self.lib.libusb_open_device_with_vid_pid(self.ctx, vid, pid)
            if not self.handle:
                raise UsbError(
                    f"Cannot open camera {vid:04x}:{pid:04x}; disconnected, busy, or permission denied"
                )
            self._check(self.lib.libusb_claim_interface(self.handle, interface))
            self.claimed = True
            self._check(
                self.lib.libusb_set_interface_alt_setting(self.handle, interface, alternate)
            )
        except Exception:
            self.close()
            raise

    def _check(self, result):
        if result < 0:
            raise UsbError(self.lib.libusb_error_name(result).decode())

    def read(self, endpoint, size, timeout_ms):
        buf = C.create_string_buffer(size)
        n = C.c_int()
        result = self.lib.libusb_bulk_transfer(
            self.handle, endpoint, buf, size, C.byref(n), timeout_ms
        )
        if result == -7:
            return b""  # Incomplete timeout data is discarded: protocol resynchronizes.
        if result in (-8, -9):
            self._check(self.lib.libusb_clear_halt(self.handle, endpoint))
            raise UsbError("Input overflow/stall cleared; reconnecting")
        self._check(result)
        return buf.raw[: n.value]

    def write(self, endpoint, data, timeout_ms):
        buf = C.create_string_buffer(data)
        n = C.c_int()
        self._check(
            self.lib.libusb_bulk_transfer(
                self.handle, endpoint, buf, len(data), C.byref(n), timeout_ms
            )
        )
        if n.value != len(data):
            raise UsbError("Short command write")

    def close(self):
        if self.handle:
            if self.claimed:
                self.lib.libusb_set_interface_alt_setting(self.handle, self.interface, 0)
                self.lib.libusb_release_interface(self.handle, self.interface)
            self.lib.libusb_close(self.handle)
            self.handle = None
        if self.ctx:
            self.lib.libusb_exit(self.ctx)
            self.ctx = C.c_void_p()
