from functools import partial

import trio
from trio import socket

from cmb_protocol.connection import Connection
from cmb_protocol.constants import MAXIMUM_TRANSMISSION_UNIT, SYMBOLS_PER_BLOCK
from cmb_protocol.packets import PacketType, RequestResourceFlags, RequestResource
from cmb_protocol.helpers import get_logger, set_listen_address, set_remote_address, get_ip_family, spawn_child_nursery, \
    calculate_number_of_blocks

logger = get_logger(__name__)


class ClientConnection(Connection):
    def __init__(self, shutdown, spawn, send, write_blocks, resource_id, reverse=False):
        super().__init__(shutdown, spawn, send)
        self.write_blocks = write_blocks
        self.resource_id = resource_id
        self.reverse = reverse

    async def init_protocol(self):
        resource_request = RequestResource(flags=RequestResourceFlags.NONE,
                                           resource_id=self.resource_id,
                                           block_offset=0)
        await self.send(resource_request)

    async def handle_packet(self, packet):
        self.shutdown()

    def send_stop(self, block_id):
        pass


async def open_connection(udp_sock, nursery, write_blocks, stop_loop, resource_id, reverse=False):
    child_nursery, shutdown_trigger = await spawn_child_nursery(nursery)

    def shutdown():
        shutdown_trigger.set()
        stop_loop()
        logger.debug('Closed connection')

    spawn = child_nursery.start_soon

    async def send(packet):
        data = packet.to_bytes()
        await udp_sock.send(data)

    return ClientConnection(shutdown, spawn, send, write_blocks, resource_id, reverse)


async def run_connection(connection, udp_sock, server_address, cancel_scope):
    with udp_sock, cancel_scope:
        await udp_sock.connect(server_address)
        set_listen_address(udp_sock.getsockname())
        set_remote_address(server_address)

        await connection.init_protocol()

        while True:
            try:
                data, address = await udp_sock.recvfrom(2048)
            except (ConnectionResetError, ConnectionRefusedError):
                # maybe handle this error
                # however, it is not guaranteed that we will receive an error when sending into the void
                pass
            else:
                packet = PacketType.parse_packet(data)
                logger.debug('Received %s', packet)
                await connection.handle_packet(packet)


async def download(resource_id, file_writer, server_address, offloading_server_address=None):
    async with trio.open_nursery() as nursery:
        server_connection, offloading_server_connection = None, None

        _, resource_length = resource_id
        block_size = MAXIMUM_TRANSMISSION_UNIT * SYMBOLS_PER_BLOCK
        blocks = [None] * calculate_number_of_blocks(resource_length, block_size)

        async def write_blocks(offset, received_blocks, reverse=False):
            # TODO: maybe need to reverse received blocks if reversed=True
            blocks[offset:offset + len(blocks)] = received_blocks

            if reverse:
                await server_connection.send_stop(offset)
            elif offloading_server_address:
                await offloading_server_connection.send_stop(offset + len(received_blocks) - 1)

        server_sock = socket.socket(family=get_ip_family(server_address), type=socket.SOCK_DGRAM)
        server_cancel_scope = trio.CancelScope()
        server_connection = await open_connection(udp_sock=server_sock,
                                                  nursery=nursery,
                                                  write_blocks=partial(write_blocks, reverse=False),
                                                  stop_loop=server_cancel_scope.cancel,
                                                  resource_id=resource_id,
                                                  reverse=False)

        if offloading_server_address:
            offloading_server_sock = socket.socket(family=get_ip_family(offloading_server_address), type=socket.SOCK_DGRAM)
            offloading_server_cancel_scope = trio.CancelScope()
            offloading_server_connection = await open_connection(udp_sock=offloading_server_sock,
                                                                 nursery=nursery,
                                                                 write_blocks=partial(write_blocks, reverse=False),
                                                                 stop_loop=offloading_server_cancel_scope.cancel,
                                                                 resource_id=resource_id,
                                                                 reverse=True)

            nursery.start_soon(run_connection, offloading_server_connection, offloading_server_sock, offloading_server_address, offloading_server_cancel_scope)

        nursery.start_soon(run_connection, server_connection, server_sock, server_address, server_cancel_scope)

    assert all([block is not None for block in blocks])

    with file_writer:
        for block in blocks:
            file_writer.write(block)


def run(resource_id, file_writer, server_address, offloading_server_address=None):
    logger.debug('Writing to %s', file_writer.name)

    trio.run(download, resource_id, file_writer, server_address, offloading_server_address)
