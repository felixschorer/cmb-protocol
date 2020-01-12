import logging
import trio
from trio import socket
from ipaddress import IPv6Address
from cmb_protocol.packets import PacketType, RequestResource, DataWithMetadata

logger = logging.getLogger(__name__)


async def listen(address):
    ip_addr, port = address
    family = socket.AF_INET6 if isinstance(ip_addr, IPv6Address) else socket.AF_INET

    udp_sock = socket.socket(family=family, type=socket.SOCK_DGRAM)
    await udp_sock.bind((ip_addr, port))

    while True:
        try:
            data, address = await udp_sock.recvfrom(2048)
        except ConnectionResetError:
            pass
        else:
            packet = PacketType.parse_packet(data)
            logger.debug('Received {} from {}'.format(packet, address))

            if isinstance(packet, RequestResource):
                data_with_metadata = DataWithMetadata(resource_size=0, block_id=0, fec_data=bytes())
                await udp_sock.sendto(data_with_metadata.to_bytes(), address)


async def start_listening(addresses):
    async with trio.open_nursery() as nursery:
        for address in addresses:
            nursery.start_soon(listen, address)


def run(file_reader, listen_addresses):
    with file_reader:
        logger.debug('Reading from {}'.format(file_reader.name))

    trio.run(start_listening, listen_addresses)
