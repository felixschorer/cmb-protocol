import struct
from enum import IntFlag
from packets.packet import Packet


class RequestResourceFlags(IntFlag):
    NONE = 0
    REVERSE = 1


class RequestResource(Packet):
    __slots__ = 'flags', 'resource_id', 'block_offset'

    _packet_type_ = 0xcb00

    __format = '!B1s16sQ'

    def __init__(self, flags, resource_id, block_offset):
        super().__init__()
        assert isinstance(flags, RequestResourceFlags)
        self.flags = flags
        self.resource_id = resource_id
        self.block_offset = block_offset

    def _serialize_fields(self):
        return struct.pack(self.__format,
                           self.flags, bytes(1), self.resource_id, self.block_offset)

    @classmethod
    def _parse_fields(cls, packet_bytes):
        flags, reserved, resource_id, block_offset = struct.unpack(cls.__format, packet_bytes)
        return RequestResource(flags=RequestResourceFlags(flags), resource_id=resource_id, block_offset=block_offset)
