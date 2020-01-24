import math
from collections import namedtuple

import trio
from async_generator import async_generator, yield_

from cmb_protocol.sequencenumber import SequenceNumber
from cmb_protocol.timestamp import Timestamp


NDUPACK = 3
NUMBER_OF_LOSS_INTERVALS = 8


class LossEventRateCalculator:
    Entry = namedtuple('Entry', ['timestamp', 'sequence_number'])

    def __init__(self):
        # initialize with -1 to be able to detect the packet with sequence number 0
        self._received_sequence_numbers = [self.Entry(timestamp=Timestamp.now(), sequence_number=SequenceNumber(-1))]
        self._loss_events = []
        self.loss_event_rate = 0

    def update(self, sequence_number, rtt):
        # RFC 5348 Section 5.1
        self._received_sequence_numbers.append(self.Entry(timestamp=Timestamp.now(), sequence_number=sequence_number))
        self._received_sequence_numbers.sort(key=lambda x: x.sequence_number)
        if len(self._received_sequence_numbers) == NDUPACK + 1:
            before, after = self._received_sequence_numbers[:2]
            # RFC 5348 Section 5.2
            for loss_sequence_number in range(before.sequence_number.value + 1, after.sequence_number.value):
                loss_sequence_number = SequenceNumber(loss_sequence_number)
                loss_timestamp = before.timestamp + (after.timestamp - before.timestamp) * (loss_sequence_number - before.sequence_numer) / (after.sequence_numer - before.sequence_numer)
                if len(self._loss_events) == 0 or self._loss_events[-1].timestamp + rtt < loss_timestamp:  # TODO: what happens if rtt is 0?
                    # start new loss event, insert at index 0
                    self._loss_events.insert(0, self.Entry(timestamp=loss_timestamp, sequence_number=loss_sequence_number))
                    if len(self._loss_events) > NUMBER_OF_LOSS_INTERVALS:
                        del self._loss_events[NUMBER_OF_LOSS_INTERVALS:]
                    self.recalculate()
            del self._received_sequence_numbers[0]

    def recalculate(self):
        if len(self._loss_events) == 0:
            return

        # RFC 5348 Section 5.3
        interval_sizes = [self._received_sequence_numbers[-1].sequence_number - self._loss_events[0].sequence_number + 1]
        for i in range(1, len(self._loss_events)):
            interval_sizes[i] = self._loss_events[i - 1].sequence_number - self._loss_events[i].sequence_number

        # RFC 5348 Section 5.4
        weights = [1 if i < NUMBER_OF_LOSS_INTERVALS / 2 else 2 * (NUMBER_OF_LOSS_INTERVALS - i) / (NUMBER_OF_LOSS_INTERVALS + 2) for i in range(0, len(self._loss_events))]

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

        self.loss_event_rate = 1 / i_mean

        # TODO (OPTIONAL): RFC 5348 Section 5.5


