import logging
from contextvars import ContextVar
from logging import LoggerAdapter

from cmb_protocol.helpers import format_address

logging.basicConfig(format='[%(levelname)s]\t%(message)s', level=logging.INFO)

_logging_context = ContextVar('logging_context', default=dict())
_verbose_logging = False


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


def get_logging_context(key):
    return _logging_context.get({}).get(key, None)