import asyncio

from connection import Connection, ProtocolServer
from packets import PacketType, RequestResource, DataWithMetadata


class ClientConnection(Connection):
    async def handle_packet(self, data):
        packet = PacketType.parse_packet(data)
        print(packet)

        if isinstance(packet, RequestResource):
            data_with_metadata = DataWithMetadata(block_id=0, fec_data=bytes(10), resource_size=10)
            await self.send(data_with_metadata.to_bytes())

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
