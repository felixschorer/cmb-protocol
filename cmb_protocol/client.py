import logging
import trio
from trio import socket
from ipaddress import IPv6Address
from cmb_protocol.packets import PacketType, RequestResource
from cmb_protocol.packets.request_resource import RequestResourceFlags

logger = logging.getLogger(__name__)


async def init_protocol(sock):
    resource_request = RequestResource(flags=RequestResourceFlags.NONE, resource_id=bytes(16), block_offset=0)
    packet_bytes = resource_request.to_bytes()

    await sock.send(packet_bytes)


async def receive(sock):
    try:
        data, address = await sock.recvfrom(2048)
    except ConnectionResetError:
        pass
    else:
        packet = PacketType.parse_packet(data)
        logger.debug('Received {} from {}'.format(packet, address))


async def start_download(resource_id, server_address, offloading_server_address=None):
    ip_addr, port = server_address
    family = socket.AF_INET6 if isinstance(ip_addr, IPv6Address) else socket.AF_INET

    udp_sock = socket.socket(family=family, type=socket.SOCK_DGRAM)
    await udp_sock.connect((ip_addr, port))

    async with trio.open_nursery() as nursery:
        nursery.start_soon(init_protocol, udp_sock)
        nursery.start_soon(receive, udp_sock)


def run(resource_id, file_writer, server_address, offloading_server_address=None):
    with file_writer:
        logger.debug('Writing to {}'.format(file_writer.name))

    trio.run(start_download, resource_id, server_address, offloading_server_address)
