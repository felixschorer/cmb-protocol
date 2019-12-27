import struct
from .packet import Packet


class Data(Packet):
    __slots__ = 'blob_id', 'fec_data'

    _packet_type_ = 0xcb01

    __format = '!Q'
    __format_size = struct.calcsize(__format)

    def __init__(self, blob_id, fec_data):
        super().__init__()
        self.blob_id = blob_id
        self.fec_data = fec_data

    def _serialize_fields(self):
        return struct.pack(type(self).__format, self.blob_id) + self.fec_data

    @classmethod
    def _parse_fields(cls, packet_bytes):
        blob_id, = struct.unpack(cls.__format, packet_bytes[:cls.__format_size])
        fec_data = packet_bytes[cls.__format_size:]
        return Data(blob_id=blob_id, fec_data=fec_data)


class DataWithObjectTransmissionInfo(Data):
    __slots__ = 'transfer_length', 'maximum_transmission_unit'

    _packet_type_ = 0xcb02

    __format = '!QH'
    __format_size = struct.calcsize(__format)

    def __init__(self, blob_id, fec_data, transfer_length, maximum_transmission_unit):
        super().__init__(blob_id, fec_data)
        self.transfer_length = transfer_length
        self.maximum_transmission_unit = maximum_transmission_unit

    def _serialize_fields(self):
        return struct.pack(type(self).__format, self.transfer_length, self.maximum_transmission_unit) \
               + super()._serialize_fields()

    @classmethod
    def _parse_fields(cls, packet_bytes):
        transfer_length, maximum_transmission_unit = struct.unpack(cls.__format, packet_bytes[:cls.__format_size])
        packet_bytes = super()._parse_fields(packet_bytes[cls.__format_size:])
        return DataWithObjectTransmissionInfo(blob_id=packet_bytes.blob_id, fec_data=packet_bytes.fec_data,
                                              transfer_length=transfer_length,
                                              maximum_transmission_unit=maximum_transmission_unit)
