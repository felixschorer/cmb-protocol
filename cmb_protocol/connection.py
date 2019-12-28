import asyncio
from abc import ABC, abstractmethod
from asyncio import Future, DatagramProtocol


class BoundTransport(ABC):
    @abstractmethod
    def send(self, data):
        pass


class BoundDatagramTransport(BoundTransport):
    def __init__(self, datagram_transport, addr=None):
        super().__init__()
        self._datagram_transport = datagram_transport
        self._addr = addr

    def send(self, data):
        self._datagram_transport.sendto(data, addr=self._addr)


class Connection:
    def __init__(self, transport):
        self.close_future = Future()
        self.__transport = transport
        self.__resume_writing_future = None

    async def init_connection(self):
        pass

    async def handle_packet(self, data):
        pass

    async def send(self, packet):
        if self.__resume_writing_future is not None:
            await self.__resume_writing_future
        self.__transport.send(packet)

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
            asyncio.ensure_future(connection.handle_packet(data))
        else:
            transport = BoundDatagramTransport(self._transport, addr=addr)
            connection = self._connection_factory(transport)
            connection.close_future.add_done_callback(lambda _: self._remove_connection(addr))
            asyncio.ensure_future(self._init_connection(connection, data))
            self._connections[addr] = connection

    def pause_writing(self):
        for connection in self._connections.values():
            connection.pause_writing()

    def resume_writing(self):
        for connection in self._connections.values():
            connection.resume_writing()

    @staticmethod
    async def _init_connection(connection, data):
        await connection.init_connection()
        await connection.handle_packet(data)

    def _remove_connection(self, addr):
        del self._connections[addr]


class ProtocolClient(DatagramProtocol):
    def __init__(self, connection_factory):
        self.close_future = Future()
        self._connection_factory = connection_factory
        self._connection = None

    def connection_made(self, transport):
        self._connection = self._connection_factory(BoundDatagramTransport(transport))
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
