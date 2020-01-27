import math
from sys import maxsize
from raptorq import SourceBlockEncoder, SourceBlockDecoder

RAPTORQ_HEADER_SIZE = 4


class Encoder:
    def __init__(self, data, symbol_size):
        self.minimum_packet_count = math.ceil(len(data) / symbol_size)
        padded_symbol_length = len(data) % symbol_size
        if padded_symbol_length > 0:
            data += bytes(symbol_size - padded_symbol_length)
        self._enc = SourceBlockEncoder(0, symbol_size, data)

    def source_packets(self):
        return self._enc.source_packets()

    def repair_packets(self):
        for offset in range(0, maxsize, 10):
            for packet in self._enc.repair_packets(offset, 10):
                yield packet


class Decoder:
    def __init__(self, data_length, symbol_size):
        self.minimum_packet_count = math.ceil(data_length / symbol_size)
        self._data_length = data_length
        self._dec = SourceBlockDecoder(0, symbol_size, data_length)

    def decode(self, packets):
        result = self._dec.decode(packets)
        if result is None:
            return None
        return result[:self._data_length]
