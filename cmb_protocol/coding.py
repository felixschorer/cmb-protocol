# import os
# import random
# from raptorq import SourceBlockEncoder, SourceBlockDecoder
#
# symbol_size = 512
# data = os.urandom(symbol_size * 100 + 1)
# padding = bytes(symbol_size - len(data) % symbol_size) if len(data) % symbol_size > 0 else bytes()
# padded_data = data + padding
#
# enc = SourceBlockEncoder(0, symbol_size, padded_data)
#
# packets = enc.source_packets() + enc.repair_packets(0, 50)
#
# random.shuffle(packets)
#
# dec = SourceBlockDecoder(0, symbol_size, len(padded_data))
#
# result = None
# for packet in packets[50:]:
#     result = dec.decode(packet)
#     if result:
#         break
#
# assert padded_data == result
