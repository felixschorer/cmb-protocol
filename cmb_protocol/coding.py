from sys import maxsize

from cmb_protocol.packets import Data
from raptorq import SourceBlockEncoder, SourceBlockDecoder


class Encoder:
    def __init__(self, block_id, data, symbol_size):
        self.block_id = block_id
        padded_symbol_length = len(data) % symbol_size
        if padded_symbol_length > 0:
            data += bytes(symbol_size - padded_symbol_length)
        self._enc = SourceBlockEncoder(0, symbol_size, data)

    @property
    def source_packets(self):
        return [Data(self.block_id, fec_data) for fec_data in self._enc.source_packets()]

    def repair_packets(self):
        for offset in range(0, maxsize, 10):
            for fec_data in self._enc.repair_packets(offset, 10):
                yield Data(self.block_id, fec_data)


class Decoder:
    def __init__(self, block_id, data_length, symbol_size):
        self.block_id = block_id
        self._data_length = data_length
        self._dec = SourceBlockDecoder(0, symbol_size, data_length)

    def decode(self, packets):
        assert all([self.block_id == packet.block_id for packet in packets])

        result = self._dec.decode([packet.fec_data for packet in packets])
        if result is None:
            return None
        return result[:self._data_length]
