import struct
from cmb_protocol.packets.packet import Packet


class NackBlock(Packet):
    __slots__ = 'received_packets', 'block_id'

    _packet_type_ = 0xcb05

    __format = '!HQ'

    def __init__(self, received_packets, block_id):
        super().__init__()
        self.received_packets = received_packets
        self.block_id = block_id

    def _serialize_fields(self):
        return struct.pack(self.__format, self.received_packets, self.block_id)

    @classmethod
    def _parse_fields(cls, packet_bytes):
        received_packets, block_id = struct.unpack(cls.__format, packet_bytes)
        return NackBlock(received_packets=received_packets, block_id=block_id)
