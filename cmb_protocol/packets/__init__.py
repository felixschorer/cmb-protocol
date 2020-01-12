from enum import Enum, unique
from cmb_protocol.packets.packet import Packet
from cmb_protocol.packets.request_resource import RequestResource
from cmb_protocol.packets.data import Data, DataWithMetadata
from cmb_protocol.packets.ack import AckBlock, AckMetadata, AckOppositeRange
from cmb_protocol.packets.nack import NackBlock


@unique
class PacketType(Enum):
    """
    Enum for defining all possible packet types.
    """

    REQUEST_RESOURCE = RequestResource
    DATA = Data
    DATA_WITH_METADATA = DataWithMetadata
    ACK_BLOCK = AckBlock
    ACK_METADATA = AckMetadata
    NACK_BLOCK = NackBlock
    ACK_OPPOSITE_RANGE = AckOppositeRange

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
