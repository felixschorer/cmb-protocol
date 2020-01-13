import logging
import trio
from trio import Event

logger = logging.getLogger(__name__)


async def spawn_child_nursery(nursery):
    send_channel, receive_channel = trio.open_memory_channel(0)
    async with receive_channel:
        shutdown_trigger = Event()
        nursery.start_soon(_run_nursery_until_event, send_channel, shutdown_trigger)
        return await receive_channel.receive(), shutdown_trigger


async def _run_nursery_until_event(send_channel, shutdown_trigger):
    logger.debug('Starting child nursery')
    async with trio.open_nursery() as nursery:
        nursery.start_soon(shutdown_trigger.wait)
        async with send_channel:
            await send_channel.send(nursery)

    if nursery.cancel_scope.cancelled_caught:
        # in case of cancellation trigger shutdown event as some cleanup code might depend on it
        shutdown_trigger.set()

    logger.debug('Stopped child nursery')
