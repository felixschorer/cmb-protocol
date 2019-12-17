import struct
from packets.packet import Packet


class ResourceRequest(Packet):
    _packet_type_ = 0xcb00

    _format = '!2s16s16sQ'

    def __init__(self, connection_id, resource_id, offset):
        self.connection_id = connection_id
        self.resource_id = resource_id
        self.offset = offset

    def _serialize_fields(self):
        return struct.pack(type(self)._format, bytes(2), self.connection_id, self.resource_id, self.offset)

    @classmethod
    def _parse_fields(cls, data):
        reserved, connection_id, resource_id, offset = struct.unpack(cls._format, data)
        return ResourceRequest(connection_id=connection_id, resource_id=resource_id, offset=offset)
