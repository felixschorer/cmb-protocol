import math
from collections import namedtuple

import trio
from async_generator import async_generator, yield_

from cmb_protocol import log_util
from cmb_protocol.sequencenumber import SequenceNumber
from cmb_protocol.timestamp import Timestamp

logger = log_util.get_logger(__name__)

NDUPACK = 3
NUMBER_OF_LOSS_INTERVALS = 8


class Event:
    def __init__(self):
        self.listeners = set()

    def __iadd__(self, other):
        self.listeners.add(other)
        return self

    def __isub__(self, other):
        self.listeners.remove(other)
        return self

    def clear(self):
        self.listeners.clear()

    def trigger(self, *args, **kwargs):
        for listener in self.listeners:
            listener(*args, **kwargs)


class TFRCReceiver:
    Entry = namedtuple('Entry', ['timestamp', 'sequence_number'])
    PacketMeta = namedtuple('PacketMeta', ['rtt', 'timestamp', 'sequence_number', 'received_at'])

    def __init__(self, segment_size, feedback_timer):
        self._segment_size = segment_size
        self._feedback_timer = feedback_timer
        self._feedback_timer += self._handle_feedback_timer_expired
        self._sender_params = None
        self._packet_count = 0
        self._feedback_timer_last_expired = None
        self._sent_feedback = False
        self._max_receive_rate = 0
        # initialize with -1 to be able to detect the packet with sequence number 0
        self._received_sequence_numbers = [self.Entry(timestamp=Timestamp.now(), sequence_number=SequenceNumber(-1))]
        self._loss_events = []
        self._rtt = 0
        self._loss_event_rate = 0

        self.feedback_handler = Event()
        self.rtt_updated = Event()

    def handle_data(self, timestamp, rtt, sequence_number):
        if rtt != 0:
            self.rtt_updated.trigger(rtt)
            self._rtt = rtt

        self._packet_count += 1
        if self._feedback_timer_last_expired is None:
            self._feedback_timer_last_expired = Timestamp.now()

        if self._sender_params is None or sequence_number > self._sender_params.sequence_number:
            self._sender_params = self.PacketMeta(rtt=rtt, timestamp=timestamp,
                                                  sequence_number=sequence_number, received_at=Timestamp.now())

        if self._sender_params is None or self._sender_params.rtt == 0:
            # feedback timer has not been set yet
            if rtt != 0:
                self._feedback_timer.reset(rtt)

            self.feedback_handler.trigger(delay=0, timestamp=timestamp, receive_rate=0, loss_event_rate=0)
        else:
            previous_loss_event_rate = self._loss_event_rate
            self._update_loss_history(sequence_number)
            if self._loss_event_rate > previous_loss_event_rate or not self._sent_feedback:
                self._feedback_timer.expire()

    def _update_loss_history(self, sequence_number):
        # RFC 5348 Section 5.1
        self._received_sequence_numbers.append(self.Entry(timestamp=Timestamp.now(), sequence_number=sequence_number))
        self._received_sequence_numbers.sort(key=lambda x: x.sequence_number)
        if len(self._received_sequence_numbers) == NDUPACK + 1:
            before, after = self._received_sequence_numbers[:2]
            # RFC 5348 Section 5.2
            for loss_sequence_number in range(before.sequence_number.value + 1, after.sequence_number.value):
                loss_sequence_number = SequenceNumber(loss_sequence_number)
                loss_timestamp = before.timestamp + (after.timestamp - before.timestamp) * (
                        loss_sequence_number - before.sequence_number) / (
                                         after.sequence_number - before.sequence_number)
                if len(self._loss_events) == 0 or self._loss_events[
                    0].timestamp + self._rtt < loss_timestamp:  # TODO: what happens if rtt is 0?
                    # start new loss event, insert at index 0
                    self._loss_events.insert(0,
                                             self.Entry(timestamp=loss_timestamp, sequence_number=loss_sequence_number))
                    if len(self._loss_events) > NUMBER_OF_LOSS_INTERVALS:
                        del self._loss_events[NUMBER_OF_LOSS_INTERVALS:]
                    self._recalculate_loss_event_rate()
                    logger.debug('Detected new loss event, updated loss event rate: %f', self._loss_event_rate)
            del self._received_sequence_numbers[0]

    def _approximate_loss_event_rate(self):
        start = 0
        end = 1
        estimated_loss_event_rate = 0
        for _ in range(100):
            estimated_loss_event_rate = start + (end - start) / 2
            estimated_receive_rate = self._segment_size / (self._rtt * (
                    math.sqrt(2 * estimated_loss_event_rate / 3) + 12 * math.sqrt(
                3 * estimated_loss_event_rate / 8) * estimated_loss_event_rate * (
                            1 + 32 * estimated_loss_event_rate ** 2)))

            error = (self._max_receive_rate - estimated_receive_rate) / self._max_receive_rate
            if error > 0.05:
                end = estimated_loss_event_rate
            elif error < -0.05:
                start = estimated_loss_event_rate
            else:
                break
        return estimated_loss_event_rate

    def _recalculate_loss_event_rate(self):
        if len(self._loss_events) == 1:
            # RFC 5348 Section 6.3.1
            self._loss_event_rate = self._approximate_loss_event_rate()
        elif len(self._loss_events) > 1:
            # RFC 5348 Section 5.3
            interval_sizes = [
                self._received_sequence_numbers[-1].sequence_number - self._loss_events[0].sequence_number + 1]
            for i in range(1, len(self._loss_events)):
                interval_sizes.append(self._loss_events[i - 1].sequence_number - self._loss_events[i].sequence_number)

            # RFC 5348 Section 5.4
            weights = [1 if i < NUMBER_OF_LOSS_INTERVALS / 2 else 2 * (NUMBER_OF_LOSS_INTERVALS - i) / (
                    NUMBER_OF_LOSS_INTERVALS + 2) for i in range(0, len(self._loss_events))]

            i_tot0 = 0
            i_tot1 = 0
            w_tot = 0
            for i in range(len(self._loss_events) - 1):
                i_tot0 = i_tot0 + interval_sizes[i] * weights[i]
                w_tot = w_tot + weights[i]

            for i in range(1, len(self._loss_events)):
                i_tot1 = i_tot1 + interval_sizes[i] * weights[i - 1]

            i_tot = max(i_tot0, i_tot1)
            i_mean = i_tot / w_tot

            self._loss_event_rate = 1 / i_mean

            # TODO (OPTIONAL): RFC 5348 Section 5.5

    def _handle_feedback_timer_expired(self, expired_early):
        # RFC 5348 Section 6.2
        if self._packet_count != 0:
            receive_rate = self._packet_count * self._segment_size / (
                    Timestamp.now() - self._feedback_timer_last_expired)
            self._max_receive_rate = max(receive_rate, self._max_receive_rate)
            self._recalculate_loss_event_rate()

            delay = Timestamp.now() - self._sender_params.received_at
            self.feedback_handler.trigger(delay=delay, timestamp=self._sender_params.timestamp,
                                          receive_rate=receive_rate,
                                          loss_event_rate=self._loss_event_rate)
            self._sent_feedback = True

            if not expired_early:
                self._packet_count = 0
        else:
            self._sent_feedback = False

        self._feedback_timer.reset(self._sender_params.rtt)

    def close(self):
        self._feedback_timer.clear_listeners()
        self.feedback_handler.clear()
        self.rtt_updated.clear()


