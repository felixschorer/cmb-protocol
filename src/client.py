import asyncio
import secrets
from asyncio import DatagramProtocol
from functools import partial

from packets import ResourceRequest


class ClientProtocol(DatagramProtocol):
    def __init__(self, loop):
        self.loop = loop

    def connection_made(self, transport):
        resource_request = ResourceRequest(connection_id=secrets.token_bytes(16),
                                           resource_id=secrets.token_bytes(16),
                                           offset=0)
        transport.sendto(resource_request.to_bytes())

        transport.close()

    def connection_lost(self, _):
        self.loop.stop()


def main():
    loop = asyncio.get_event_loop()
    client = partial(ClientProtocol, loop)

    connect = loop.create_datagram_endpoint(client, remote_addr=('127.0.0.1', 9999))
    transport, protocol = loop.run_until_complete(connect)

    loop.run_forever()
    transport.close()
    loop.close()


if __name__ == '__main__':
    main()
