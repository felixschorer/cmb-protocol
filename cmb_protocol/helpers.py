import logging
import trio
from ipaddress import ip_address, IPv6Address
from contextvars import ContextVar
from logging import LoggerAdapter
from trio import Event, socket

logging.basicConfig(format='[%(levelname)s]\t%(message)s', level=logging.INFO)

_logging_context = ContextVar('logging_context', default=dict())
_verbose_logging = False


def get_ip_family(address):
    ip_addr, port = address
    parsed_ip_addr = ip_address(ip_addr)
    return socket.AF_INET6 if isinstance(parsed_ip_addr, IPv6Address) else socket.AF_INET


def format_address(address):
    ip_addr, port = address
    try:
        parsed_ip_addr = ip_address(ip_addr)
    except ValueError:
        return repr(address)
    else:
        fmt = '[{}]:{}' if isinstance(parsed_ip_addr, IPv6Address) else '{}:{}'
        return fmt.format(parsed_ip_addr.compressed, port)


class _AddressInjectingAdapter(LoggerAdapter):
    def process(self, msg, kwargs):
        logging_context = {**self.extra, **_logging_context.get()}
        context_lines = ['{}={}'.format(key, value) for key, value in logging_context.items() if value is not None]

        if _verbose_logging and len(context_lines) > 0:
            return '\n# '.join([msg, *context_lines]) + '\n', kwargs

        return msg, kwargs


def enable_verbose_logging(enable):
    global _verbose_logging
    _verbose_logging = enable
    if enable:
        logging.root.setLevel(logging.DEBUG)
    else:
        logging.root.setLevel(logging.INFO)


def get_logger(name, **extra):
    return _AddressInjectingAdapter(logging.getLogger(name), extra)


def set_listen_address(address):
    update_logging_context(listen_address=format_address(address) if address else None)


def set_remote_address(address):
    update_logging_context(remote_address=format_address(address) if address else None)


def update_logging_context(**kwargs):
    curr = _logging_context.get()
    _logging_context.set({**curr, **kwargs})


logger = get_logger(__name__)


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
    logger.debug('Stopped child nursery')
