import math
import trio

from collections import namedtuple
from abc import ABC

from cmb_protocol.coding import Decoder, RAPTORQ_HEADER_SIZE
from cmb_protocol.constants import MAXIMUM_TRANSMISSION_UNIT, calculate_number_of_blocks, calculate_block_size
from cmb_protocol.helpers import calculate_time_elapsed
from cmb_protocol.packets import RequestResourceFlags, RequestResource, AckBlock, NackBlock, AckOppositeRange, Data, \
    Error, ErrorCode, Packet, Feedback

from cmb_protocol.trio_util import Timer


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


class ReceiveRateSet:
    Entry = namedtuple('RecvSetEntry', ['timestamp', 'receive_rate'])

    def __init__(self, receive_rate=math.inf, timestamp=0):
        self._entries = [self.Entry(timestamp=timestamp, receive_rate=receive_rate)]

    def halve(self):
        self._entries = [(timestamp, recv / 2) for timestamp, recv in self._entries]

    def maximize(self, receive_rate, timestamp):
        self._append(self.Entry(timestamp=timestamp, receive_rate=receive_rate))
        # delete initial receive_rate Infinity if it is still a member
        if self._entries[0].receive_rate == math.inf:
            del self._entries[0]
        # set the timestamp of the largest item to the current time, delete all other items
        self._entries = [self.Entry(timestamp=timestamp, receive_rate=self.max_receive_rate)]

    @property
    def max_receive_rate(self):
        return max(receive_rate for _, receive_rate in self._entries)

    def update(self, receive_rate, timestamp, rtt):
        self._append(self.Entry(timestamp=timestamp, receive_rate=receive_rate))
        # delete receive_rates older than two round-trip times
        self._entries = [recv for recv in self._entries if calculate_time_elapsed(recv.timestamp, timestamp) < 2 * rtt]

    def _append(self, entry):
        self._entries.append(entry)
        # limit set to 3 most recent entries
        if len(self._entries) > 3:
            del self._entries[:-3]


