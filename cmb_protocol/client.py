import trio
from trio import socket
from cmb_protocol.packets import PacketType, RequestResource
from cmb_protocol.packets.request_resource import RequestResourceFlags
from cmb_protocol.helpers import get_logger, set_listen_address, set_remote_address, get_ip_family

logger = get_logger(__name__)


async def init_protocol(sock):
    resource_request = RequestResource(flags=RequestResourceFlags.NONE, resource_id=bytes(16), block_offset=0)
    packet_bytes = resource_request.to_bytes()

    await sock.send(packet_bytes)


async def receive(sock):
    try:
        data, address = await sock.recvfrom(2048)
    except ConnectionResetError:
        # maybe handle this error
        # however, it is not guaranteed that we will receive an error when sending into the void
        pass
    else:
        packet = PacketType.parse_packet(data)
        logger.debug('Received %s', packet)


async def start_download(resource_id, server_address, offloading_server_address=None):
    set_remote_address(server_address)
    with socket.socket(family=get_ip_family(server_address), type=socket.SOCK_DGRAM) as udp_sock:
        await udp_sock.connect(server_address)
        set_listen_address(udp_sock.getsockname())
        async with trio.open_nursery() as nursery:
            nursery.start_soon(init_protocol, udp_sock)
            nursery.start_soon(receive, udp_sock)


def run(resource_id, file_writer, server_address, offloading_server_address=None):
    logger.debug('Writing to %s', file_writer.name)

    trio.run(start_download, resource_id, server_address, offloading_server_address)
