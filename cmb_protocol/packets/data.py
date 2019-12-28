import struct

from cmb_protocol.packets.packet import Packet


class Data(Packet):
    __slots__ = 'block_id', 'fec_data'

    _packet_type_ = 0xcb01

    __format = '!2sQ'
    __format_size = struct.calcsize(__format)

    def __init__(self, block_id, fec_data):
        super().__init__()
        self.block_id = block_id
        self.fec_data = fec_data

    def _serialize_fields(self):
        return struct.pack(self.__format, bytes(2), self.block_id) + self.fec_data

    @classmethod
    def _parse_fields(cls, packet_bytes):
        reserved, block_id = struct.unpack(cls.__format, packet_bytes[:cls.__format_size])
        fec_data = packet_bytes[cls.__format_size:]
        return Data(block_id=block_id, fec_data=fec_data)


class DataWithMetadata(Data):
    __slots__ = 'transfer_length'

    _packet_type_ = 0xcb02

    __format = '!Q'
    __format_size = struct.calcsize(__format)

    def __init__(self, block_id, fec_data, transfer_length):
        super().__init__(block_id, fec_data)
        self.transfer_length = transfer_length

    def _serialize_fields(self):
        return super()._serialize_fields() + struct.pack(self.__format, self.transfer_length)

    @classmethod
    def _parse_fields(cls, packet_bytes):
        transfer_length, block_size = struct.unpack(cls.__format, packet_bytes[-cls.__format_size:])
        data = super()._parse_fields(packet_bytes[:-cls.__format_size])
        return DataWithMetadata(block_id=data.block_id, fec_data=data.fec_data,
                                transfer_length=transfer_length)
