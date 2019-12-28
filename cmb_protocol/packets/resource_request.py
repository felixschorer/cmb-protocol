import struct

from cmb_protocol.packets.packet import Packet


class ResourceRequest(Packet):
    __slots__ = 'overhead', 'resource_id', 'blob_offset'

    _packet_type_ = 0xcb00

    __format = '!B1s16sQ'

    def __init__(self, overhead, resource_id, blob_offset):
        super().__init__()
        self.overhead = overhead
        self.resource_id = resource_id
        self.blob_offset = blob_offset

    def _serialize_fields(self):
        return struct.pack(self.__format,
                           self.overhead, bytes(1), self.resource_id, self.blob_offset)

    @classmethod
    def _parse_fields(cls, packet_bytes):
        overhead, reserved, connection_id, resource_id, blob_offset = struct.unpack(cls.__format, packet_bytes)
        return ResourceRequest(overhead=overhead, resource_id=resource_id, blob_offset=blob_offset)
