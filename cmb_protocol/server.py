import struct
import trio
import hashlib

from functools import partial
from trio import socket

from cmb_protocol.coding import Encoder
from cmb_protocol.connection import ServerSideConnection
from cmb_protocol.constants import MAXIMUM_TRANSMISSION_UNIT, SYMBOLS_PER_BLOCK, RESOURCE_ID_STRUCT_FORMAT
from cmb_protocol.packets import PacketType, RequestResource
from cmb_protocol.helpers import spawn_child_nursery, get_logger, set_listen_address, set_remote_address, get_ip_family

logger = get_logger(__name__)


async def run_accept_loop(udp_sock, resource_id, encoders):
    async with trio.open_nursery() as nursery:
        connections = dict()
        while True:
            try:
                data, address = await udp_sock.recvfrom(2048)
                set_remote_address(address)
                packet = PacketType.parse_packet(data)
                logger.debug('Received %s', packet)
            except (ConnectionResetError, ConnectionRefusedError):
                # ignore error as we can't infer which send operation failed
                pass
            except ValueError as exc:
                logger.exception(exc)
            else:
                if address not in connections:
                    if not isinstance(packet, RequestResource):
                        continue

                    child_nursery, shutdown_trigger = await spawn_child_nursery(nursery, shutdown_timeout=3)

                    def shutdown():
                        shutdown_trigger.set()
                        del connections[address]
                        logger.debug('Closed connection')

                    spawn = child_nursery.start_soon

                    async def send(packet_to_send):
                        packet_bytes = packet_to_send.to_bytes()
                        await udp_sock.sendto(packet_bytes, address)

                    connections[address] = ServerSideConnection(shutdown, spawn, send, resource_id, encoders)
                    logger.debug('Accepted connection')

                await connections[address].handle_packet(packet)


async def serve(addresses, resource_id, encoders):
    async with trio.open_nursery() as nursery:
        for address in addresses:
            async def _serve():
                set_listen_address(address)
                with socket.socket(family=get_ip_family(address), type=socket.SOCK_DGRAM) as udp_sock:
                    await udp_sock.bind(address)
                    logger.info('Started listening')
                    await run_accept_loop(udp_sock, resource_id, encoders)

            nursery.start_soon(_serve)


def run(file_reader, addresses):
    m = hashlib.md5()
    resource_length = 0
    encoders = []

    # read file
    with file_reader:
        logger.debug('Reading from %s', file_reader.name)

        # split file into blocks
        block_size = MAXIMUM_TRANSMISSION_UNIT * SYMBOLS_PER_BLOCK
        for block in iter(partial(file_reader.read, block_size), b''):
            m.update(block)
            # create encoders for blocks
            encoders.append(Encoder(block, MAXIMUM_TRANSMISSION_UNIT))
            resource_length += len(block)

    # hash file
    resource_hash = m.digest()
    resource_id = (resource_hash, resource_length)
    packed_resource_id = struct.pack(RESOURCE_ID_STRUCT_FORMAT, *resource_id).hex()

    # print file hash concatenated with length
    logger.debug('Serving resource %s', packed_resource_id)
    trio.run(serve, addresses, resource_id, encoders)
