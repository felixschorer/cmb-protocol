import asyncio

from connection import Connection, ProtocolServer
from packets import PacketType


class ClientConnection(Connection):
    async def handle_packet(self, data):
        print(PacketType.parse_packet(data))
        await self.send(data)
        self.close()


def main():
    loop = asyncio.get_event_loop()
    listen = loop.create_datagram_endpoint(lambda: ProtocolServer(ClientConnection),
                                           local_addr=('127.0.0.1', 9999))
    transport, protocol = loop.run_until_complete(listen)

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass

    transport.close()
    loop.close()


if __name__ == '__main__':
    main()
