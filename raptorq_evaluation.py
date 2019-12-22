import random
import os
from raptorq import Encoder, Decoder


def main():
    data = os.urandom(100 * 512)
    print(len(data))

    encoder = Encoder.with_defaults(data, 512)
    packets = encoder.get_encoded_packets(50)

    print(sum(len(packet) for packet in packets))

    random.shuffle(packets)
    packets = packets[50:]

    decoder = Decoder.with_defaults(len(data), 512)
    for index, packet in enumerate(packets):
        decoded_data = decoder.decode(packet)
        if decoded_data is not None and data == decoded_data:
            print('data successfully decoded')
            break


if __name__ == '__main__':
    main()
