import math
from collections import namedtuple

import trio
from abc import ABC

from cmb_protocol.coding import Decoder, RAPTORQ_HEADER_SIZE
from cmb_protocol.constants import MAXIMUM_TRANSMISSION_UNIT, SYMBOLS_PER_BLOCK, calculate_number_of_blocks, \
    calculate_block_size
from cmb_protocol.packets import RequestResourceFlags, RequestResource, AckBlock, NackBlock, AckOppositeRange, Data, \
    Error, ErrorCode, Packet, Feedback

# called s in TFRC, in bytes
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
        self.shutdown = shutdown
        self.spawn = spawn
        self.send = send

    async def handle_packet(self, packet):
        """
        Called by the receiving loop upon packet receipt.
        The loop should await this method to propagate back pressure.
        If this method needs to do anything else other than responding with a packet,
        it should spawn a background task.
        :param packet:  the received packet
        """
        self.shutdown()


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

        self.spawn(self.init_protocol)

    async def init_protocol(self):
        flags = RequestResourceFlags.REVERSE if self.reverse else RequestResourceFlags.NONE
        resource_request = RequestResource(flags=flags,
                                           resource_id=self.resource_id,
                                           block_offset=self.offset)
        await self.send(resource_request)

    async def handle_data(self, packet):
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


RecvSetEntry = namedtuple('RecvSetEntry', ['timestamp', 'value'])


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
        self.initial_timestamp = trio.current_time()

        # TFRC parameters
        self.allowed_sending_rate = SEGMENT_SIZE  # X, in bytes per second
        self.time_last_doubled = 0  # tld, during slow-start, in seconds
        self.no_feedback_timer_cancel_scope = None
        self.initial_no_feedback_timer_cancel_scope_deadline = None
        self.set_no_feedback_timer(2000)  # in milliseconds
        self.rtt = None  # R
        self.received_initial_feedback = False
        # list of tuples with timestamp and estimated receive rate at the receiver
        self.recv_set = [RecvSetEntry(timestamp=0, value=math.inf)]
        self.loss_event_rate = 0

    def set_no_feedback_timer(self, timeout):
        deadline = trio.current_time() + timeout / 1000  # trio needs seconds

        async def init():
            with trio.CancelScope(deadline=self.initial_no_feedback_timer_cancel_scope_deadline) as cancel_scope:
                self.no_feedback_timer_cancel_scope = cancel_scope
                await trio.sleep_forever()
            self.no_feedback_timer_cancel_scope = None
            self.initial_no_feedback_timer_cancel_scope_deadline = None
            self.handle_no_feedback_timer_expired()

        if self.no_feedback_timer_cancel_scope is None:
            old_deadline = self.initial_no_feedback_timer_cancel_scope_deadline
            self.initial_no_feedback_timer_cancel_scope_deadline = deadline
            if old_deadline is None:
                self.spawn(init)
        else:
            self.no_feedback_timer_cancel_scope.deadline = deadline

    def handle_no_feedback_timer_expired(self):
        pass

    @property
    def current_timestamp(self):
        return int((trio.current_time() - self.initial_timestamp) * 1000) % (2 ** 24)

    def update_rtt(self, timestamp, delay):
        r_sample = (self.current_timestamp - timestamp) % (2 ** 24) - delay
        q = 0.9
        self.rtt = r_sample if self.rtt is None else q * self.rtt + (1 - q) * r_sample

    def halve_recv_set(self):
        self.recv_set = [(timestamp, recv / 2) for timestamp, recv in self.recv_set]

    def maximize_recv_set(self, receive_rate):
        self.recv_set.append(RecvSetEntry(timestamp=self.current_timestamp, value=receive_rate))
        # delete initial value Infinity from X_recv_set, if it is still a member
        if self.recv_set[0].value == math.inf:
            del self.recv_set[0]

        self.recv_set = [RecvSetEntry(timestamp=self.current_timestamp, value=self.max_recv_value)]

    @property
    def max_recv_value(self):
        return max(value for _, value in self.recv_set)

    def update_recv_set(self, receive_rate):
        ts = self.current_timestamp
        self.recv_set.append(RecvSetEntry(timestamp=ts, value=receive_rate))
        # delete from X_recv_set values older than two round-trip times
        self.recv_set = [recv for recv in self.recv_set if (ts - recv.timestamp) % (2 ** 24) < 2 * self.rtt]

    async def handle_feedback(self, packet):
        delay, timestamp, receive_rate, loss_event_rate = packet.delay, packet.timestamp, packet.receive_rate, \
                                                          packet.loss_event_rate
        self.update_rtt(timestamp, delay)
        previous_loss_event_rate, self.loss_event_rate = self.loss_event_rate, loss_event_rate
        rto = max(4 * self.rtt, 2 * SEGMENT_SIZE / self.allowed_sending_rate)

        if not self.received_initial_feedback:
            self.received_initial_feedback = True
            w_init = min(4 * SEGMENT_SIZE, max(2 * SEGMENT_SIZE, 4380))
            self.allowed_sending_rate = w_init / self.rtt
            self.time_last_doubled = trio.current_time()
        else:
            t_mbi = 64 * 1000  # maximum backoff interval in milliseconds
            recv_limit = None
            if True:  # TODO: calculate condition
                if previous_loss_event_rate < loss_event_rate:  # TODO: regard NACKs as well
                    self.halve_recv_set()
                    receive_rate *= 0.85
                    self.maximize_recv_set(receive_rate)
                    recv_limit = self.max_recv_value
            else:
                pass  # TODO: continue

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
        sequence_number = 0
        try:
            for block_id, encoder in reversed(self.encoders.items()) if self.reverse else self.encoders.items():
                for fec_data in encoder.source_packets:
                    # check in every iteration if we have received a stop signal in the meantime
                    finished = self.stop_at_block_id >= block_id if self.reverse else self.stop_at_block_id <= block_id
                    if finished:
                        return

                    timestamp = self.current_timestamp
                    packet = Data(block_id=block_id,
                                  timestamp=timestamp,
                                  estimated_rtt=0,
                                  sequence_number=sequence_number,
                                  fec_data=fec_data)
                    sequence_number = (sequence_number + 1) % (2 ** 24)
                    await self.send(packet)
                    await trio.sleep(0.01)
        finally:
            self.shutdown()

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
