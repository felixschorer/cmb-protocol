import hashlib
import time
from collections import namedtuple

import trio
from trio import socket
from cmb_protocol.connection import ClientSideConnection
from cmb_protocol.constants import calculate_number_of_blocks
from cmb_protocol.packets import PacketType
from cmb_protocol.helpers import once
from cmb_protocol.trio_util import spawn_child_nursery, get_ip_family
from cmb_protocol import log_util

logger = log_util.get_logger(__name__)


ConnectionConfig = namedtuple('ConnectionConfig', ['address', 'sending_rate', 'reverse'])


async def run_receive_loop(connection_opened, connection_closed, write_blocks, resource_id, connection_config):
    with socket.socket(family=get_ip_family(connection_config.address), type=socket.SOCK_DGRAM) as udp_sock:
        async with trio.open_nursery() as nursery:
            child_nursery, shutdown_trigger = await spawn_child_nursery(nursery.start_soon, shutdown_timeout=3)

            with trio.CancelScope() as cancel_scope:
                await udp_sock.connect(connection_config.address)
                log_util.set_listen_address(udp_sock.getsockname()[:2])
                log_util.set_remote_address(connection_config.address)

                @once
                def shutdown():
                    # coordinate shutdown with higher order protocol instance
                    connection_closed()
                    # trigger child nursery timeout
                    shutdown_trigger.set()
                    # cancel receive loop
                    cancel_scope.cancel()
                    logger.debug('Closed connection')

                spawn = child_nursery.start_soon

                async def send(packet_to_send):
                    packet_bytes = packet_to_send.to_bytes()
                    await udp_sock.send(packet_bytes)

                connection = ClientSideConnection(shutdown, spawn, send, write_blocks, resource_id,
                                                  connection_config.sending_rate, connection_config.reverse)
                # coordinate startup with higher order protocol instance
                connection_opened(connection)

                while True:
                    try:
                        data = await udp_sock.recv(2048)
                        packet = PacketType.parse_packet(data)
                    except (ConnectionResetError, ConnectionRefusedError):
                        # maybe handle this error
                        # however, it is not guaranteed that we will receive an error when sending into the void
                        pass
                    except ValueError as exc:
                        logger.exception(exc)
                    else:
                        await connection.handle_packet(packet)


async def fetch(resource_id, connection_configs):
    resource_hash, resource_length = resource_id
    blocks = [None] * calculate_number_of_blocks(resource_length)

    async with trio.open_nursery() as nursery:
        connections = dict()  # reverse -> connection

        # inner function to create a closure around reverse_direction and server_address
        def spawn_connection(connection_config):
            def connection_opened(connection):
                connections[connection_config.reverse] = connection

            def connection_closed():
                del connections[connection_config.reverse]

            async def write_block(block_id, received_block):
                blocks[block_id - 1] = received_block  # block ids start at 1

                if (not connection_config.reverse) in connections:
                    await connections[not connection_config.reverse].send_stop(block_id)

            nursery.start_soon(run_receive_loop, connection_opened, connection_closed, write_block,
                               resource_id, connection_config)

        for config in connection_configs:
            spawn_connection(config)

    md5 = hashlib.md5()
    for block in blocks:
        md5.update(block)
    assert md5.digest() == resource_hash

    return blocks


def log_value_error(exc):
    if isinstance(exc, ValueError):
        logger.error(exc)
        return None
    else:
        return exc


def run(resource_id, file_writer, connection_configs):
    if hasattr(file_writer, 'buffer'):
        # in case of stdout we have to use the buffer to write binary data
        file_writer = file_writer.buffer

    logger.info('Writing to %s', file_writer.name)
    _, resource_length = resource_id
    logger.info('Downloading %f Mb', resource_length / 1000 / 1000)
    logger.info('Combined target transmission rate %f Mbit/s',
                sum(config.sending_rate for config in connection_configs) / 1000 / 1000 * 8)

    with trio.MultiError.catch(log_value_error):
        start = time.time()
        blocks = trio.run(fetch, resource_id, connection_configs)
        elapsed = time.time() - start
        logger.info('Took %f seconds', elapsed)
        logger.info('Good put %f Mbit/s', resource_length / 1000 / 1000 / elapsed * 8)

        with file_writer:
            for block in blocks:
                file_writer.write(block)
