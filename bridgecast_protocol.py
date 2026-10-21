"""Roland BRIDGE CAST ONE APP MIDI protocol and a bounded settings client.

The bank layout is based on a live BRIDGE CAST ONE RQ1 response. Some field
names come from BridgeMix's original BRIDGE CAST map and remain provisional on
ONE; callers only write fields explicitly listed in WRITABLE.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import re
import subprocess
import time
from dataclasses import dataclass

MODEL_PREFIX = bytes.fromhex("f0 41 10 00 00 00 00 11")
FADER_SECTION = 3
FADER_TYPE = 7
FADER_LENGTH = 0x6A

CHANNELS = ("Mic", "Aux", "Chat", "Game", "Music", "System", "SFX")
STREAM_FADERS = (0x00, 0x02, 0x04, 0x06, 0x08, 0x0A, 0x0C)
PERSONAL_FADERS = (0x10, 0x12, 0x14, 0x16, 0x18, 0x1A, 0x1C)
STREAM_MUTES = (0x20, 0x22, 0x24, 0x26, 0x28, 0x2A)
PERSONAL_MUTES = (0x30, 0x32, 0x34, 0x36, 0x38, 0x3A)
OUTPUT_LEVELS = {"Stream": 0x50, "Phones": 0x56, "Line Out": 0x58}
OUTPUT_MUTES = {"Stream": 0x60, "Phones": 0x66, "Line Out": 0x68}
LINE_OUT_MODES = {1: "Stream Mix", 2: "Phones Sync", 0: "Mic"}
WRITABLE = set(STREAM_FADERS + PERSONAL_FADERS + STREAM_MUTES + PERSONAL_MUTES)
WRITABLE.update(OUTPUT_MUTES.values())
WRITABLE.add(0x58)  # LINE OUT level; verified by one-step live write and restore
MIC_FX_LIMITS = {
    0x00: 1, 0x02: 15,   # Low cut enable / frequency
    0x10: 1, 0x12: 96,   # Noise suppression enable / threshold
    0x20: 1, 0x22: 9,    # De-esser enable / depth
    0x30: 1,             # Manual EQ enable
    0x70: 1, 0x72: 10, 0x74: 20, 0x76: 16, 0x78: 13, 0x7A: 30,
}
MIC_GAIN_ADDRESSES = (0x22, 0x24)


def checksum(data: bytes) -> int:
    return -sum(data) & 0x7F


def make_request(section: int, kind: int, address: int, size: int) -> bytes:
    if not all(0 <= value <= 0x7F for value in (section, kind, address, size)):
        raise ValueError("Roland address and size bytes must be 7-bit")
    body = bytes((0x7F, section, kind, address, 0, 0, 0, size))
    return MODEL_PREFIX + bytes((0x11,)) + body + bytes((checksum(body), 0xF7))


def make_write(section: int, kind: int, address: int, value: int) -> bytes:
    if not all(0 <= part <= 0x7F for part in (section, kind, address, value)):
        raise ValueError("Roland address and value bytes must be 7-bit")
    # The ONE replies with two-byte parameter slots. The first address byte
    # after type is the field offset; the second is zero (e.g. 30 00).
    body = bytes((0x7F, section, kind, address, 0, value))
    return MODEL_PREFIX + bytes((0x12,)) + body + bytes((checksum(body), 0xF7))


@dataclass(frozen=True)
class Reply:
    section: int
    kind: int
    address: int
    data: bytes


def parse_reply(frame: bytes) -> Reply | None:
    if len(frame) < 16 or not frame.startswith(MODEL_PREFIX + b"\x12") or frame[-1] != 0xF7:
        return None
    # The ONE's observed DT1 read replies carry raw data up to F7, without
    # the outbound DT1 checksum byte. The 106-byte bank reply is 121 bytes.
    body = frame[9:-1]
    if len(body) < 6 or body[0] != 0x7F:
        return None
    if body[4] != 0:
        return None
    return Reply(body[1], body[2], body[3], body[5:])


def find_app_port() -> str:
    result = subprocess.run(("amidi", "-l"), capture_output=True, text=True, check=True)
    for line in result.stdout.splitlines():
        if "BRIDGE CAST ONE MIDI 1" in line:
            match = re.search(r"\bhw:\d+,\d+,\d+\b", line)
            if match:
                return match.group()
    raise RuntimeError("BRIDGE CAST ONE APP MIDI port not found. Select PC mode and reconnect USB.")


class RawMidi:
    def __init__(self, port: str):
        path = ctypes.util.find_library("asound")
        if not path:
            raise RuntimeError("libasound is unavailable")
        self.lib = ctypes.CDLL(path)
        self.lib.snd_rawmidi_open.argtypes = (ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_void_p), ctypes.c_char_p, ctypes.c_int)
        self.lib.snd_rawmidi_open.restype = ctypes.c_int
        self.lib.snd_rawmidi_read.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t)
        self.lib.snd_rawmidi_read.restype = ctypes.c_ssize_t
        self.lib.snd_rawmidi_write.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t)
        self.lib.snd_rawmidi_write.restype = ctypes.c_ssize_t
        self.lib.snd_rawmidi_nonblock.argtypes = (ctypes.c_void_p, ctypes.c_int)
        self.lib.snd_rawmidi_nonblock.restype = ctypes.c_int
        self.lib.snd_rawmidi_close.argtypes = (ctypes.c_void_p,)
        self.lib.snd_strerror.argtypes = (ctypes.c_int,)
        self.lib.snd_strerror.restype = ctypes.c_char_p
        self.input = ctypes.c_void_p()
        self.output = ctypes.c_void_p()
        error = self.lib.snd_rawmidi_open(ctypes.byref(self.input), ctypes.byref(self.output), port.encode(), 0)
        if error < 0:
            raise OSError(self.lib.snd_strerror(error).decode())
        for handle in (self.input, self.output):
            error = self.lib.snd_rawmidi_nonblock(handle, 1)
            if error < 0:
                self.close()
                raise OSError(self.lib.snd_strerror(error).decode())
        self.pending = bytearray()

    def send(self, frame: bytes) -> None:
        buffer = ctypes.create_string_buffer(frame)
        count = self.lib.snd_rawmidi_write(self.output, buffer, len(frame))
        if count != len(frame):
            raise OSError(f"short MIDI write ({count}/{len(frame)})")

    def receive(self) -> list[bytes]:
        buffer = ctypes.create_string_buffer(8192)
        count = self.lib.snd_rawmidi_read(self.input, buffer, len(buffer))
        if count <= 0:
            return []
        self.pending.extend(buffer.raw[:count])
        frames = []
        while True:
            start = self.pending.find(0xF0)
            if start < 0:
                self.pending.clear()
                break
            if start:
                del self.pending[:start]
            end = self.pending.find(0xF7, 1)
            if end < 0:
                break
            frames.append(bytes(self.pending[:end + 1]))
            del self.pending[:end + 1]
        if len(self.pending) > 32768:
            self.pending.clear()
        return frames

    def close(self) -> None:
        for handle in (self.input, self.output):
            if handle.value:
                self.lib.snd_rawmidi_close(handle)
                handle.value = None


class BridgeCastOne:
    def __init__(self, port: str | None = None):
        self.port = port or find_app_port()
        self.midi = RawMidi(self.port)

    def close(self) -> None:
        self.midi.close()

    def read(self, section: int, kind: int, address: int, size: int, timeout: float = 1.5) -> bytes:
        # Device change notifications use the same DT1 address as RQ1 replies.
        # Clear any notification queued by an earlier write before requesting
        # a fresh value; otherwise readback can lag one operation behind.
        drain_until = time.monotonic() + 0.02
        while time.monotonic() < drain_until:
            self.midi.receive()
            time.sleep(0.002)
        self.midi.send(make_request(section, kind, address, size))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for frame in self.midi.receive():
                reply = parse_reply(frame)
                if reply and (reply.section, reply.kind, reply.address) == (section, kind, address) and len(reply.data) >= size:
                    return reply.data[:size]
            time.sleep(0.005)
        raise TimeoutError(f"No device reply for {section:02x}/{kind:02x}/{address:02x}; check PC mode and reconnect USB")

    def snapshot(self) -> tuple[bytes, int]:
        bank = self.read(FADER_SECTION, FADER_TYPE, 0, FADER_LENGTH)
        route = self.read(3, 0, 0x42, 2)[0]
        return bank, route

    def meter_snapshot(self) -> bytes:
        """Read the first 0x70 bytes of the live level bank.

        A request for the whole 0x7c bank is split into two MIDI replies at
        0x70. The first reply contains all of the input level pairs.
        """
        return self.read(1, 0x10, 0, 0x70, timeout=0.35)

    def set_fader(self, address: int, value: int) -> None:
        if address not in WRITABLE:
            raise ValueError("Field is not approved for writing on BRIDGE CAST ONE")
        if address in STREAM_MUTES + PERSONAL_MUTES + tuple(OUTPUT_MUTES.values()) and value not in (0, 1):
            raise ValueError("Mute values must be 0 or 1")
        self.midi.send(make_write(FADER_SECTION, FADER_TYPE, address, value))

    def set_line_out_mode(self, value: int) -> None:
        if value not in (1, 2):
            raise ValueError("Only Stream Mix and Phones Sync are enabled in this controller")
        self.midi.send(make_write(3, 0, 0x42, value))

    def mic_fx_snapshot(self) -> dict[int, int]:
        values = {}
        for address, size in ((0x00, 4), (0x10, 4), (0x20, 4), (0x30, 2), (0x70, 12)):
            block = self.read(3, 1, address, size)
            for offset in range(0, size, 2):
                values[address + offset] = block[offset]
        return values

    def set_mic_fx(self, address: int, value: int) -> None:
        maximum = MIC_FX_LIMITS.get(address)
        if maximum is None or not 0 <= value <= maximum:
            raise ValueError("Unsupported mic effect setting or value")
        self.midi.send(make_write(3, 1, address, value))

    def mic_input_snapshot(self) -> dict[int, int]:
        block = self.read(3, 0, 0x20, 8)
        return {0x20 + offset: block[offset] for offset in range(0, 8, 2)}

    def set_mic_gain(self, address: int, value: int) -> None:
        if address not in MIC_GAIN_ADDRESSES or not 0 <= value <= 25:
            raise ValueError("Unsupported mic gain setting or value")
        self.midi.send(make_write(3, 0, address, value))
