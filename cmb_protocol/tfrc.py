class TFRCSender:
    def update(self, delay, timestamp, receive_rate, loss_event_rate):
        
        return 0, 0


class TFRCReceiver:
    def update(self, timestamp, estimated_rtt, sequence_number):
        return 0, 0, 0, 0.0
