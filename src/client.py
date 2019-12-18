import asyncio
import secrets
from asyncio import DatagramProtocol, Future

from packets import ResourceRequest


class ClientProtocol(DatagramProtocol):
    def __init__(self):
        self.complete_future = Future()

    def connection_made(self, transport):
        resource_request = ResourceRequest(connection_id=secrets.token_bytes(16),
                                           resource_id=secrets.token_bytes(16),
                                           offset=0)
        transport.sendto(resource_request.to_bytes())
        transport.close()

    def connection_lost(self, _):
        self.complete_future.done()


def main():
    loop = asyncio.get_event_loop()

    connect = loop.create_datagram_endpoint(ClientProtocol, remote_addr=('127.0.0.1', 9999))
    transport, protocol = loop.run_until_complete(connect)

    loop.run_until_complete(protocol.complete_future)
    loop.close()


if __name__ == '__main__':
    main()
