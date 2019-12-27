import struct
from .packet import Packet


class ResourceRequest(Packet):
    __slots__ = 'connection_id', 'resource_id', 'blob_offset'

    _packet_type_ = 0xcb00

    __format = '!2s16s16sQ'

    def __init__(self, connection_id, resource_id, blob_offset):
        super().__init__()
        self.connection_id = connection_id
        self.resource_id = resource_id
        self.blob_offset = blob_offset

    def _serialize_fields(self):
        return struct.pack(type(self).__format, bytes(2), self.connection_id, self.resource_id, self.blob_offset)

    @classmethod
    def _parse_fields(cls, packet_bytes):
        reserved, connection_id, resource_id, blob_offset = struct.unpack(cls.__format, packet_bytes)
        return ResourceRequest(connection_id=connection_id, resource_id=resource_id, blob_offset=blob_offset)
