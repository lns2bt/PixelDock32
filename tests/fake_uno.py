"""Packet-level Uno substitute, not an AVR timing or electrical simulator."""

import struct


def packet(command: int, payload: bytes = b"") -> bytes:
    body = struct.pack("<2sBH", b"PD", command, len(payload)) + payload
    checksum = 0
    for byte in body:
        checksum ^= byte
    return body + bytes([checksum])


class FakeUno:
    def __init__(self):
        self.timeout = 0.02
        self.responses = bytearray()
        self.writes = []
        self.closed = False
        self.frame = None
        self.ack_mode = "ok"
        self.version = 2
        self.brightness = 64

    def write(self, data):
        self.writes.append(bytes(data))
        command = data[2]
        payload = data[5:-1]
        if packet(command, payload) != data:
            raise AssertionError("invalid host packet")
        if command == 4:
            self.responses.extend(packet(0x84, struct.pack("<BIIIIIIHHHBB", self.version, *([0] * 9), 0, self.brightness)))
        elif command == 2:
            self.brightness = payload[0]
        elif command == 3:
            self.responses.extend(packet(0x83, payload))
        elif command in (1, 5):
            self.frame = bytes(payload[2:] if command == 5 else payload)
            if command == 5 and self.ack_mode != "missing":
                sequence = struct.unpack("<H", payload[:2])[0]
                if self.ack_mode == "wrong_sequence":
                    sequence = (sequence + 1) & 0xFFFF
                reply = packet(0x85, struct.pack("<H", sequence))
                if self.ack_mode == "checksum":
                    reply = reply[:-1] + bytes([reply[-1] ^ 1])
                self.responses.extend(reply)
        return len(data)

    def read(self, count):
        data = bytes(self.responses[:count])
        del self.responses[:count]
        return data

    def reset_input_buffer(self):
        self.responses.clear()

    def reset_output_buffer(self):
        pass

    def close(self):
        self.closed = True
