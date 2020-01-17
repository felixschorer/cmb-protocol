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


async def accept_connection(connections, udp_sock, nursery, address, resource_id, encoders):
    child_nursery, shutdown_trigger = await spawn_child_nursery(nursery)

    def shutdown():
        shutdown_trigger.set()
        del connections[address]
        logger.debug('Closed connection')

    spawn = child_nursery.start_soon

    async def send(packet):
        data = packet.to_bytes()
        await udp_sock.sendto(data, address)

    connections[address] = ServerSideConnection(shutdown, spawn, send, resource_id, encoders)
    logger.debug('Accepted connection')


async def run_accept_loop(udp_sock, resource_id, encoders):
    async with trio.open_nursery() as nursery:
        connections = dict()
        while True:
            try:
                data, address = await udp_sock.recvfrom(2048)
            except (ConnectionResetError, ConnectionRefusedError):
                # ignore error as we can't infer which send operation failed
                pass
            else:
                set_remote_address(address)
                packet = PacketType.parse_packet(data)
                logger.debug('Received %s', packet)

                if address not in connections:
                    if not isinstance(packet, RequestResource):
                        continue
                    await accept_connection(connections, udp_sock, nursery, address, resource_id, encoders)

                await connections[address].handle_packet(packet)


async def listen(address, resource_id, encoders):
    set_listen_address(address)
    with socket.socket(family=get_ip_family(address), type=socket.SOCK_DGRAM) as udp_sock:
        await udp_sock.bind(address)
        logger.info('Started listening')
        await run_accept_loop(udp_sock, resource_id, encoders)


async def listen_to_all(addresses, resource_id, encoders):
    async with trio.open_nursery() as nursery:
        for address in addresses:
            nursery.start_soon(listen, address, resource_id, encoders)


def run(file_reader, addresses):
    m = hashlib.md5()
    resource_length = 0
    encoders = []

    # read file, split file into blocks, create encoders for blocks, hash file, print file hash concatenated with length
    with file_reader:
        logger.debug('Reading from %s', file_reader.name)

        block_size = MAXIMUM_TRANSMISSION_UNIT * SYMBOLS_PER_BLOCK
        for block in iter(partial(file_reader.read, block_size), b''):
            m.update(block)
            encoders.append(Encoder(block, MAXIMUM_TRANSMISSION_UNIT))
            resource_length += len(block)

    resource_hash = m.digest()
    resource_id = (resource_hash, resource_length)
    packed_resource_id = struct.pack(RESOURCE_ID_STRUCT_FORMAT, *resource_id).hex()

    logger.debug('Serving resource %s', packed_resource_id)
    trio.run(listen_to_all, addresses, resource_id, encoders)
