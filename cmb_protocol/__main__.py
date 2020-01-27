from argparse import ArgumentParser, FileType
from ipaddress import ip_address

from cmb_protocol.client import ConnectionConfig
from cmb_protocol.constants import DEFAULT_PORT, DEFAULT_IP_ADDR, DEFAULT_SENDING_RATE
from cmb_protocol.helpers import parse_resource_id
from cmb_protocol import log_util, client, server

logger = log_util.get_logger(__file__)

MODE = 'mode'
CLIENT = 'client'
SERVER = 'server'
VERBOSE = 'verbose'
IP_ADDR = 'ip_addr'
PORT = 'port'
SENDING_RATE = 'sending_rate'
RESOURCE_ID = 'resource_id'
OUTPUT = 'output'
FILE = 'file'


def parse_args():
    address_parser = ArgumentParser(add_help=False)
    address_parser.add_argument('-a', '--{}'.format(IP_ADDR), action='append', type=str, default=[])
    address_parser.add_argument('-p', '--{}'.format(PORT), action='append', type=int, default=[])

    loglevel_parser = ArgumentParser(add_help=False)
    loglevel_parser.add_argument('-v', '--{}'.format(VERBOSE), action='store_const', const=True,
                                 default=False)

    main_parser = ArgumentParser()

    subparsers = main_parser.add_subparsers(dest=MODE)

    client_parser = subparsers.add_parser(CLIENT, parents=[address_parser, loglevel_parser])
    client_parser.add_argument(RESOURCE_ID, type=str)
    client_parser.add_argument(OUTPUT, type=FileType('wb'))
    client_parser.add_argument('-r', '--{}'.format(SENDING_RATE), action='append', type=int, default=[])

    server_parser = subparsers.add_parser(SERVER, parents=[address_parser, loglevel_parser])
    server_parser.add_argument(FILE, type=FileType('rb'))

    return main_parser.parse_args()


def main():
    args = parse_args()

    log_util.enable_verbose_logging(getattr(args, VERBOSE))

    mode, ip_addrs, ports = getattr(args, MODE), getattr(args, IP_ADDR), getattr(args, PORT)

    if len(ip_addrs) == 0:
        ip_addrs.append(DEFAULT_IP_ADDR)

    if len(ports) == 0:
        ports.append(DEFAULT_PORT)

    if len(ip_addrs) == 1:
        ip_addrs *= len(ports)

    if len(ports) == 1:
        ports *= len(ip_addrs)

    if len(ip_addrs) != len(ports):
        logger.error('Expected the number of addresses to match the number of ports, ',
                     'or the number of addresses or ports to be 1')
        exit(1)

    for ip_addr in ip_addrs:
        try:
            ip_address(ip_addr)
        except ValueError:
            logger.error('%s is not a valid IPv4 or IPv6 address', ip_addr)
            exit(1)

    for port in ports:
        if port < 2 ** 10 or 2 ** 16 - 1 < port:
            logger.error('%d is not within the valid port range [%d, %d]', port, 2 ** 10, 2 ** 16 - 1)
            exit(1)

    addresses = list(zip(ip_addrs, ports))

    if mode == CLIENT:
        if len(addresses) > 2:
            logger.error('Expected at most 2 addresses, %d were given', len(addresses))
            exit(1)

        sending_rates = getattr(args, SENDING_RATE)
        if len(sending_rates) == 0:
            sending_rates.append(DEFAULT_SENDING_RATE)

        if len(sending_rates) == 1:
            sending_rates *= len(addresses)

        if len(sending_rates) != len(addresses):
            logger.error('Expected the number of addresses to match the number of sending rates, ',
                         'or the number of sending rates to be 1')
            exit(1)

        connection_configs = [
            ConnectionConfig(address=server_address, sending_rate=sending_rate, reverse=reverse) for
            reverse, server_address, sending_rate in zip([False, True], addresses, sending_rates)]

        resource_id, output = getattr(args, RESOURCE_ID), getattr(args, OUTPUT)
        try:
            parsed_resource_id = parse_resource_id(resource_id)
        except ValueError:
            logger.error('%s is not a valid resource id', resource_id)
            exit(1)
        else:
            client.run(resource_id=parsed_resource_id, file_writer=output, connection_configs=connection_configs)

    elif mode == SERVER:
        file_type = getattr(args, FILE)
        server.run(file_type, addresses)


if __name__ == '__main__':
    main()
