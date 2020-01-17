class Connection:
    def __init__(self, shutdown, spawn, send):
        self.shutdown = shutdown
        self.spawn = spawn
        self.send = send

    async def handle_packet(self, packet):
        self.shutdown()
