import math
import trio
from ipaddress import ip_address, IPv6Address
from trio import Event, socket
from cmb_protocol import log_util

logger = log_util.get_logger(__name__)


class Timer:
    def __init__(self, spawn):
        """
        :param spawn: function for spawning background tasks
        """
        self._spawn = spawn
        self._listeners = set()
        self._starting = False
        self._cancel_scope = None
        self._deadline = None

    def reset(self, timeout):
        self._deadline = trio.current_time() + timeout
        if len(self._listeners):
            self._start_waiter()

    def add_listener(self, listener):
        self._listeners.add(listener)
        if self._deadline is not None:
            self._start_waiter()

    def remove_listener(self, listener):
        self._listeners.remove(listener)
        if len(self._listeners) == 0 and self._cancel_scope is not None:
            self._cancel_scope.cancel()

    def clear_listeners(self):
        self._listeners.clear()
        if self._cancel_scope is not None:
            self._cancel_scope.cancel()

    def _start_waiter(self):
        async def waiter():
            self._starting = False
            with trio.move_on_at(self._deadline) as cancel_scope:
                self._cancel_scope = cancel_scope
                await trio.sleep_forever()
            self._cancel_scope = None
            for listener in self._listeners:
                listener()

        if self._cancel_scope is not None:
            self._cancel_scope.deadline = self._deadline
        elif not self._starting:
            self._starting = True
            self._spawn(waiter)


async def spawn_child_nursery(spawn, shutdown_timeout=math.inf):
    send_channel, receive_channel = trio.open_memory_channel(0)
    async with receive_channel:
        shutdown_trigger = Event()
        spawn(_run_nursery_until_event, send_channel, shutdown_trigger, shutdown_timeout)
        return await receive_channel.receive(), shutdown_trigger


async def _run_nursery_until_event(send_channel, shutdown_trigger, shutdown_timeout):
    logger.debug('Starting child nursery')
    async with trio.open_nursery() as nursery:
        async def shutdown():
            await shutdown_trigger.wait()
            nursery.cancel_scope.deadline = trio.current_time() + shutdown_timeout
            logger.debug('Giving child nursery %.3f seconds to shut down...', shutdown_timeout)

        nursery.start_soon(shutdown)

        async with send_channel:
            await send_channel.send(nursery)

    if nursery.cancel_scope.cancelled_caught:
        logger.warning('Forcefully stopped child nursery')
    else:
        logger.debug('Child nursery shut down')


def get_ip_family(address):
    ip_addr, port = address
    parsed_ip_addr = ip_address(ip_addr)
    return socket.AF_INET6 if isinstance(parsed_ip_addr, IPv6Address) else socket.AF_INET
