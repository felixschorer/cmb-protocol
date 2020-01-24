from abc import ABC
from collections import namedtuple

from cmb_protocol.coding import Decoder, RAPTORQ_HEADER_SIZE
from cmb_protocol.constants import MAXIMUM_TRANSMISSION_UNIT, calculate_number_of_blocks, calculate_block_size
from cmb_protocol.packets import RequestResourceFlags, RequestResource, AckBlock, NackBlock, AckOppositeRange, Data, \
    Error, ErrorCode, Packet, Feedback
from cmb_protocol.sequencenumber import SequenceNumber
from cmb_protocol.tfrc import TFRCSender, LossEventRateCalculator


# called s in TFRC, in bytes
from cmb_protocol.timestamp import Timestamp
from cmb_protocol.trio_util import Timer

SEGMENT_SIZE = Packet.PACKET_TYPE_SIZE + Data.HEADER_SIZE + RAPTORQ_HEADER_SIZE + MAXIMUM_TRANSMISSION_UNIT


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
    PacketMeta = namedtuple('PacketMeta', ['rtt', 'timestamp', 'sequence_number', 'received_at'])

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

        self.spawn(self.init_protocol)

        # TFRC parameters
        self.loss_event_rate_calculator = LossEventRateCalculator()
        self.feedback_timer = Timer(self.spawn)
        self.feedback_timer.add_listener(self.handle_feedback_timer_expired)
        self.sender_params = None
        self.packet_count = 0
        self.feedback_timer_last_expired = None

    async def init_protocol(self):
        flags = RequestResourceFlags.REVERSE if self.reverse else RequestResourceFlags.NONE
        resource_request = RequestResource(flags=flags,
                                           resource_id=self.resource_id,
                                           block_offset=self.offset)
        await self.send(resource_request)

    async def handle_data(self, packet):
        if self.sender_params is None:
            # first data packet
            await self.send(Feedback(delay=0, timestamp=packet.timestamp, receive_rate=0, loss_event_rate=0))
        elif self.sender_params.rtt == 0:
            # feedback timer has not been set yet
            if packet.estimated_rtt != 0:
                self.feedback_timer.reset(packet.estimated_rtt)

            receive_rate = SEGMENT_SIZE / (Timestamp.now() - self.sender_params.received_at)
            await self.send(Feedback(delay=0, timestamp=packet.timestamp, receive_rate=receive_rate,
                                     loss_event_rate=self.loss_event_rate_calculator.loss_event_rate))

        self.packet_count += 1
        if self.feedback_timer_last_expired is None:
            self.feedback_timer_last_expired = Timestamp.now()

        if self.sender_params is None or packet.sequence_number > self.sender_params.sequence_number:
            self.sender_params = self.PacketMeta(rtt=packet.estimated_rtt, timestamp=packet.timestamp,
                                                 sequence_number=packet.sequence_number, received_at=Timestamp.now())

        previous_loss_event_rate = self.loss_event_rate_calculator.loss_event_rate
        self.loss_event_rate_calculator.update(packet.sequence_number, packet.estimated_rtt)
        if self.loss_event_rate_calculator.loss_event_rate > previous_loss_event_rate:
            self.feedback_timer.expire()
        # TODO: other conditions

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

    def handle_feedback_timer_expired(self, expired_early):
        # RFC 5348 Section 6.2
        self.loss_event_rate_calculator.recalculate()
        receive_rate = self.packet_count * SEGMENT_SIZE / (Timestamp.now() - self.feedback_timer_last_expired)

        if not expired_early:
            self.packet_count = 0

        self.spawn(self.send_feedback, receive_rate, self.sender_params)
        self.feedback_timer.reset(self.sender_params.rtt)

    async def send_feedback(self, receive_rate, sender_params):
        delay = Timestamp.now() - sender_params.received_at
        await self.send(Feedback(delay=delay, timestamp=sender_params.timestamp, receive_rate=receive_rate,
                                 loss_event_rate=self.loss_event_rate_calculator.loss_event_rate))

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
            await self.send(AckOppositeRange(stop_at_block_id=stop_at_block_id))

    def shutdown(self):
        super().shutdown()
        self.feedback_timer.clear_listeners()


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
        self.connected = False
        self.reverse = None
        self.stop_at_block_id = None

        self.tfrc = TFRCSender(SEGMENT_SIZE)

    async def handle_feedback(self, packet):
        params = packet.delay, packet.timestamp, packet.receive_rate, packet.loss_event_rate
        self.tfrc.handle_feedback(*params)

    async def handle_request_resource(self, packet):
        if self.resource_id != packet.resource_id:
            await self.send(Error(ErrorCode.RESOURCE_NOT_FOUND))
            self.shutdown()
        elif not self.connected:
            self.reverse = packet.flags is RequestResourceFlags.REVERSE
            self.connected = True
            self.stop_at_block_id = -1 if self.reverse else len(self.encoders)
            self.spawn(self.send_blocks)
        else:
            pass  # already connected and sending

    async def send_blocks(self):
        def packets():
            for block_id, encoder in reversed(self.encoders.items()) if self.reverse else self.encoders.items():
                for fec_data in encoder.source_packets:
                    # check in every iteration if we have received a stop signal in the meantime
                    finished = self.stop_at_block_id >= block_id if self.reverse else self.stop_at_block_id <= block_id
                    if finished:
                        return

                    yield block_id, fec_data

        packet_iter = packets()

        async for timestamp, rtt, sequence_number in self.tfrc.sending_credits:
            try:
                block_id, fec_data = next(packet_iter)
                packet = Data(block_id, timestamp, rtt, sequence_number, fec_data)
                await self.send(packet)
            except StopIteration:
                return

    async def handle_ack_block(self, packet):
        pass

    async def handle_nack_block(self, packet):
        pass

    async def handle_ack_opposite_range(self, packet):
        current, new = self.stop_at_block_id, packet.stop_at_block_id
        recent = current <= new if self.reverse else current >= new
        if recent:
            self.stop_at_block_id = new

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
        elif isinstance(packet, AckOppositeRange):
            await self.handle_ack_opposite_range(packet)
        elif isinstance(packet, Feedback):
            await self.handle_feedback(packet)
