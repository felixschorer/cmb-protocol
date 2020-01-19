class TFRCSender:
    def update(self, delay, timestamp, receive_rate, loss_event_rate):
        """
        :param delay: 16 bit for the amount of time elapsed between the receipt of the last data packet at the receiver and the generation of this feedback report
        :param timestamp: 24 bit timestamp in milliseconds of the last data packet received
        :param receive_rate: 32 bit denoted in packets per second as rate at which the receiver estimates that data was received in the previous round-trip time
        :param loss_event_rate: 32 bit IEEE 754 float estimate of the loss event rate
        :return: estimated_rtt in milliseconds, sending_rate in bytes per second
        """
        return 0, 0


class TFRCReceiver:
    def update(self, timestamp, estimated_rtt, sequence_number):
        """
        :param timestamp: 24 bit timestamp in milliseconds starting at 0
        :param estimated_rtt: 16 bit estimated round trip time
        :param sequence_number: 24 bit sequence number
        :return: delay, timestamp, receive_rate, loss_event_rate
        """
        return 0, 0, 0, 0.0
