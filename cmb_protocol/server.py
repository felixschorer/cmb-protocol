import logging
import trio
from trio import socket
from ipaddress import IPv6Address
from contextvars import ContextVar
from cmb_protocol.packets import PacketType, RequestResource, DataWithMetadata
from cmb_protocol.helpers import spawn_child_nursery

logger = logging.getLogger(__name__)
listen_address = ContextVar('listen_address')


class Connection:
    def __init__(self, shutdown, spawn, send):
        self.shutdown = shutdown
        self.spawn = spawn
        self.send = send

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
        logger.debug('Closed connection {} <-> {}'.format(listen_address.get(), address))

    spawn = child_nursery.start_soon

    async def send(packet):
        data = packet.to_bytes()
        await udp_sock.sendto(data, address)

    connections[address] = Connection(shutdown, spawn, send)
    logger.debug('Accepted connection {} <-> {}'.format(listen_address.get(), address))


async def run_accept_loop(udp_sock):
    async with trio.open_nursery() as nursery:
        connections = dict()
        while True:
            try:
                data, address = await udp_sock.recvfrom(2048)
            except ConnectionResetError:
                # ignore error as we can't infer which send operation failed
                pass
            else:
                packet = PacketType.parse_packet(data)
                logger.debug('Received {} on {} from {}'.format(packet, listen_address.get(), address))

                if address not in connections:
                    if not isinstance(packet, RequestResource):
                        continue
                    await accept_connection(connections, udp_sock, nursery, address)

                await connections[address].handle_packet(packet)


async def listen(address):
    listen_address.set(address)
    ip_addr, port = address
    family = socket.AF_INET6 if isinstance(ip_addr, IPv6Address) else socket.AF_INET
    with socket.socket(family=family, type=socket.SOCK_DGRAM) as udp_sock:
        await udp_sock.bind((ip_addr, port))
        logger.info('Started listening on {}'.format(address))
        await run_accept_loop(udp_sock)


async def listen_to_all(addresses):
    async with trio.open_nursery() as nursery:
        for address in addresses:
            nursery.start_soon(listen, address)


def run(file_reader, addresses):
    logger.debug('Reading from {}'.format(file_reader.name))
    trio.run(listen_to_all, addresses)
