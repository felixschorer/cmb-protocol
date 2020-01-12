import struct
from cmb_protocol.packets.packet import Packet


class AckBlock(Packet):
    __slots__ = 'block_id'

    _packet_type_ = 0xcb03

    __format = '!2sQ'

    def __init__(self, block_id):
        super().__init__()
        self.block_id = block_id

    def _serialize_fields(self):
        return struct.pack(self.__format, bytes(2), self.block_id)

    @classmethod
    def _parse_fields(cls, packet_bytes):
        reserved, block_id, = struct.unpack(cls.__format, packet_bytes)
        return AckBlock(block_id=block_id)


class AckMetadata(Packet):
    _packet_type_ = 0xcb04

    def __init__(self):
        super().__init__()

    def _serialize_fields(self):
        return bytes(2)

    @classmethod
    def _parse_fields(cls, packet_bytes):
        return AckMetadata()


class AckOppositeRange(Packet):
    __slots__ = 'block_id'

    _packet_type_ = 0xcb06

    __format = '!2sQ'

    def __init__(self, block_id):
        super().__init__()
        self.block_id = block_id

    def _serialize_fields(self):
        return struct.pack(self.__format, bytes(2), self.block_id)

    @classmethod
    def _parse_fields(cls, packet_bytes):
        reserved, block_id, = struct.unpack(cls.__format, packet_bytes)
        return AckOppositeRange(block_id=block_id)
