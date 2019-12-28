import struct

from cmb_protocol.packets.packet import Packet


class NackBlock(Packet):
    _packet_type_ = 0xcb05

    def __init__(self):
        super().__init__()

    def _serialize_fields(self):
        return b''

    @classmethod
    def _parse_fields(cls, packet_bytes):
        return NackBlock()
