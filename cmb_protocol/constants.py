import math

MAXIMUM_TRANSMISSION_UNIT = 512
SYMBOLS_PER_BLOCK = 100
DEFAULT_PORT = 9999
DEFAULT_IP_ADDR = '127.0.0.1'
RESOURCE_ID_STRUCT_FORMAT = '!16sQ'


def calculate_number_of_blocks(resource_length):
    return math.ceil(resource_length / (MAXIMUM_TRANSMISSION_UNIT * SYMBOLS_PER_BLOCK))


def calculate_block_size(resource_length, block_id):
    block_size = MAXIMUM_TRANSMISSION_UNIT * SYMBOLS_PER_BLOCK
    last_block_id = calculate_number_of_blocks(resource_length) - 1
    last_block_size = resource_length % block_size or block_size

    if 0 <= block_id < last_block_id:
        return block_size
    elif block_id == last_block_id:
        return last_block_size
    else:
        return None