class ReceiveRateSet:
    Entry = namedtuple('RecvSetEntry', ['timestamp', 'receive_rate'])

    def __init__(self, receive_rate=math.inf, timestamp=None):
        if timestamp is None:
            timestamp = Timestamp.now()
        self._entries = [self.Entry(timestamp=timestamp, receive_rate=receive_rate)]

    def halve(self):
        self._entries = [self.Entry(timestamp=timestamp, receive_rate=recv / 2) for timestamp, recv in self._entries]

    def maximize(self, receive_rate):
        self._append(self.Entry(timestamp=Timestamp.now(), receive_rate=receive_rate))
        # delete initial receive_rate Infinity if it is still a member
        if self._entries[0].receive_rate == math.inf:
            del self._entries[0]
        # set the timestamp of the largest item to the current time, delete all other items
        self._entries = [self.Entry(timestamp=Timestamp.now(), receive_rate=self.max_receive_rate)]

    @property
    def max_receive_rate(self):
        return max(receive_rate for _, receive_rate in self._entries)

    def update(self, receive_rate, rtt):
        timestamp = Timestamp.now()
        self._append(self.Entry(timestamp=timestamp, receive_rate=receive_rate))
        # delete receive_rates older than two round-trip times
        self._entries = [recv for recv in self._entries if timestamp - recv.timestamp < 2 * rtt]

    def _append(self, entry):
        self._entries.append(entry)
        # limit set to 3 most recent entries
        if len(self._entries) > 3:
            del self._entries[:-3]


