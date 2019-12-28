import asyncio

from packets import RequestResource, PacketType, DataWithMetadata, AckMetadata, Data
from connection import Connection, ProtocolClient


class ServerConnection(Connection):
    def __init__(self, transport):
        super().__init__(transport)
        self.transfer_started = False

    async def init_connection(self):
        resource_request = RequestResource(overhead=0, resource_id=bytes(16), block_offset=0)
        packet_bytes = resource_request.to_bytes()

        back_off = 1
        while True:
            await self.send(packet_bytes)
            await asyncio.sleep(back_off)
            if self.transfer_started:
                return
            back_off = min(30, back_off * 2)

    async def handle_packet(self, data):
        packet = PacketType.parse_packet(data)
        print(packet)

        if isinstance(packet, Data):
            self.transfer_started = True

        if isinstance(packet, DataWithMetadata):
            ack_metadata = AckMetadata()
            await self.send(ack_metadata.to_bytes())

        self.close()


def main():
    loop = asyncio.get_event_loop()
    connect = loop.create_datagram_endpoint(lambda: ProtocolClient(ServerConnection),
                                            remote_addr=('127.0.0.1', 9999))
    transport, protocol = loop.run_until_complete(connect)
    loop.run_until_complete(protocol.close_future)
    loop.close()


if __name__ == '__main__':
    main()
