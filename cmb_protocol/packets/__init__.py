from enum import Enum, unique

from .packet import Packet
from .resource_request import ResourceRequest
from .data import Data, DataWithTransmissionMetadata


@unique
class PacketType(Enum):
    """
    Enum for defining all possible packet types.
    """

    RESOURCE_REQUEST = ResourceRequest
    DATA_WITH_TRANSMISSION_METADATA = DataWithTransmissionMetadata

    def __new__(cls, packet_cls):
        assert issubclass(packet_cls, Packet)
        obj = object.__new__(cls)
        obj._value_ = packet_cls.packet_type
        return obj

    def __init__(self, packet_cls):
        self.packet_cls = packet_cls

    @classmethod
    def parse_packet(cls, packet_bytes):
        packet_type = Packet.extract_packet_type(packet_bytes)
        return cls(packet_type).packet_cls.from_bytes(packet_bytes)
