import struct
import trio
import hashlib
from functools import partial
from trio import socket
from cmb_protocol.coding import Encoder
from cmb_protocol.connection import ServerSideConnection
from cmb_protocol.constants import MAXIMUM_TRANSMISSION_UNIT, SYMBOLS_PER_BLOCK, RESOURCE_ID_STRUCT_FORMAT
from cmb_protocol.packets import PacketType, RequestResource
from cmb_protocol.helpers import once
from cmb_protocol.trio_util import spawn_child_nursery, get_ip_family
from cmb_protocol import log_util

logger = log_util.get_logger(__name__)


async def run_accept_loop(udp_sock, resource_id, encoders):
    async with trio.open_nursery() as nursery:
        connections = dict()

        # inner function to create a closure around client_address
        async def accept_connection(client_address):
            child_nursery, shutdown_trigger = await spawn_child_nursery(nursery.start_soon, shutdown_timeout=3)

            @once
            def shutdown():
                # trigger child nursery timeout
                shutdown_trigger.set()
                # remove from dict to prevent handling of future packets
                del connections[client_address]
                logger.debug('Closed connection')

            spawn = child_nursery.start_soon

            async def send(packet_to_send):
                packet_bytes = packet_to_send.to_bytes()
                await udp_sock.sendto(packet_bytes, client_address)

            connections[client_address] = ServerSideConnection(shutdown, spawn, send, resource_id, encoders)
            logger.debug('Accepted connection')

        while True:
            try:
                data, address = await udp_sock.recvfrom(2048)
                log_util.set_remote_address(address)

                packet = PacketType.parse_packet(data)
            except (ConnectionResetError, ConnectionRefusedError):
                # ignore error as we can't infer which send operation failed
                pass
            except ValueError as exc:
                logger.exception(exc)
            else:
                if address not in connections:
                    if not isinstance(packet, RequestResource):
                        continue
                    await accept_connection(address)

                await connections[address].handle_packet(packet)


async def serve(addresses, resource_id, encoders):
    async with trio.open_nursery() as nursery:
        for address in addresses:
            async def _serve():
                log_util.set_listen_address(address)

                with socket.socket(family=get_ip_family(address), type=socket.SOCK_DGRAM) as udp_sock:
                    await udp_sock.bind(address)
                    logger.info('Started listening')
                    await run_accept_loop(udp_sock, resource_id, encoders)

            nursery.start_soon(_serve)


def run(file_reader, addresses):
    md5 = hashlib.md5()
    resource_length = 0
    encoders = dict()  # block_id -> encoder

    with file_reader:
        logger.debug('Reading from %s', file_reader.name)

        # split file into blocks
        block_size = MAXIMUM_TRANSMISSION_UNIT * SYMBOLS_PER_BLOCK
        for block_index, block_content in enumerate(iter(partial(file_reader.read, block_size), b'')):
            md5.update(block_content)
            resource_length += len(block_content)
            encoders[block_index + 1] = Encoder(block_content, MAXIMUM_TRANSMISSION_UNIT)  # block id starts at 1

    resource_hash = md5.digest()
    resource_id = (resource_hash, resource_length)
    packed_resource_id = struct.pack(RESOURCE_ID_STRUCT_FORMAT, *resource_id).hex()

    logger.info('Serving resource %s', packed_resource_id)
    trio.run(serve, addresses, resource_id, encoders)
