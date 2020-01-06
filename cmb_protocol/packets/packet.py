import struct
from abc import ABC, abstractmethod, ABCMeta


class _PacketMeta(ABCMeta):
    """
    Metaclass for reading the _packet_type_ field of packet class definitions.
    """

    _PACKET_TYPE_KEY = '_packet_type_'
    _PACKET_TYPE_FORMAT = '!H'
    PACKET_TYPE_SIZE = struct.calcsize(_PACKET_TYPE_FORMAT)

    def __init__(cls, name, bases, dct):
        super(_PacketMeta, cls).__init__(name, bases, dct)

        if ABC in bases:
            cls.packet_type = None
        else:
            try:
                cls.packet_type = struct.pack(cls._PACKET_TYPE_FORMAT, dct[cls._PACKET_TYPE_KEY])
            except (KeyError, struct.error) as e:
                msg = '{}.{} must have a valid class member {}'.format(cls.__module__, cls.__name__,
                                                                       cls._PACKET_TYPE_KEY)
                raise AssertionError(msg) from e


class Packet(ABC, metaclass=_PacketMeta):
    """
    Abstract base class for all packet definitions.
    _packet_type_ has to be set on the class, e.g. `_packet_type_ = 0xbeef`.
    """

    def to_bytes(self):
        return type(self).packet_type + self._serialize_fields()

    @classmethod
    def from_bytes(cls, packet_bytes):
        assert cls.extract_packet_type(packet_bytes) == cls.packet_type
        return cls._parse_fields(packet_bytes[cls.PACKET_TYPE_SIZE:])

    @classmethod
    def extract_packet_type(cls, packet_bytes):
        return packet_bytes[:cls.PACKET_TYPE_SIZE]

    @abstractmethod
    def _serialize_fields(self):
        """
        Abstract method for serializing the fields of a packet to bytes (excluding the packet type).
        """
        pass

    @classmethod
    @abstractmethod
    def _parse_fields(cls, packet_bytes):
        """
        Abstract method for parsing the fields of a packet from bytes (excluding the packet type).
        """
        pass
