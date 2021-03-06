from abc import ABC
from collections import namedtuple
from heapq import heappush, heappop

import trio
from recordclass import recordclass

from cmb_protocol import log_util
from cmb_protocol.coding import Decoder, RAPTORQ_HEADER_SIZE
from cmb_protocol.constants import MAXIMUM_TRANSMISSION_UNIT, calculate_number_of_blocks, calculate_block_size, \
    HEARTBEAT_INTERVAL, SCHEDULING_GRANULARITY
from cmb_protocol.helpers import is_reversed, directed_range, format_resource_id
from cmb_protocol.log_util import get_logging_context
from cmb_protocol.packets import RequestResource, AckBlock, NackBlock, ShrinkRange, Data, Error, ErrorCode, Packet
from cmb_protocol.timestamp import Timestamp


logger = log_util.get_logger(__name__)


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


BlockMetadata = recordclass('BlockMetadata', ['packets_received', 'decoder', 'nack_timestamp'])


class ClientSideConnection(Connection):
    def __init__(self, shutdown, spawn, send, write_block, resource_id, sending_rate, reverse):
        """
        :param shutdown:     cf. Connection
        :param spawn:        cf. Connection
        :param send:         cf. Connection
        :param write_block:  async function for writing a block to the output
        :param resource_id:  the id of the resource
        :param sending_rate: sending rate in bps
        :param reverse:      bool whether this connection should request the blocks in reverse order
        """
        super().__init__(shutdown, spawn, send)
        self.write_block = write_block
        self.sending_rate = sending_rate
        self.resource_id = resource_id
        self.reverse = reverse

        _, resource_length = self.resource_id
        last_block_id = calculate_number_of_blocks(resource_length)  # block id starts at 1

        self.block_range_start = last_block_id if self.reverse else 1  # inclusive
        self.block_range_end = 0 if self.reverse else last_block_id + 1  # exclusive

        self.acknowledged_blocks = dict()  # block_id -> time of ACK sent
        self.not_acknowledged_blocks = dict()  # block_id -> (#packets received, decoder, time of NACK sent)

        self.head_of_line_blocked = set()  # block_ids
        self.opposite_head_of_line_blocked = set()  # block_ids

        self.rtt = None
        self.cancel_scope = None

        self.spawn(self.keep_connection_alive)

    @property
    def active_block_range(self):
        return directed_range(self.block_range_start, self.block_range_end)

    def shutdown(self):
        super().shutdown()
        self.cancel_scope.cancel()

    async def keep_connection_alive(self):
        with trio.CancelScope() as cancel_scope:
            self.cancel_scope = cancel_scope
            while True:
                resource_request = RequestResource(timestamp=Timestamp.now(),
                                                   sending_rate=self.sending_rate,
                                                   block_range_start=self.block_range_start,
                                                   resource_id=self.resource_id,
                                                   block_range_end=self.block_range_end)
                await self.send(resource_request)
                await trio.sleep(HEARTBEAT_INTERVAL)

    async def check_could_decode_previous(self, block_id):
        block_metadata = self.not_acknowledged_blocks[block_id]
        for previous_block_id in directed_range(self.block_range_start, block_id):
            if previous_block_id not in self.not_acknowledged_blocks:
                # did decode block already, block is head of line blocked
                continue

            distance = abs(block_id - previous_block_id)  # if reversed, difference might be negative
            if distance < 2 and block_metadata.packets_received < 3:
                # does not fulfill packet loss criteria
                continue

            inter_packet_arrival_time = SEGMENT_SIZE / self.sending_rate
            # add inter packet arrival time in case the sender is sending less than 1 packet every 4 RTTs
            nack_resend_timeout = 4 * self.rtt + inter_packet_arrival_time
            previous_block_metadata = self.not_acknowledged_blocks[previous_block_id]
            if previous_block_metadata.nack_timestamp is not None \
                    and Timestamp.now() - previous_block_metadata.nack_timestamp < nack_resend_timeout:
                # did send nack recently
                continue

            previous_block_metadata.nack_timestamp = Timestamp.now()
            await self.send(NackBlock(block_id=previous_block_id,
                                      received_packets=previous_block_metadata.packets_received))
            logger.debug('Sent NACK %d', previous_block_id)

    def advance_head_of_line(self, block_id):
        if block_id > self.block_range_start if self.reverse else block_id < self.block_range_start:
            return False
        elif block_id == self.block_range_start:
            self.block_range_start += -1 if self.reverse else 1
            while self.block_range_start in self.head_of_line_blocked:
                self.head_of_line_blocked.remove(self.block_range_start)
                self.block_range_start += -1 if self.reverse else 1

            # safeguard against overshooting the range end
            self.block_range_start = \
                max(self.block_range_start, self.block_range_end) \
                if self.reverse else \
                min(self.block_range_start, self.block_range_end)

            return True
        else:
            self.head_of_line_blocked.add(block_id)
            return False

    def advance_opposite_head_of_line(self, block_id):
        def _last_block_id():
            return self.block_range_end + 1 if self.reverse else self.block_range_end - 1

        if block_id <= self.block_range_end if self.reverse else block_id >= self.block_range_end:
            return False
        elif block_id == _last_block_id():
            self.block_range_end += 1 if self.reverse else -1
            while _last_block_id() in self.opposite_head_of_line_blocked:
                self.opposite_head_of_line_blocked.remove(_last_block_id())
                self.block_range_end += 1 if self.reverse else -1

            # safeguard against overshooting the range start
            self.block_range_end = \
                min(self.block_range_start, self.block_range_end) \
                if self.reverse else \
                max(self.block_range_start, self.block_range_end)

            return True
        else:
            self.opposite_head_of_line_blocked.add(block_id)
            return False

    async def handle_data(self, packet):
        rtt_sample = Timestamp.now() - packet.timestamp - packet.delay
        self.rtt = rtt_sample if self.rtt is None else 0.9 * self.rtt + 0.1 * rtt_sample

        if packet.block_id in self.active_block_range and packet.block_id not in self.acknowledged_blocks:
            if packet.block_id not in self.not_acknowledged_blocks:
                _, resource_length = self.resource_id
                block_size = calculate_block_size(resource_length, packet.block_id)
                decoder = Decoder(block_size, MAXIMUM_TRANSMISSION_UNIT)
                block_metadata = BlockMetadata(packets_received=0, decoder=decoder, nack_timestamp=None)
                self.not_acknowledged_blocks[packet.block_id] = block_metadata

            block_metadata = self.not_acknowledged_blocks[packet.block_id]
            block_metadata.packets_received += 1
            if block_metadata.nack_timestamp is not None:
                # reset nack send timeout
                block_metadata.nack_timestamp = Timestamp.now()

            decoded_block = block_metadata.decoder.decode([packet.fec_data])

            await self.check_could_decode_previous(packet.block_id)

            if decoded_block:
                del self.not_acknowledged_blocks[packet.block_id]

                self.advance_head_of_line(packet.block_id)
                self.acknowledged_blocks[packet.block_id] = Timestamp.now()

                await self.send(AckBlock(block_id=packet.block_id))
                logger.debug('Sent ACK %d', packet.block_id)
                await self.write_block(packet.block_id, decoded_block)

                if self.block_range_start == self.block_range_end:
                    self.shutdown()

        elif packet.block_id in self.acknowledged_blocks \
                and Timestamp.now() - self.acknowledged_blocks[packet.block_id] > 4 * self.rtt:
            # acknowledgement got lost
            self.acknowledged_blocks[packet.block_id] = Timestamp.now()
            await self.send(AckBlock(block_id=packet.block_id))
            logger.debug('Sent duplicate ACK %d', packet.block_id)

    def handle_error(self, packet):
        if ErrorCode.RESOURCE_NOT_FOUND == packet.error_code:
            raise ValueError('Resource {} not found on {}'.format(format_resource_id(self.resource_id),
                                                                  get_logging_context('remote_address')))

    async def handle_packet(self, packet):
        """
        Called by the receiving loop upon packet receipt.
        cf. Connection
        """
        if isinstance(packet, Data):
            await self.handle_data(packet)
        elif isinstance(packet, Error):
            self.handle_error(packet)

    async def send_stop(self, block_id):
        """
        Called by the higher order protocol instance after receiving a block from the opposing connection
        :param block_id: the id of the block which has been received
        """
        if self.advance_opposite_head_of_line(block_id):
            await self.send(ShrinkRange(block_range_start=self.block_range_start, block_range_end=self.block_range_end))
        if self.block_range_start == self.block_range_end:
            self.shutdown()


