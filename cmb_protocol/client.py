import trio
from packets import RequestResource, PacketType


async def init_protocol(sock):
    resource_request = RequestResource(overhead=0, resource_id=bytes(16), block_offset=0)
    packet_bytes = resource_request.to_bytes()

    await sock.send(packet_bytes)


async def receive(sock):
    data, address = await sock.recvfrom(2048)
    packet = PacketType.parse_packet(data)
    print(address, packet)


async def main():
    udp_sock = trio.socket.socket(
        family=trio.socket.AF_INET,   # IPv4
        type=trio.socket.SOCK_DGRAM,  # UDP
    )

    await udp_sock.connect(('127.0.0.1', 9999))

    async with trio.open_nursery() as nursery:
        nursery.start_soon(init_protocol, udp_sock)
        nursery.start_soon(receive, udp_sock)


if __name__ == '__main__':
    trio.run(main)
