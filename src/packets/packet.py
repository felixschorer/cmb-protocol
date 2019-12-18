import struct
from abc import ABC, abstractmethod, ABCMeta


class _PacketMeta(ABCMeta):
    """
    Metaclass for reading the _packet_type_ field of packet class definitions.
    """

    _PACKET_TYPE_FORMAT = '!H'
    PACKET_TYPE_SIZE = struct.calcsize(_PACKET_TYPE_FORMAT)

    def __init__(cls, name, bases, dct):
        if ABC not in bases:
            cls.packet_type = struct.pack(cls._PACKET_TYPE_FORMAT, dct['_packet_type_'])
        else:
            cls.packet_type = None
        super(_PacketMeta, cls).__init__(name, bases, dct)


class Packet(ABC, metaclass=_PacketMeta):
    """
    Abstract base class for all packet definitions.
    _packet_type_ has to be set on the class, e.g. `_packet_type_ = 0xbeef`.
    """

    def to_bytes(self):
        return type(self).packet_type + self._serialize_fields()

    @classmethod
    def from_bytes(cls, data):
        assert cls.extract_packet_type(data) == cls.packet_type
        return cls._parse_fields(data[cls.PACKET_TYPE_SIZE:])

    @classmethod
    def extract_packet_type(cls, data):
        return data[:cls.PACKET_TYPE_SIZE]

    @abstractmethod
    def _serialize_fields(self):
        """
        Abstract method for serializing the fields of a packet to bytes (excluding the packet type).
        """
        pass

    @classmethod
    @abstractmethod
    def _parse_fields(cls, data):
        """
        Abstract method for parsing the fields of a packet from bytes (excluding the packet type).
        """
        pass
