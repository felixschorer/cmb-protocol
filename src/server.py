import asyncio
import capnp
from asyncio import DatagramProtocol


capnp.remove_import_hook()
hello_capnp = capnp.load('../capnp/hello.capnp')


class ServerProtocol(DatagramProtocol):
    def datagram_received(self, data, addr):
        hello = hello_capnp.Hello.from_bytes_packed(data)
        print(hello.message)


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
