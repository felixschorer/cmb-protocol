from functools import partial

import trio
from trio import socket

from cmb_protocol.connection import ClientSideConnection
from cmb_protocol.constants import MAXIMUM_TRANSMISSION_UNIT, SYMBOLS_PER_BLOCK
from cmb_protocol.packets import PacketType
from cmb_protocol.helpers import get_logger, set_listen_address, set_remote_address, get_ip_family, spawn_child_nursery, \
    calculate_number_of_blocks

logger = get_logger(__name__)


async def start_connection(nursery, address, write_blocks, resource_id, reverse):
    sock = socket.socket(family=get_ip_family(address), type=socket.SOCK_DGRAM)
    cancel_scope = trio.CancelScope()

    child_nursery, shutdown_trigger = await spawn_child_nursery(nursery, shutdown_timeout=10)

    def shutdown():
        shutdown_trigger.set()
        cancel_scope.cancel()
        logger.debug('Closed connection')

    spawn = child_nursery.start_soon

    async def send(packet):
        data = packet.to_bytes()
        await sock.send(data)

    connection = ClientSideConnection(shutdown, spawn, send, write_blocks, resource_id, reverse)

    nursery.start_soon(run_receive_loop, connection, sock, address, cancel_scope)

    return connection


async def run_receive_loop(connection, udp_sock, server_address, cancel_scope):
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


async def fetch(resource_id, server_addresses):
    connections = dict()  # reverse -> connection

    _, resource_length = resource_id
    block_size = MAXIMUM_TRANSMISSION_UNIT * SYMBOLS_PER_BLOCK
    blocks = [None] * calculate_number_of_blocks(resource_length, block_size)

    async def write_blocks(offset, received_blocks, from_reverse):
        # TODO: maybe need to reverse received blocks if reversed=True
        blocks[offset:offset + len(received_blocks)] = received_blocks

        if (not from_reverse) in connections:
            await connections[not from_reverse].send_stop(offset if from_reverse else offset + len(received_blocks) - 1)

    async with trio.open_nursery() as nursery:
        for reverse, address in server_addresses.items():
            connections[reverse] = await start_connection(nursery, address, write_blocks, resource_id, reverse)

    assert all([block is not None for block in blocks])

    return blocks


def run(resource_id, file_writer, server_addresses):
    logger.debug('Writing to %s', file_writer.name)

    blocks = trio.run(fetch, resource_id, server_addresses)

    with file_writer:
        for block in blocks:
            file_writer.write(block)
