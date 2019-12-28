import struct

from cmb_protocol.packets.packet import Packet


class AckBlock(Packet):
    _packet_type_ = 0xcb03

    def __init__(self):
        super().__init__()

    def _serialize_fields(self):
        return b''

    @classmethod
    def _parse_fields(cls, packet_bytes):
        return AckBlock()


class AckTransmissionMetadata(Packet):
    _packet_type_ = 0xcb04

    def __init__(self):
        super().__init__()

    def _serialize_fields(self):
        return b''

    @classmethod
    def _parse_fields(cls, packet_bytes):
        return AckTransmissionMetadata()
