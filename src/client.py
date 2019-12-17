import asyncio
import sys
from asyncio import DatagramProtocol
from functools import partial

from packets.hello import Hello, Greeting, Subject


class ClientProtocol(DatagramProtocol):
    def __init__(self, loop):
        self.loop = loop

    def connection_made(self, transport):
        hello = Hello(greeting=Greeting.HELLO, subject=Subject.WORLD)
        transport.sendto(hello.to_bytes())
        transport.close()


    def connection_lost(self, _):
        self.loop.stop()


def main(argv):
    loop = asyncio.get_event_loop()
    client = partial(ClientProtocol, loop)

    connect = loop.create_datagram_endpoint(client, remote_addr=('127.0.0.1', 9999))
    transport, protocol = loop.run_until_complete(connect)

    loop.run_forever()
    transport.close()
    loop.close()


if __name__ == '__main__':
    main(sys.argv)
