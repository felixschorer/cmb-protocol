import struct
from functools import wraps
from ipaddress import ip_address, IPv6Address

from cmb_protocol.constants import RESOURCE_ID_STRUCT_FORMAT


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


def is_reversed(start, end):
    return end < start


def directed_range(start, end):
    return reversed(range(end + 1, start + 1)) if is_reversed(start, end) else range(start, end)


def once(func):
    has_been_called = False

    @wraps(func)
    def wrapped(*args, **kwargs):
        nonlocal has_been_called
        if not has_been_called:
            has_been_called = True
            func(*args, **kwargs)

    return wrapped


def format_resource_id(resource_id):
    return struct.pack(RESOURCE_ID_STRUCT_FORMAT, *resource_id).hex()


def format_address(address):
    ip_addr, port = address
    try:
        parsed_ip_addr = ip_address(ip_addr)
    except ValueError:
        return repr(address)
    else:
        fmt = '[{}]:{}' if isinstance(parsed_ip_addr, IPv6Address) else '{}:{}'
        return fmt.format(parsed_ip_addr.compressed, port)