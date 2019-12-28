import asyncio
from asyncio import Future, DatagramProtocol


class Connection:
    def __init__(self, datagram_transport, addr=None):
        self.addr = addr
        self.close_future = Future()
        self.__datagram_transport = datagram_transport
        self.__resume_writing_future = None

    async def init_connection(self):
        pass

    async def handle_packet(self, data):
        pass

    async def send(self, packet):
        if self.__resume_writing_future is not None:
            await self.__resume_writing_future
        self.__datagram_transport.sendto(packet, self.addr)

    def pause_writing(self):
        if self.__resume_writing_future is None:
            self.__resume_writing_future = Future()

    def resume_writing(self):
        if self.__resume_writing_future is not None:
            self.__resume_writing_future.set_result(None)

    def close(self):
        self.close_future.set_result(None)


class ProtocolServer(DatagramProtocol):
    def __init__(self, connection_factory):
        self._connection_factory = connection_factory
        self._connections = dict()
        self._transport = None

    def connection_made(self, transport):
        self._transport = transport

    def datagram_received(self, data, addr):
        if addr in self._connections:
            connection = self._connections[addr]
        else:
            connection = self._connection_factory(self._transport, addr=addr)
            connection.close_future.add_done_callback(lambda _: self._remove_connection(addr))
            asyncio.ensure_future(connection.close_future)
            asyncio.ensure_future(connection.init_connection())
            self._connections[addr] = connection

        asyncio.ensure_future(connection.handle_packet(data))

    def pause_writing(self):
        for connection in self._connections.values():
            connection.pause_writing()

    def resume_writing(self):
        for connection in self._connections.values():
            connection.resume_writing()

    def _remove_connection(self, addr):
        del self._connections[addr]


class ProtocolClient(DatagramProtocol):
    def __init__(self, connection_factory):
        self.close_future = Future()
        self._connection_factory = connection_factory
        self._connection = None

    def connection_made(self, transport):
        self._connection = self._connection_factory(transport)
        self._connection.close_future.add_done_callback(lambda _: transport.close())
        asyncio.ensure_future(self._connection.close_future)
        asyncio.ensure_future(self._connection.init_connection())

    def datagram_received(self, data, addr):
        asyncio.ensure_future(self._connection.handle_packet(data))

    def pause_writing(self):
        self._connection.pause_writing()

    def resume_writing(self):
        self._connection.resume_writing()

    def connection_lost(self, exc):
        self.close_future.set_result(None)
