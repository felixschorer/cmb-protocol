from abc import ABC

import trio

from cmb_protocol import log_util
from cmb_protocol.coding import Decoder, RAPTORQ_HEADER_SIZE
from cmb_protocol.constants import MAXIMUM_TRANSMISSION_UNIT, calculate_number_of_blocks, calculate_block_size
from cmb_protocol.packets import RequestResourceFlags, RequestResource, AckBlock, NackBlock, ShrinkRange, Data, \
    Error, ErrorCode, Packet
from cmb_protocol.sequence_number import SequenceNumber
from cmb_protocol.timestamp import Timestamp


logger = log_util.get_logger(__name__)


SEGMENT_SIZE = Packet.PACKET_TYPE_SIZE + Data.HEADER_SIZE + RAPTORQ_HEADER_SIZE + MAXIMUM_TRANSMISSION_UNIT
MAXIMUM_HEARTBEAT_INTERVAL = 0.25
SCHEDULING_GRANULARITY = 0.001


class Connection(ABC):
    """
    Abstract connection which immediately shuts down after receiving a packet
    """

    def __init__(self, shutdown, spawn, send):
        """
        :param shutdown: function for notifying the receiving loop to shut down this connection
        :param spawn:    function for spawning background tasks
        :param send:     async function for sending a packet to the remote peer
        """
        self._shutdown = shutdown
        self._spawn = spawn
        self._send = send

    async def handle_packet(self, packet):
        """
        Called by the receiving loop upon packet receipt.
        The loop should await this method to propagate back pressure.
        If this method needs to do anything else other than responding with a packet,
        it should spawn a background task.
        :param packet:  the received packet
        """
        self.shutdown()

    def shutdown(self):
        self._shutdown()

    def spawn(self, async_func, *args, **kwargs):
        self._spawn(async_func, *args, **kwargs)

    async def send(self, packet):
        await self._send(packet)


class ClientSideConnection(Connection):
    def __init__(self, shutdown, spawn, send, write_blocks, resource_id, reverse):
        """
        :param shutdown:     cf. Connection
        :param spawn:        cf. Connection
        :param send:         cf. Connection
        :param write_blocks: async function for writing a consecutive range of block to the output
        :param resource_id:  the id of the resource
        :param reverse:      bool whether this connection should request the blocks in reverse order
        """
        super().__init__(shutdown, spawn, send)
        self.write_blocks = write_blocks
        self.resource_id = resource_id
        self.reverse = reverse

        _, resource_length = self.resource_id
        last_block_id = calculate_number_of_blocks(resource_length) - 1

        self.stop_after_block_id = 0 if self.reverse else last_block_id
        self.offset = last_block_id if self.reverse else 0

        self.decoders = dict()  # block_id -> decoder

        self.rtt = None
        self.cancel_scope = None

        self.spawn(self.keep_connection_alive)

    async def keep_connection_alive(self):
        with trio.CancelScope() as cancel_scope:
            self.cancel_scope = cancel_scope
            while True:
                sending_rate = 500000  # TODO
                flags = RequestResourceFlags.REVERSE if self.reverse else RequestResourceFlags.NONE
                resource_request = RequestResource(flags=flags,
                                                   timestamp=Timestamp.now(),
                                                   sending_rate=sending_rate,
                                                   resource_id=self.resource_id,
                                                   block_offset=self.offset)
                await self.send(resource_request)
                min_interval = max(4 * SEGMENT_SIZE / sending_rate, SCHEDULING_GRANULARITY)
                interval = MAXIMUM_HEARTBEAT_INTERVAL if self.rtt is None else max(min_interval, min(self.rtt, MAXIMUM_HEARTBEAT_INTERVAL))
                await trio.sleep(interval)

    async def handle_data(self, packet):
        rtt_sample = Timestamp.now() - packet.timestamp - packet.delay
        self.rtt = rtt_sample if self.rtt is None else 0.9 * self.rtt + 0.1 * rtt_sample
        logger.debug('Measured RTT: %f', self.rtt)

        recent = packet.block_id <= self.offset if self.reverse else packet.block_id >= self.offset
        if recent:
            if packet.block_id not in self.decoders:
                _, resource_length = self.resource_id
                block_size = calculate_block_size(resource_length, packet.block_id)
                self.decoders[packet.block_id] = Decoder(block_size, MAXIMUM_TRANSMISSION_UNIT)

            # TODO: decode only if we have enough packets
            decoded = self.decoders[packet.block_id].decode([packet.fec_data])

            if decoded:
                # TODO: blocks could be decoded out of order
                self.offset += -1 if self.reverse else 1
                if self.stop_after_block_id == packet.block_id:
                    self.shutdown()
                await self.send(AckBlock(block_id=packet.block_id))
                await self.write_blocks(packet.block_id, [decoded])

    async def handle_error(self, packet):
        # TODO: error handling?
        self.shutdown()

    async def handle_packet(self, packet):
        """
        Called by the receiving loop upon packet receipt.
        cf. Connection
        """
        if isinstance(packet, Data):
            await self.handle_data(packet)
        elif isinstance(packet, Error):
            await self.handle_error(packet)

    async def send_stop(self, stop_at_block_id):
        """
        Called by the higher order protocol instance after receiving blocks from the opposing connection
        :param stop_at_block_id: the block id at which the transmission should stop
        """
        current, new = self.stop_after_block_id, stop_at_block_id + 1 if self.reverse else stop_at_block_id - 1
        recent = current <= new if self.reverse else current >= new
        if recent:
            self.stop_after_block_id = new
            finished = self.offset <= stop_at_block_id if self.reverse else self.offset >= stop_at_block_id
            if finished:
                self.shutdown()
            await self.send(ShrinkRange(stop_at_block_id=stop_at_block_id))

    def shutdown(self):
        super().shutdown()
        self.cancel_scope.cancel()


