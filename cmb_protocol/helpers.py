import math
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


def calculate_number_of_blocks(resource_length, block_size):
    return math.ceil(resource_length / block_size)
