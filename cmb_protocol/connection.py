from cmb_protocol.constants import MAXIMUM_TRANSMISSION_UNIT, SYMBOLS_PER_BLOCK
from cmb_protocol.helpers import calculate_number_of_blocks
from cmb_protocol.packets import RequestResourceFlags, RequestResource, Data


class Connection:
    def __init__(self, shutdown, spawn, send):
        self.shutdown = shutdown
        self.spawn = spawn
        self.send = send

    async def handle_packet(self, packet):
        self.shutdown()


class ClientSideConnection(Connection):
    def __init__(self, shutdown, spawn, send, write_blocks, resource_id, reverse):
        super().__init__(shutdown, spawn, send)
        self.write_blocks = write_blocks
        self.resource_id = resource_id
        self.reverse = reverse

        self.spawn(self.init_protocol)

    async def init_protocol(self):
        flags = RequestResourceFlags.REVERSE if self.reverse else RequestResourceFlags.NONE
        _, resource_length = self.resource_id
        block_size = MAXIMUM_TRANSMISSION_UNIT * SYMBOLS_PER_BLOCK
        offset = calculate_number_of_blocks(resource_length, block_size) - 1 if self.reverse else 0
        resource_request = RequestResource(flags=flags,
                                           resource_id=self.resource_id,
                                           block_offset=offset)
        await self.send(resource_request)

    async def handle_packet(self, packet):
        self.shutdown()

    async def send_stop(self, block_id):
        pass


class ServerSideConnection(Connection):
    def __init__(self, shutdown, spawn, send, resource_id, encoders):
        super().__init__(shutdown, spawn, send)
        self.resource_id = resource_id
        self.encoders = encoders

    async def handle_packet(self, packet):
        if isinstance(packet, RequestResource):
            data = Data(block_id=0, fec_data=bytes())
            await self.send(data)
        self.shutdown()