PendingNack = namedtuple('PendingNack', ['block_id', 'repair_count'])


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
        self.repair_packet_generators = dict()  # block_id -> repair packet iterator
        self.acknowledged_blocks = set()
        self.connected = False

        self.block_range_start = None
        self.block_range_end = None
        self.sending_rate = None
        self.recent_receiver_timestamp = None

        self.keep_alive_received_at = None

        self.nack_heap = []  # defines nack processing order
        self.pending_nacks = set()  # block_id

    @property
    def block_range_reversed(self):
        return self.connected and is_reversed(self.block_range_start, self.block_range_end)

    @property
    def active_block_range(self):
        return directed_range(self.block_range_start, self.block_range_end)

    def generate_next_repair_packet(self, block_id):
        if block_id not in self.repair_packet_generators:
            encoder = self.encoders[block_id]
            self.repair_packet_generators[block_id] = encoder.repair_packets()

        return block_id, next(self.repair_packet_generators[block_id])

    def generate_packets(self):
        for block_id in self.active_block_range:
            # check in every outer iteration if we have received a stop signal in the meantime
            if block_id in self.acknowledged_blocks or block_id not in self.active_block_range:
                continue

            encoder = self.encoders[block_id]
            for fec_data in encoder.source_packets():
                # check in every inner iteration if we have received a stop signal in the meantime
                if block_id in self.acknowledged_blocks or block_id not in self.active_block_range:
                    break

                yield block_id, fec_data

        # preemptive repair phase, send repair packets is round robin until everything has been acknowledged
        logger.debug('Exhausted source packets, starting preemptive repair phase')
        yield from self.generate_preemptive_repair_packets()

    def generate_preemptive_repair_packets(self):
        while True:
            repair_packets_generated = 0
            for block_id in self.active_block_range:
                # check if we have received a stop signal in the meantime
                if block_id in self.acknowledged_blocks or block_id not in self.active_block_range:
                    continue

                # generate next repair packet
                yield self.generate_next_repair_packet(block_id)
                repair_packets_generated += 1

            if repair_packets_generated == 0:
                # all blocks have been acknowledged
                return
            else:
                logger.debug('Generated %d repair packets', repair_packets_generated)

    def generate_repair_packets(self):
        while True:
            if len(self.nack_heap) > 0:
                _, (block_id, repair_count) = heappop(self.nack_heap)

                for _ in range(repair_count):
                    # check if we have received a stop signal in the meantime
                    if block_id in self.acknowledged_blocks or block_id not in self.active_block_range:
                        break

                    yield self.generate_next_repair_packet(block_id)

                self.pending_nacks.remove(block_id)
                logger.debug('Sent repair %d', block_id)
            else:
                yield None, None

    async def send_blocks(self):
        try:
            packet_generator = self.generate_packets()
            repair_packet_generator = self.generate_repair_packets()
            send_time = Timestamp.now()
            while True:
                if Timestamp.now() - self.keep_alive_received_at > 4 * HEARTBEAT_INTERVAL:
                    logger.debug('Connection timed out')
                    return  # connection is broken, shutdown

                if Timestamp.now() < send_time:
                    await trio.sleep(SCHEDULING_GRANULARITY)
                else:
                    try:
                        block_id, fec_data = next(repair_packet_generator)  # prioritize repair over source packets
                        if not fec_data:
                            block_id, fec_data = next(packet_generator)
                    except StopIteration:
                        break  # all source packets have been sent
                    else:
                        packet = Data(block_id=block_id,
                                      timestamp=self.recent_receiver_timestamp,
                                      delay=Timestamp.now() - self.keep_alive_received_at,
                                      fec_data=fec_data)
                        await self.send(packet)
                        send_time += SEGMENT_SIZE / self.sending_rate
        finally:
            self.shutdown()

    def shrink_range(self, block_range_start, block_range_end):
        block_range_reversed = is_reversed(block_range_start, block_range_end)
        if block_range_start == block_range_end:
            self.block_range_end = self.block_range_start = block_range_start
        elif self.block_range_reversed and block_range_reversed:
            if self.block_range_end < block_range_end:
                self.block_range_end = block_range_end
            if self.block_range_start > block_range_start:
                self.block_range_start = block_range_start
        elif not self.block_range_reversed and not block_range_reversed:
            if self.block_range_start < block_range_start:
                self.block_range_start = block_range_start
            if self.block_range_end > block_range_end:
                self.block_range_end = block_range_end
        else:
            logger.warning('Ranges [%d:%d) and [%d:%d) have opposing direction',
                           self.block_range_start, self.block_range_end, block_range_start, block_range_end)
        logger.debug('Set range [%d, %d)', self.block_range_start, self.block_range_end)

    async def handle_request_resource(self, packet):
        if self.resource_id != packet.resource_id:
            await self.send(Error(ErrorCode.RESOURCE_NOT_FOUND))
            self.shutdown()
            return

        logger.debug('Received keep alive')

        self.keep_alive_received_at = Timestamp.now()
        self.sending_rate = packet.sending_rate
        self.recent_receiver_timestamp = packet.timestamp

        if not self.connected:
            self.block_range_start = packet.block_range_start
            self.block_range_end = packet.block_range_end
            self.connected = True
            self.spawn(self.send_blocks)
        else:
            self.shrink_range(packet.block_range_start, packet.block_range_end)

    def handle_ack_block(self, packet):
        self.acknowledged_blocks.add(packet.block_id)

    def handle_nack_block(self, packet):
        if packet.block_id not in self.pending_nacks:
            logger.debug('Received NACK %d', packet.block_id)
            priority = -packet.block_id if self.block_range_reversed else packet.block_id
            repair_count = max(2, self.encoders[packet.block_id].minimum_packet_count - packet.received_packets)
            heappush(self.nack_heap, (priority, PendingNack(block_id=packet.block_id, repair_count=repair_count)))
            self.pending_nacks.add(packet.block_id)

    def handle_shrink_range(self, packet):
        self.shrink_range(packet.block_range_start, packet.block_range_end)

    async def handle_packet(self, packet):
        """
        Called by the receiving loop upon packet receipt.
        cf. Connection
        """
        if isinstance(packet, RequestResource):
            await self.handle_request_resource(packet)
        elif isinstance(packet, AckBlock):
            self.handle_ack_block(packet)
        elif isinstance(packet, NackBlock):
            self.handle_nack_block(packet)
        elif isinstance(packet, ShrinkRange):
            self.handle_shrink_range(packet)
