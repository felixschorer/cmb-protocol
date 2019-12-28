import asyncio
from asyncio import DatagramProtocol

from cmb_protocol.packets import PacketType


class ServerProtocol(DatagramProtocol):
    def datagram_received(self, data, addr):
        packet = PacketType.parse_packet(data)
        print(packet)


def main():
    loop = asyncio.get_event_loop()
    listen = loop.create_datagram_endpoint(ServerProtocol, local_addr=('127.0.0.1', 9999))
    transport, protocol = loop.run_until_complete(listen)

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass

    transport.close()
    loop.close()


if __name__ == '__main__':
    main()
