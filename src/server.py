import asyncio
from asyncio import DatagramProtocol

from packets import parse, ResourceRequest


class ServerProtocol(DatagramProtocol):
    def datagram_received(self, data, addr):
        packet = parse(data)

        print(packet)

        if isinstance(packet, ResourceRequest):
            print('Connection ID', packet.connection_id)
            print('Resource ID', packet.resource_id)


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
