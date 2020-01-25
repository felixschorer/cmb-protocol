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
        self._cancel_scope = None
        self._deadline = None

    def __iadd__(self, other):
        self.add_listener(other)
        return self

    def __isub__(self, other):
        self.remove_listener(other)
        return self

    def reset(self, timeout):  # timeout in seconds
        self._stop_waiter()
        self._deadline = trio.current_time() + timeout
        self._start_waiter()

    def add_listener(self, listener):
        self._listeners.add(listener)
        self._start_waiter()

    def remove_listener(self, listener):
        self._listeners.remove(listener)
        if len(self._listeners) == 0:
            self._stop_waiter()

    def clear_listeners(self):
        self._listeners.clear()
        self._stop_waiter()

    def clear(self):
        self._deadline = None
        self._stop_waiter()

    def expire(self):
        self.clear()
        for listener in self._listeners:
            listener(True)

    def _stop_waiter(self):
        if self._cancel_scope is not None:
            self._cancel_scope.cancel()
            self._cancel_scope = None

    def _start_waiter(self):
        if self._cancel_scope is None \
                and self._deadline is not None \
                and self._deadline >= trio.current_time() \
                and len(self._listeners) > 0:
            self._cancel_scope = trio.CancelScope()
            self._spawn(self._waiter, self._cancel_scope, self._deadline)

    # gets passed cancel_scope and deadline explicitly
    # since self._cancel_scope and self._deadline might change until this task is started
    async def _waiter(self, cancel_scope, deadline):
        with cancel_scope:
            await trio.sleep_until(deadline)
            # in case this task was not cancelled,
            # self._cancel_scope and self._deadline should equal cancel_scope and deadline respectively
            assert self._cancel_scope == cancel_scope
            assert self._deadline == deadline
            self._cancel_scope = None
            self._deadline = None
            for listener in self._listeners:
                listener(False)


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
