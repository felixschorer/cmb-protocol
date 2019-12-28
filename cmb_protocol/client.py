import asyncio
import secrets

from packets import RequestResource, PacketType
from connection import Connection, ProtocolClient


class ServerConnection(Connection):
    async def init_connection(self):
        resource_request = RequestResource(overhead=0, resource_id=secrets.token_bytes(16), block_offset=0)
        await self.send(resource_request.to_bytes())

    async def handle_packet(self, data):
        print(PacketType.parse_packet(data))
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
