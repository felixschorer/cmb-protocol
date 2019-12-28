import struct

from cmb_protocol.packets.packet import Packet


class ResourceRequest(Packet):
    __slots__ = 'overhead', 'resource_id', 'block_offset'

    _packet_type_ = 0xcb00

    __format = '!B1s16sQ'

    def __init__(self, overhead, resource_id, block_offset):
        super().__init__()
        self.overhead = overhead
        self.resource_id = resource_id
        self.block_offset = block_offset

    def _serialize_fields(self):
        return struct.pack(self.__format,
                           self.overhead, bytes(1), self.resource_id, self.block_offset)

    @classmethod
    def _parse_fields(cls, packet_bytes):
        overhead, reserved, resource_id, block_offset = struct.unpack(cls.__format, packet_bytes)
        return ResourceRequest(overhead=overhead, resource_id=resource_id, block_offset=block_offset)
