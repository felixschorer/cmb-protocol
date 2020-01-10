import trio
from packets import PacketType, RequestResource, DataWithMetadata


async def main():
    udp_sock = trio.socket.socket(
        family=trio.socket.AF_INET,   # IPv4
        type=trio.socket.SOCK_DGRAM,  # UDP
    )

    await udp_sock.bind(('127.0.0.1', 9999))

    while True:
        data, address = await udp_sock.recvfrom(2048)
        packet = PacketType.parse_packet(data)
        print(address, packet)

        if isinstance(packet, RequestResource):
            data_with_metadata = DataWithMetadata(resource_size=0, block_id=0, fec_data=bytes())
            await udp_sock.sendto(data_with_metadata.to_bytes(), address)


if __name__ == '__main__':
    trio.run(main)
