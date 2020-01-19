import math
import struct
from functools import wraps

import trio
from ipaddress import ip_address, IPv6Address
from trio import Event, socket
from cmb_protocol import log_util

logger = log_util.get_logger(__name__)


def get_ip_family(address):
    ip_addr, port = address
    parsed_ip_addr = ip_address(ip_addr)
    return socket.AF_INET6 if isinstance(parsed_ip_addr, IPv6Address) else socket.AF_INET


async def spawn_child_nursery(nursery, shutdown_timeout=math.inf):
    send_channel, receive_channel = trio.open_memory_channel(0)
    async with receive_channel:
        shutdown_trigger = Event()
        nursery.start_soon(_run_nursery_until_event, send_channel, shutdown_trigger, shutdown_timeout)
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


def pack_uint48(uint48):
    assert uint48 < 2**48
    return struct.pack('!Q', uint48)[-6:]


def unpack_uint48(buffer):
    assert len(buffer) == 6
    uint48, = struct.unpack('!Q', bytes(2) + buffer)
    return uint48


def pack_uint24(uint24):
    assert uint24 < 2**24
    return struct.pack('!I', uint24)[-3:]


def unpack_uint24(buffer):
    assert len(buffer) == 3
    uint24, = struct.unpack('!I', bytes(1) + buffer)
    return uint24


def once(func):
    has_been_called = False

    @wraps(func)
    def wrapped(*args, **kwargs):
        nonlocal has_been_called
        if not has_been_called:
            has_been_called = True
            func(*args, **kwargs)

    return wrapped
