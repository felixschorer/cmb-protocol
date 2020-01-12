import struct
from packets.packet import Packet


class NackBlock(Packet):
    __slots__ = 'lost_packets', 'block_id'

    _packet_type_ = 0xcb05

    __format = '!HQ'

    def __init__(self, lost_packets, block_id):
        super().__init__()
        self.lost_packets = lost_packets
        self.block_id = block_id

    def _serialize_fields(self):
        return struct.pack(self.__format, self.lost_packets, self.block_id)

    @classmethod
    def _parse_fields(cls, packet_bytes):
        lost_packets, block_id = struct.unpack(cls.__format, packet_bytes)
        return NackBlock(lost_packets=lost_packets,block_id=block_id)
