import trio
from cmb_protocol.helpers import unpack_uint24, pack_uint24


class Timestamp:
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
            raise NotImplemented('only supported for int and float')

    def __radd__(self, other):
        return self + other

    def __sub__(self, other):
        if isinstance(other, int) or isinstance(other, float):
            return Timestamp(self.value - other)
        elif isinstance(other, Timestamp):
            return (self.value - other.value) % self.MAX_VALUE
        else:
            raise NotImplemented('only supported for int and float or Timestamp')

    def __eq__(self, other):
        return isinstance(other, Timestamp) and self.value == other.value

    def __lt__(self, other):  # self < other (self older than other)
        if isinstance(other, Timestamp):
            return self - other > other - self  # consider shorter duration to be more likely
        else:
            raise NotImplemented('only supported for Timestamp')

    def __gt__(self, other):  # self > other (self newer than other)
        if isinstance(other, Timestamp):
            return self - other < other - self  # consider shorter duration to be more likely
        else:
            raise NotImplemented('only supported for Timestamp')

    def __le__(self, other):
        return self == other or self < other

    def __ge__(self, other):
        return self == other or self > other
