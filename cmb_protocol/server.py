import trio
from trio import socket

from cmb_protocol.connection import Connection
from cmb_protocol.packets import PacketType, RequestResource, DataWithMetadata
from cmb_protocol.helpers import spawn_child_nursery, get_logger, set_listen_address, set_remote_address, get_ip_family

logger = get_logger(__name__)


class ServerConnection(Connection):
    async def handle_packet(self, packet):
        if isinstance(packet, RequestResource):
            data_with_metadata = DataWithMetadata(resource_size=0, block_id=0, fec_data=bytes())
            await self.send(data_with_metadata)
        self.shutdown()


async def accept_connection(connections, udp_sock, nursery, address):
    child_nursery, shutdown_trigger = await spawn_child_nursery(nursery)

    def shutdown():
        shutdown_trigger.set()
        del connections[address]
        logger.debug('Closed connection')

    spawn = child_nursery.start_soon

    async def send(packet):
        data = packet.to_bytes()
        await udp_sock.sendto(data, address)

    connections[address] = ServerConnection(shutdown, spawn, send)
    logger.debug('Accepted connection')


async def run_accept_loop(udp_sock):
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
                    await accept_connection(connections, udp_sock, nursery, address)

                await connections[address].handle_packet(packet)


async def listen(address):
    set_listen_address(address)
    with socket.socket(family=get_ip_family(address), type=socket.SOCK_DGRAM) as udp_sock:
        await udp_sock.bind(address)
        logger.info('Started listening')
        await run_accept_loop(udp_sock)


async def listen_to_all(addresses):
    async with trio.open_nursery() as nursery:
        for address in addresses:
            nursery.start_soon(listen, address)


def run(file_reader, addresses):

    # read file, split file into blocks, create encoders for blocks, hash file, print file hash concatenated with length

    logger.debug('Reading from %s', file_reader.name)
    trio.run(listen_to_all, addresses)