MAXIMUM_BACKOFF_INTERVAL = 64  # t_mbi, in seconds
SCHEDULING_GRANULARITY = 0.001


class TFRCSender:
    def __init__(self, segment_size):
        # RFC 5348 Section 4.2
        self._segment_size = segment_size
        self._allowed_sending_rate = segment_size  # X, in bytes per second
        self._initial_allowed_sending_rate = None
        self._time_last_doubled = Timestamp.now()  # tld, during slow-start, in seconds
        self._rtt = 0  # R
        self._rto = None
        # list of tuples with timestamp in seconds and estimated receive rate at the receiver
        self._recv_set = ReceiveRateSet()
        self._loss_event_rate = 0  # p
        self._tcp_sending_rate = None  # X_bps
        # data-limited interval
        self._not_limited1 = self._not_limited2 = self._t_new = self._t_next = Timestamp.now()
        self._data_limited = False
        self._no_feedback_deadline = Timestamp.now() + 2
        self.rtt_updated = Event()

    def handle_feedback(self, delay, timestamp, receive_rate, loss_event_rate):
        # RFC 5348 Section 4.3
        self._check_no_feedback_timer_expired()
        previous_rtt = self._rtt
        self._update_rtt(timestamp, delay)
        previous_loss_event_rate, self._loss_event_rate = self._loss_event_rate, loss_event_rate
        self._rto = max(4 * self._rtt, 2 * self._segment_size / self._allowed_sending_rate)

        if previous_rtt == 0:
            # RFC 5348 Section 4.2
            w_init = min(4 * self._segment_size, max(2 * self._segment_size, 4380))
            self._initial_allowed_sending_rate = self._allowed_sending_rate = w_init / self._rtt
            self._time_last_doubled = Timestamp.now()
        else:
            self._update_allowed_sending_rate(receive_rate, previous_loss_event_rate)

        # TODO: for oscillation: cf. RFC 5348 Section 4.5

        self._no_feedback_deadline = Timestamp.now() + self._rto

        # RFC 5348 Section 8.2.1
        self._t_new = timestamp
        t_old = self._t_new - self._rtt
        self._t_next = Timestamp.now()
        self._data_limited = not (
                t_old < self._not_limited1 <= self._t_new or t_old < self._not_limited2 <= self._t_new)

        if self._not_limited1 <= self._t_new < self._not_limited2:
            self._not_limited1 = self._not_limited2

    @property
    @async_generator
    async def sending_credits(self):
        sequence_number = SequenceNumber(0)
        t = Timestamp.now()
        sent_in_previous_iteration = False
        while True:
            self._check_no_feedback_timer_expired()

            # RFC 5348 Section 4.6, 8.2, and 8.3
            t_inter_packet_interval = self._segment_size / self._allowed_sending_rate
            t_delta = min(t_inter_packet_interval, SCHEDULING_GRANULARITY,
                          self._rtt if self._rtt != 0 else math.inf) / 2
            if Timestamp.now() > t - t_delta:
                await yield_((Timestamp.now(), self._rtt, sequence_number))
                sequence_number += 1
                t += t_inter_packet_interval  # set t_(i+1)
                sent_in_previous_iteration = True
            else:
                if sent_in_previous_iteration:
                    # sender is not data-limited at this instant
                    if self._not_limited1 <= self._t_new:
                        # goal: self.not_limited1 > self.t_new
                        self._not_limited1 = self._t_new
                    elif self._not_limited2 <= self._t_next:
                        # goal: self.not_limited2 > self.t_next
                        self._not_limited2 = Timestamp.now()

                await trio.sleep(SCHEDULING_GRANULARITY)
                sent_in_previous_iteration = False

    def _check_no_feedback_timer_expired(self):
        while self._no_feedback_deadline <= Timestamp.now():
            logger.debug('No-feedback timer expired')

            # RFC 5348 Section 4.4
            receive_rate = self._recv_set.max_receive_rate

            def update_limits(timer_limit):
                if timer_limit < self._segment_size / MAXIMUM_BACKOFF_INTERVAL:
                    timer_limit = self._segment_size / MAXIMUM_BACKOFF_INTERVAL
                self._recv_set = ReceiveRateSet(receive_rate=timer_limit / 2, timestamp=Timestamp.now())
                self._update_allowed_sending_rate(receive_rate)

            if self._rtt == 0 or self._loss_event_rate == 0:
                self._allowed_sending_rate = max(self._allowed_sending_rate / 2,
                                                 self._segment_size / MAXIMUM_BACKOFF_INTERVAL)
                logger.debug('Updated allowed sending rate: %f bps', self._allowed_sending_rate)
            # elif "sender has been idle ever since no_feedback_deadline was set" never happens in our case
            elif self._tcp_sending_rate > 2 * receive_rate:
                update_limits(receive_rate)
            else:
                update_limits(self._tcp_sending_rate / 2)

            self._no_feedback_deadline += max(4 * self._rtt, 2 * self._segment_size / self._allowed_sending_rate)

    def _update_rtt(self, timestamp, delay):  # timestamp in seconds, delay in seconds
        r_sample = Timestamp.now() - timestamp - delay
        q = 0.9
        self._rtt = r_sample if self._rtt == 0 else q * self._rtt + (1 - q) * r_sample
        self.rtt_updated.trigger(self._rtt)

    def _update_allowed_sending_rate(self, receive_rate, previous_loss_event_rate=None):
        # RFC 5348 Section 4.3
        if previous_loss_event_rate is None:
            previous_loss_event_rate = self._loss_event_rate
        if self._data_limited:
            if previous_loss_event_rate < self._loss_event_rate:  # TODO: regard NACKs as well
                self._recv_set.halve()
                receive_rate *= 0.85
                self._recv_set.maximize(receive_rate)
                recv_limit = self._recv_set.max_receive_rate
            else:
                self._recv_set.maximize(receive_rate)
                recv_limit = self._recv_set.max_receive_rate
        else:
            self._recv_set.update(receive_rate, self._rtt)
            recv_limit = 2 * self._recv_set.max_receive_rate

        if self._loss_event_rate > 0:
            self._tcp_sending_rate = self._segment_size / (
                    self._rtt * math.sqrt(2 * self._loss_event_rate / 3) + (self._rto * (
                    3 * math.sqrt(3 * self._loss_event_rate / 8) * self._loss_event_rate * (
                    1 + 32 * self._loss_event_rate ** 2))))
            self._allowed_sending_rate = max(min(self._tcp_sending_rate, recv_limit),
                                             self._segment_size / MAXIMUM_BACKOFF_INTERVAL)
        elif Timestamp.now() - self._time_last_doubled >= self._rtt:
            self._allowed_sending_rate = max(min(2 * self._allowed_sending_rate, recv_limit),
                                             self._initial_allowed_sending_rate)
            self._time_last_doubled = Timestamp.now()

        logger.debug('Updated allowed sending rate: %f bps', self._allowed_sending_rate)

    def close(self):
        self.rtt_updated.clear()
