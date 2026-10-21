import unittest

from bridgecast_protocol import BridgeCastOne, make_request, make_write, parse_reply


class ProtocolTests(unittest.TestCase):
    def test_personal_mic_mute_matches_verified_wire_command(self):
        self.assertEqual(make_write(3, 7, 0x30, 0).hex(" "),
                         "f0 41 10 00 00 00 00 11 12 7f 03 07 30 00 00 47 f7")

    def test_bank_request_matches_live_probe(self):
        self.assertEqual(make_request(3, 7, 0, 0x6A),
                         bytes.fromhex("f0 41 10 00 00 00 00 11 11 7f 03 07 00 00 00 00 6a 0d f7"))

    def test_parse_one_route_reply_without_outbound_checksum(self):
        frame = bytes.fromhex("f0 41 10 00 00 00 00 11 12 7f 03 00 42 00 01 00 f7")
        reply = parse_reply(frame)
        self.assertEqual((reply.section, reply.kind, reply.address, reply.data),
                         (3, 0, 0x42, b"\x01\x00"))

    def test_read_bank_from_split_midi_frames(self):
        bank = bytearray(0x6A)
        bank[0x20] = 0
        bank[0x30] = 1
        bank[0x58] = 100
        payload = bytes.fromhex("f0 41 10 00 00 00 00 11 12 7f 03 07 00 00") + bank + b"\xf7"

        class FakeMidi:
            def __init__(self):
                self.sent = []
                self.stale_reads = 0

            def send(self, frame):
                self.sent.append(frame)

            def receive(self):
                if not self.sent:
                    self.stale_reads += 1
                    return [b"\xf0\xf7"]
                return [payload]

        client = BridgeCastOne.__new__(BridgeCastOne)
        client.midi = FakeMidi()
        self.assertEqual(client.read(3, 7, 0, 0x6A), bytes(bank))
        self.assertEqual(len(client.midi.sent), 1)
        self.assertGreater(client.midi.stale_reads, 0)

    def test_reject_unverified_phones_level_write(self):
        client = BridgeCastOne.__new__(BridgeCastOne)
        with self.assertRaises(ValueError):
            client.set_fader(0x56, 127)

    def test_reject_out_of_range_mic_effect(self):
        client = BridgeCastOne.__new__(BridgeCastOne)
        with self.assertRaises(ValueError):
            client.set_mic_fx(0x76, 17)


if __name__ == "__main__":
    unittest.main()
