class TFRCSender:
    def update(self, delay, timestamp, receive_rate, loss_event_rate):
        """
        :param delay:
        :param timestamp:
        :param receive_rate:
        :param loss_event_rate:
        :return:
        """
        return 0, 0


class TFRCReceiver:
    def update(self, timestamp, estimated_rtt, sequence_number):
        """
        :param timestamp:
        :param estimated_rtt:
        :param sequence_number:
        :return:
        """
        return 0, 0, 0, 0.0
