import logging
import trio
from trio import socket
from ipaddress import IPv6Address
from cmb_protocol.packets import PacketType, RequestResource, DataWithMetadata
from cmb_protocol.helpers import spawn_child_nursery

logger = logging.getLogger(__name__)


class BoundTransport:
    def __init__(self, sock, address):
        self._sock = sock
        self._address = address

    async def send(self, packet):
        data = packet.to_bytes()
        await self._sock.sendto(data, self._address)


class Connection:
    def __init__(self, shutdown_trigger, nursery, transport):
        self._shutdown_trigger = shutdown_trigger
        self._nursery = nursery
        self._transport = transport

    async def handle_packet(self, packet):
        if isinstance(packet, RequestResource):
            data_with_metadata = DataWithMetadata(resource_size=0, block_id=0, fec_data=bytes())
            await self.send(data_with_metadata)
        self.shutdown()

    async def send(self, packet):
        await self._transport.send(packet)

    def shutdown(self):
        self._shutdown_trigger.set()

    def force_close(self):
        self._nursery.cancel_scope.cancel()


async def listen(listen_address, nursery):
    ip_addr, port = listen_address
    family = socket.AF_INET6 if isinstance(ip_addr, IPv6Address) else socket.AF_INET

    udp_sock = socket.socket(family=family, type=socket.SOCK_DGRAM)
    await udp_sock.bind((ip_addr, port))

    logger.info('Started listening on {}'.format(listen_address))

    connections = dict()
    while True:
        try:
            data, address = await udp_sock.recvfrom(2048)
        except ConnectionResetError:
            # ignore error as we can't infer which send operation failed
            pass
        else:
            packet = PacketType.parse_packet(data)
            logger.debug('Received {} from {}'.format(packet, address))

            if address not in connections:
                if not isinstance(packet, RequestResource):
                    continue

                child_nursery, shutdown_trigger = await spawn_child_nursery(nursery)
                transport = BoundTransport(udp_sock, address)
                connections[address] = Connection(shutdown_trigger, child_nursery, transport)

                logger.debug('Accepted connection {} <-> {}'.format(listen_address, address))

                async def cleanup():
                    await shutdown_trigger.wait()
                    del connections[address]
                    logger.debug('Closed connection {} <-> {}'.format(listen_address, address))

                nursery.start_soon(cleanup)

            await connections[address].handle_packet(packet)


async def start_listening(addresses):
    async with trio.open_nursery() as nursery:
        for address in addresses:
            nursery.start_soon(listen, address, nursery)


def run(file_reader, listen_addresses):
    logger.debug('Reading from {}'.format(file_reader.name))

    trio.run(start_listening, listen_addresses)