class ReceiveRateSet:
    Entry = namedtuple('RecvSetEntry', ['timestamp', 'receive_rate'])

    def __init__(self, receive_rate=math.inf, timestamp=None):
        if timestamp is None:
            timestamp = Timestamp.now()
        self._entries = [self.Entry(timestamp=timestamp, receive_rate=receive_rate)]

    def halve(self):
        self._entries = [(timestamp, recv / 2) for timestamp, recv in self._entries]

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
        self.segment_size = segment_size
        self.allowed_sending_rate = segment_size  # X, in bytes per second
        self.initial_allowed_sending_rate = None
        self.time_last_doubled = Timestamp.now()  # tld, during slow-start, in seconds
        self.rtt = 0  # R
        self.rto = None
        # list of tuples with timestamp in seconds and estimated receive rate at the receiver
        self.recv_set = ReceiveRateSet()
        self.loss_event_rate = 0  # p
        self.tcp_sending_rate = None  # X_bps
        # data-limited interval
        self.not_limited1 = self.not_limited2 = self.t_new = self.t_next = Timestamp.now()
        self.data_limited = False

        self.no_feedback_deadline = Timestamp.now() + 2

    def handle_feedback(self, delay, timestamp, receive_rate, loss_event_rate):
        # RFC 5348 Section 4.3
        self._check_no_feedback_timer_expired()
        previous_rtt = self.rtt
        self._update_rtt(timestamp, delay)
        previous_loss_event_rate, self.loss_event_rate = self.loss_event_rate, loss_event_rate
        self.rto = max(4 * self.rtt, 2 * self.segment_size / self.allowed_sending_rate)

        if previous_rtt == 0:
            # RFC 5348 Section 4.2
            w_init = min(4 * self.segment_size, max(2 * self.segment_size, 4380))
            self.initial_allowed_sending_rate = self.allowed_sending_rate = w_init / self.rtt
            self.time_last_doubled = Timestamp.now()
        else:
            self._update_allowed_sending_rate(receive_rate, previous_loss_event_rate)

        # TODO: for oscillation: cf. RFC 5348 Section 4.5

        self.no_feedback_deadline = Timestamp.now() + self.rto

        # RFC 5348 Section 8.2.1
        self.t_new = timestamp
        t_old = self.t_new - self.rtt
        self.t_next = Timestamp.now()
        self.data_limited = not (t_old < self.not_limited1 <= self.t_new or t_old < self.not_limited2 <= self.t_new)

        if self.not_limited1 <= self.t_new < self.not_limited2:
            self.not_limited1 = self.not_limited2

    @property
    @async_generator
    async def sending_credits(self):
        sequence_number = SequenceNumber(0)
        t = Timestamp.now()
        while True:
            self._check_no_feedback_timer_expired()

            # RFC 5348 Section 4.6, 8.2, and 8.3
            t_inter_packet_interval = self.segment_size / self.allowed_sending_rate
            t_delta = min(t_inter_packet_interval, SCHEDULING_GRANULARITY,
                          self.rtt if self.rtt != 0 else math.inf) / 2
            if Timestamp.now() > t - t_delta:
                try:
                    await yield_((Timestamp.now(), self.rtt, sequence_number))
                    sequence_number += 1
                    t += t_inter_packet_interval  # set t_(i+1)
                except StopIteration:
                    return
            else:
                # sender is not data-limited at this instant
                if self.not_limited1 <= self.t_new:
                    # goal: self.not_limited1 > self.t_new
                    self.not_limited1 = self.t_new
                elif self.not_limited2 <= self.t_next:
                    # goal: self.not_limited2 > self.t_next
                    self.not_limited2 = Timestamp.now()

                await trio.sleep(SCHEDULING_GRANULARITY)

    def _check_no_feedback_timer_expired(self):
        while self.no_feedback_deadline <= Timestamp.now():
            # RFC 5348 Section 4.4
            receive_rate = self.recv_set.max_receive_rate

            def update_limits(timer_limit):
                if timer_limit < self.segment_size / MAXIMUM_BACKOFF_INTERVAL:
                    timer_limit = self.segment_size / MAXIMUM_BACKOFF_INTERVAL
                self.recv_set = ReceiveRateSet(receive_rate=timer_limit / 2, timestamp=Timestamp.now())
                self._update_allowed_sending_rate(receive_rate)

            if self.rtt == 0 or self.loss_event_rate == 0:
                self.allowed_sending_rate = max(self.allowed_sending_rate / 2,
                                                self.segment_size / MAXIMUM_BACKOFF_INTERVAL)
            # elif "sender has been idle ever since no_feedback_deadline was set" never happens in our case
            elif self.tcp_sending_rate > 2 * receive_rate:
                update_limits(receive_rate)
            else:
                update_limits(self.tcp_sending_rate / 2)

            self.no_feedback_deadline += max(4 * self.rtt, 2 * self.segment_size / self.allowed_sending_rate)
    
    def _update_rtt(self, timestamp, delay):  # timestamp in seconds, delay in seconds
        r_sample = Timestamp.now() - timestamp - delay
        q = 0.9
        self.rtt = r_sample if self.rtt == 0 else q * self.rtt + (1 - q) * r_sample

    def _update_allowed_sending_rate(self, receive_rate, previous_loss_event_rate=None):
        # RFC 5348 Section 4.3
        if previous_loss_event_rate is None:
            previous_loss_event_rate = self.loss_event_rate
        if self.data_limited:
            if previous_loss_event_rate < self.loss_event_rate:  # TODO: regard NACKs as well
                self.recv_set.halve()
                receive_rate *= 0.85
                self.recv_set.maximize(receive_rate)
                recv_limit = self.recv_set.max_receive_rate
            else:
                self.recv_set.maximize(receive_rate)
                recv_limit = self.recv_set.max_receive_rate
        else:
            self.recv_set.update(receive_rate, self.rtt)
            recv_limit = 2 * self.recv_set.max_receive_rate

        if self.loss_event_rate > 0:
            self.tcp_sending_rate = self.segment_size / (self.rtt * math.sqrt(2 * self.loss_event_rate / 3) + (self.rto * (
                        3 * math.sqrt(3 * self.loss_event_rate / 8) * self.loss_event_rate * (1 + 32 * self.loss_event_rate ** 2))))
            self.allowed_sending_rate = max(min(self.tcp_sending_rate, recv_limit),
                                            self.segment_size / MAXIMUM_BACKOFF_INTERVAL)
        elif Timestamp.now() - self.time_last_doubled >= self.rtt:
            self.allowed_sending_rate = max(min(2 * self.allowed_sending_rate, recv_limit),
                                            self.initial_allowed_sending_rate)
            self.time_last_doubled = Timestamp.now()