class ServerSideConnection(Connection):

    def __init__(self, shutdown, spawn, send, resource_id, encoders):
        """
        :param shutdown:     cf. Connection
        :param spawn:        cf. Connection
        :param send:         cf. Connection
        :param resource_id:  the id of the resource
        :param encoders:     ordered dict (block_id -> encoder), ordered by block_id asc
        """
        super().__init__(shutdown, spawn, send)
        self.resource_id = resource_id
        self.encoders = encoders
        self.unacknowlegded_blocks = set(encoders.keys())
        self.connected = False
        self.reverse = None

        self.recent_resource_request_received_at = None
        self.recent_resource_request = None

    async def handle_request_resource(self, packet):
        self.recent_resource_request_received_at = Timestamp.now()
        self.recent_resource_request = packet

        if self.resource_id != packet.resource_id:
            await self.send(Error(ErrorCode.RESOURCE_NOT_FOUND))
            self.shutdown()
        elif not self.connected:
            self.reverse = bool(packet.flags & RequestResourceFlags.REVERSE)
            self.connected = True
            self.spawn(self.send_blocks)
        else:
            pass  # already connected and sending

    def packets(self):
        for block_id, encoder in reversed(self.encoders.items()) if self.reverse else self.encoders.items():
            if block_id not in self.unacknowlegded_blocks:
                continue

            for fec_data in encoder.source_packets():
                # check in every iteration if we have received a stop signal in the meantime
                if block_id not in self.unacknowlegded_blocks:
                    break

                yield block_id, fec_data

    async def send_blocks(self):
        try:
            packet_iter = self.packets()
            sequence_number = SequenceNumber(0)
            send_time = Timestamp.now()
            while True:
                if Timestamp.now() - self.recent_resource_request_received_at > 4 * MAXIMUM_HEARTBEAT_INTERVAL:
                    logger.debug('Connection timed out')
                    return  # connection is broken, shutdown

                if Timestamp.now() < send_time:
                    await trio.sleep(SCHEDULING_GRANULARITY)
                else:
                    try:
                        block_id, fec_data = next(packet_iter)
                    except StopIteration:
                        return
                    else:
                        packet = Data(block_id=block_id,
                                      timestamp=self.recent_resource_request.timestamp,
                                      delay=Timestamp.now() - self.recent_resource_request_received_at,
                                      sequence_number=sequence_number,
                                      fec_data=fec_data)
                        await self.send(packet)
                        sequence_number += 1
                        send_time += SEGMENT_SIZE / self.recent_resource_request.sending_rate
        finally:
            self.shutdown()

    async def handle_ack_block(self, packet):
        if packet.block_id in self.unacknowlegded_blocks:
            self.unacknowlegded_blocks.remove(packet.block_id)

    async def handle_nack_block(self, packet):
        pass

    async def handle_ack_opposite_range(self, packet):
        acknowledged_blocks = set(
            range(0, packet.stop_at_block_id + 1)
            if self.reverse else
            range(packet.stop_at_block_id, len(self.encoders))
        )
        self.unacknowlegded_blocks.difference_update(acknowledged_blocks)

    async def handle_packet(self, packet):
        """
        Called by the receiving loop upon packet receipt.
        cf. Connection
        """
        if isinstance(packet, RequestResource):
            await self.handle_request_resource(packet)
        elif isinstance(packet, AckBlock):
            await self.handle_ack_block(packet)
        elif isinstance(packet, NackBlock):
            await self.handle_nack_block(packet)
        elif isinstance(packet, ShrinkRange):
            await self.handle_ack_opposite_range(packet)

    def shutdown(self):
        super().shutdown()
