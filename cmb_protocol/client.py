import asyncio
import secrets
from asyncio import DatagramProtocol, Future

from cmb_protocol.packets import RequestResource


class ClientProtocol(DatagramProtocol):
    def __init__(self):
        self._complete_future = Future()

    def connection_made(self, transport):
        resource_request = RequestResource(overhead=0, resource_id=secrets.token_bytes(16), block_offset=0)
        transport.sendto(resource_request.to_bytes())
        asyncio.get_event_loop().call_soon(transport.close)

    def connection_lost(self, _):
        self._complete_future.set_result(None)

    def __await__(self):
        return self._complete_future.__await__()


def main():
    loop = asyncio.get_event_loop()

    connect = loop.create_datagram_endpoint(ClientProtocol, remote_addr=('127.0.0.1', 9999))
    transport, protocol = loop.run_until_complete(connect)

    loop.run_until_complete(protocol)
    loop.close()


if __name__ == '__main__':
    main()
