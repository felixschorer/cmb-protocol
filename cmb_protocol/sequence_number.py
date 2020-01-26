from cmb_protocol.helpers import unpack_uint24, pack_uint24


class SequenceNumber:
    __slots__ = 'value',

    MAX_VALUE = 2**24

    def __init__(self, value):
        self.value = value % self.MAX_VALUE

    @staticmethod
    def from_bytes(data):
        return SequenceNumber(unpack_uint24(data))

    def to_bytes(self):
        return pack_uint24(int(self.value))

    def __add__(self, other):
        if isinstance(other, int):
            return SequenceNumber(self.value + other)
        else:
            return NotImplemented

    def __radd__(self, other):
        return self + other

    def __sub__(self, other):
        if isinstance(other, int):
            return SequenceNumber(self.value - other)
        elif isinstance(other, SequenceNumber):
            return (self.value - other.value) % self.MAX_VALUE
        else:
            return NotImplemented

    def __eq__(self, other):
        return isinstance(other, SequenceNumber) and self.value == other.value

    def __lt__(self, other):  # self < other (self older than other)
        if isinstance(other, SequenceNumber):
            # Due to wrap around at exactly 2**24, there is no way of knowing which sequence number is older.
            # However, we can assume the order which produces the smallest difference to be correct.
            # This produces correct results for two sequence numbers which are apart less than 2**23.
            # In our case we won't be comparing sequence numbers with each other which are apart by more than a thousand.
            return self - other > other - self
        else:
            return NotImplemented

    def __gt__(self, other):  # self > other (self newer than other)
        if isinstance(other, SequenceNumber):
            # Due to wrap around at exactly 2**24, there is no way of knowing which sequence number is older.
            # However, we can assume the order which produces the smallest difference to be correct.
            # This produces correct results for two sequence numbers which are apart less than 2**23.
            # In our case we won't be comparing sequence numbers with each other which are apart by more than a thousand.
            return self - other < other - self
        else:
            return NotImplemented

    def __le__(self, other):
        return self == other or self < other

    def __ge__(self, other):
        return self == other or self > other

    def __repr__(self):
        return 'SequenceNumber(value={})'.format(self.value)
