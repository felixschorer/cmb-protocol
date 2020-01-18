import struct
from abc import ABCMeta, ABC, abstractmethod
from enum import unique, Enum, IntFlag, IntEnum


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


class AckBlock(Packet):
    __slots__ = 'block_id'

    _packet_type_ = 0xcb03

    __format = '!2sQ'

    def __init__(self, block_id):
        super().__init__()
        self.block_id = block_id

    def _serialize_fields(self):
        return struct.pack(self.__format, bytes(2), self.block_id)

    @classmethod
    def _parse_fields(cls, packet_bytes):
        reserved, block_id, = struct.unpack(cls.__format, packet_bytes)
        return AckBlock(block_id=block_id)


class AckOppositeRange(Packet):
    __slots__ = 'block_id'

    _packet_type_ = 0xcb06

    __format = '!2sQ'

    def __init__(self, block_id):
        super().__init__()
        self.block_id = block_id

    def _serialize_fields(self):
        return struct.pack(self.__format, bytes(2), self.block_id)

    @classmethod
    def _parse_fields(cls, packet_bytes):
        reserved, block_id, = struct.unpack(cls.__format, packet_bytes)
        return AckOppositeRange(block_id=block_id)


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


class NackBlock(Packet):
    __slots__ = 'received_packets', 'block_id'

    _packet_type_ = 0xcb05

    __format = '!HQ'

    def __init__(self, received_packets, block_id):
        super().__init__()
        self.received_packets = received_packets
        self.block_id = block_id

    def _serialize_fields(self):
        return struct.pack(self.__format, self.received_packets, self.block_id)

    @classmethod
    def _parse_fields(cls, packet_bytes):
        received_packets, block_id = struct.unpack(cls.__format, packet_bytes)
        return NackBlock(received_packets=received_packets, block_id=block_id)


@unique
class RequestResourceFlags(IntFlag):
    NONE = 0
    REVERSE = 1


class RequestResource(Packet):
    __slots__ = 'flags', 'resource_id', 'block_offset'

    _packet_type_ = 0xcb00

    __format = '!B1s16sQQ'

    def __init__(self, flags, resource_id, block_offset):
        super().__init__()
        assert isinstance(flags, RequestResourceFlags)
        self.flags = flags
        self.resource_id = resource_id
        self.block_offset = block_offset

    def _serialize_fields(self):
        resource_hash, resource_length = self.resource_id
        return struct.pack(self.__format,
                           self.flags, bytes(1), resource_hash, resource_length, self.block_offset)

    @classmethod
    def _parse_fields(cls, packet_bytes):
        flags, reserved, resource_hash, resource_length, block_offset = struct.unpack(cls.__format, packet_bytes)
        return RequestResource(flags=RequestResourceFlags(flags),
                               resource_id=(resource_hash, resource_length),
                               block_offset=block_offset)


@unique
class ErrorCode(IntEnum):
    RESOURCE_NOT_FOUND = 0


class Error(Packet):
    __slots__ = 'error_code'

    _packet_type_ = 0xcb07

    __format = '!H'

    def __init__(self, error_code):
        super().__init__()
        assert isinstance(error_code, ErrorCode)
        self.error_code = error_code

    def _serialize_fields(self):
        return struct.pack(self.__format, self.error_code)

    @classmethod
    def _parse_fields(cls, packet_bytes):
        error_code, = struct.unpack(cls.__format, packet_bytes)
        return Error(error_code=ErrorCode(error_code))


@unique
class PacketType(Enum):
    """
    Enum for defining all possible packet types.
    """

    REQUEST_RESOURCE = RequestResource
    DATA = Data
    ACK_BLOCK = AckBlock
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
        try:
            packet_type = Packet.extract_packet_type(packet_bytes)
            return cls(packet_type).packet_cls.from_bytes(packet_bytes)
        except Exception as exc:
            raise ValueError('Failed to parse bytes into packet') from exc
