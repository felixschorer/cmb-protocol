import trio
from cmb_protocol.helpers import unpack_uint24, pack_uint24


class Timestamp:
    """
    Timestamp which can be represented in 24 bits, measured in seconds with millisecond precision.
    It will wrap around after approx 4:40h.

    All timestamps are relative to the clock of the current trio context. Since trio uses randomized clocks,
    timestamps must not be compared with timestamps created in a different trio context.
    """

    MAX_VALUE = 2**24 / 1000  # 24 bit, in seconds, millisecond accuracy

    def __init__(self, value):
        self.value = value % self.MAX_VALUE

    @staticmethod
    def now():
        return Timestamp(trio.current_time())

    @staticmethod
    def from_bytes(data):
        return Timestamp(unpack_uint24(data) / 1000)

    def to_bytes(self):
        return pack_uint24(int(self.value * 1000))

    def __add__(self, other):
        if isinstance(other, int) or isinstance(other, float):
            return Timestamp(self.value + other)
        else:
            return NotImplemented

    def __radd__(self, other):
        return self + other

    def __sub__(self, other):
        if isinstance(other, int) or isinstance(other, float):
            return Timestamp(self.value - other)
        elif isinstance(other, Timestamp):
            return (self.value - other.value) % self.MAX_VALUE
        else:
            return NotImplemented

    def __eq__(self, other):
        return isinstance(other, Timestamp) and self.value == other.value

    def __lt__(self, other):  # self < other (self older than other)
        if isinstance(other, Timestamp):
            # Due to wrap around at approx. 4:40h, there is no way of knowing which timestamp is older.
            # However, we can assume that the order which produces the smallest duration to be correct.
            # This works in our case as we won't be comparing timestamps with each other
            # which are apart by more than a few seconds.
            return self - other > other - self
        else:
            return NotImplemented

    def __gt__(self, other):  # self > other (self newer than other)
        if isinstance(other, Timestamp):
            # Due to wrap around at approx. 4:40h, there is no way of knowing which timestamp is older.
            # However, we can assume that the order which produces the smallest duration to be correct.
            # This works in our case as we won't be comparing timestamps with each other
            # which are apart by more than a few seconds.
            return self - other < other - self
        else:
            return NotImplemented

    def __le__(self, other):
        return self == other or self < other

    def __ge__(self, other):
        return self == other or self > other
