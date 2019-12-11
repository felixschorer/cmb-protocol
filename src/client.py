import asyncio
import capnp
import sys
from asyncio import DatagramProtocol
from functools import partial


capnp.remove_import_hook()
hello_capnp = capnp.load('../capnp/hello.capnp')


class ClientProtocol(DatagramProtocol):
    def __init__(self, message, loop):
        self.message = message
        self.loop = loop

    def connection_made(self, transport):
        hello = hello_capnp.Hello.new_message()
        hello.message = self.message

        data = hello.to_bytes_packed()
        transport.sendto(data)
        transport.close()


    def connection_lost(self, exc):
        self.loop.stop()


def main(argv):
    loop = asyncio.get_event_loop()
    message = "Hello World!" if len(argv) < 2 else argv[1]
    client = partial(ClientProtocol, message, loop)

    connect = loop.create_datagram_endpoint(client, remote_addr=('127.0.0.1', 9999))
    transport, protocol = loop.run_until_complete(connect)

    loop.run_forever()
    transport.close()
    loop.close()


if __name__ == '__main__':
    main(sys.argv)
