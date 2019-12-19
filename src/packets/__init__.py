from enum import Enum, unique

from packets.packet import Packet
from packets.resource_request import ResourceRequest


@unique
class PacketType(Enum):
    """
    Enum for defining all possible packet types.
    """

    RESOURCE_REQUEST = ResourceRequest

    def __new__(cls, packet_cls):
        assert issubclass(packet_cls, Packet)
        obj = object.__new__(cls)
        obj._value_ = packet_cls.packet_type
        return obj

    def __init__(self, packet_cls):
        self._packet_cls = packet_cls

    def parse(self, data):
        return self._packet_cls.from_bytes(data)


def parse(data):
    packet_type = Packet.extract_packet_type(data)
    return PacketType(packet_type).parse(data)