class ServerSideConnection(Connection):
    MAXIMUM_BACKOFF_INTERVAL = 64  # t_mbi, in seconds
    SCHEDULING_GRANULARITY = 0.001

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

        # TFRC parameters, RFC 5348 Section 4.2
        self.allowed_sending_rate = SEGMENT_SIZE  # X, in bytes per second
        self.initial_allowed_sending_rate = None
        self.time_last_doubled = 0  # tld, during slow-start, in seconds
        self.rtt = None  # R
        self.rto = None
        # list of tuples with timestamp in seconds and estimated receive rate at the receiver
        self.recv_set = ReceiveRateSet()
        self.loss_event_rate = 0  # p
        self.tcp_sending_rate = None  # X_bps
        # data-limited interval
        self.not_limited1 = self.not_limited2 = self.t_new = self.t_next = 0
        self.data_limited = False

        self.no_feedback_timer = Timer(self.spawn)
        self.no_feedback_timer.add_listener(self.handle_no_feedback_timer_expired)

    @property
    def current_timestamp(self):  # in seconds
        return calculate_time_elapsed(self.initial_timestamp, trio.current_time())

    def shutdown(self):
        self.no_feedback_timer.clear_listeners()
        super().shutdown()

    def handle_no_feedback_timer_expired(self):
        # RFC 5348 Section 4.4
        receive_rate = self.recv_set.max_receive_rate

        def update_limits(timer_limit):
            if timer_limit < SEGMENT_SIZE / self.MAXIMUM_BACKOFF_INTERVAL:
                timer_limit = SEGMENT_SIZE / self.MAXIMUM_BACKOFF_INTERVAL
            self.recv_set = ReceiveRateSet(receive_rate=timer_limit / 2, timestamp=self.current_timestamp)
            self.update_allowed_sending_rate(receive_rate)

        if self.rtt is None or self.loss_event_rate == 0:
            self.allowed_sending_rate = max(self.allowed_sending_rate / 2, SEGMENT_SIZE / self.MAXIMUM_BACKOFF_INTERVAL)
        # elif "sender has been idle ever since no_feedback_timer was set" never happens in our case
        elif self.tcp_sending_rate > 2 * receive_rate:
            update_limits(receive_rate)
        else:
            update_limits(self.tcp_sending_rate / 2)

        self.no_feedback_timer.reset(max(4 * self.rtt, 2 * SEGMENT_SIZE / self.allowed_sending_rate))

    def update_rtt(self, timestamp, delay):  # timestamp in seconds, delay in seconds
        r_sample = calculate_time_elapsed(timestamp, self.current_timestamp) - delay
        q = 0.9
        self.rtt = r_sample if self.rtt is None else q * self.rtt + (1 - q) * r_sample

    def update_allowed_sending_rate(self, receive_rate, previous_loss_event_rate=None):
        # RFC 5348 Section 4.3
        if previous_loss_event_rate is None:
            previous_loss_event_rate = self.loss_event_rate
        if self.data_limited:
            if previous_loss_event_rate < self.loss_event_rate:  # TODO: regard NACKs as well
                self.recv_set.halve()
                receive_rate *= 0.85
                self.recv_set.maximize(receive_rate, self.current_timestamp)
                recv_limit = self.recv_set.max_receive_rate
            else:
                self.recv_set.maximize(receive_rate, self.current_timestamp)
                recv_limit = self.recv_set.max_receive_rate
        else:
            self.recv_set.update(receive_rate, self.current_timestamp, self.rtt)
            recv_limit = 2 * self.recv_set.max_receive_rate

        if self.loss_event_rate > 0:
            self.tcp_sending_rate = SEGMENT_SIZE / (self.rtt * math.sqrt(2 * self.loss_event_rate / 3) + (self.rto * (
                        3 * math.sqrt(3 * self.loss_event_rate / 8) * self.loss_event_rate * (1 + 32 * self.loss_event_rate ** 2))))
            self.allowed_sending_rate = max(min(self.tcp_sending_rate, recv_limit),
                                            SEGMENT_SIZE / self.MAXIMUM_BACKOFF_INTERVAL)
        elif calculate_time_elapsed(self.time_last_doubled, self.current_timestamp) >= self.rtt:
            self.allowed_sending_rate = max(min(2 * self.allowed_sending_rate, recv_limit),
                                            self.initial_allowed_sending_rate)
            self.time_last_doubled = self.current_timestamp

    async def handle_feedback(self, packet):
        # RFC 5348 Section 4.3
        delay, timestamp, receive_rate, loss_event_rate = packet.delay / 1000, packet.timestamp / 1000, \
                                                          packet.receive_rate, packet.loss_event_rate
        previous_rtt = self.rtt
        self.update_rtt(timestamp, delay)
        previous_loss_event_rate, self.loss_event_rate = self.loss_event_rate, loss_event_rate
        self.rto = max(4 * self.rtt, 2 * SEGMENT_SIZE / self.allowed_sending_rate)

        if previous_rtt is None:
            # RFC 5348 Section 4.2
            w_init = min(4 * SEGMENT_SIZE, max(2 * SEGMENT_SIZE, 4380))
            self.initial_allowed_sending_rate = self.allowed_sending_rate = w_init / self.rtt
            self.time_last_doubled = self.current_timestamp
        else:
            self.update_allowed_sending_rate(receive_rate, previous_loss_event_rate)

        # TODO: for oscillation: cf. RFC 5348 Section 4.5

        self.no_feedback_timer.reset(self.rto)

        # RFC 5348 Section 8.2.1
        self.t_new = timestamp
        t_old = calculate_time_elapsed(self.rtt, self.t_new)
        self.t_next = self.current_timestamp
        self.data_limited = not (t_old < self.not_limited1 <= self.t_new or t_old < self.not_limited2 <= self.t_new)

        if self.not_limited1 <= self.t_new < self.not_limited2:
            self.not_limited1 = self.not_limited2

    async def handle_request_resource(self, packet):
        if self.resource_id != packet.resource_id:
            await self.send(Error(ErrorCode.RESOURCE_NOT_FOUND))
            self.shutdown()
        elif not self.connected:
            self.reverse = packet.flags is RequestResourceFlags.REVERSE
            self.connected = True
            self.stop_at_block_id = -1 if self.reverse else len(self.encoders)
            self.no_feedback_timer.reset(2)
            self.spawn(self.send_blocks)
        else:
            pass  # already connected and sending

    async def send_blocks(self):
        def packets():
            sequence_number = 0
            for block_id, encoder in reversed(self.encoders.items()) if self.reverse else self.encoders.items():
                for fec_data in encoder.source_packets:
                    # check in every iteration if we have received a stop signal in the meantime
                    finished = self.stop_at_block_id >= block_id if self.reverse else self.stop_at_block_id <= block_id
                    if finished:
                        return

                    timestamp = self.current_timestamp * 1000
                    yield Data(block_id=block_id,
                               timestamp=timestamp,
                               estimated_rtt=0,
                               sequence_number=sequence_number,
                               fec_data=fec_data)
                    sequence_number = (sequence_number + 1) % (2 ** 24)

        packet_iter = packets()

        # RFC 5348 Section 4.6, 8.2, and 8.3
        t = trio.current_time()  # set t_0
        while True:
            t_inter_packet_interval = SEGMENT_SIZE / self.allowed_sending_rate
            t_delta = min(t_inter_packet_interval, self.SCHEDULING_GRANULARITY, self.rtt if self.rtt is not None else math.inf) / 2
            if trio.current_time() > t - t_delta:
                try:
                    packet = next(packet_iter)
                    await self.send(packet)
                    t += t_inter_packet_interval  # set t_(i+1)
                except StopIteration:
                    self.shutdown()
                    return
            else:
                # sender is not data-limited at this instant
                if self.not_limited1 <= self.t_new:
                    # goal: self.not_limited1 > self.t_new
                    self.not_limited1 = self.t_new
                elif self.not_limited2 <= self.t_next:
                    # goal: self.not_limited2 > self.t_next
                    self.not_limited2 = self.current_timestamp

                await trio.sleep(self.SCHEDULING_GRANULARITY)

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
