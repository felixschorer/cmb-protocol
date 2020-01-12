import logging
from argparse import ArgumentParser, FileType
from ipaddress import ip_address
from constants import DEFAULT_PORT, DEFAULT_IP_ADDR

logger = logging.getLogger(__name__)

MODE = 'mode'
CLIENT = 'client'
SERVER = 'server'
VERBOSE = 'verbose'
IP_ADDR = 'ip_addr'
PORT = 'port'
RESOURCE_ID = 'resource_id'
OUTPUT = 'output'
FILE = 'file'


def parse_args():
    address_parser = ArgumentParser(add_help=False)
    address_parser.add_argument('-a', '--{}'.format(IP_ADDR), action='append', type=str, default=[])
    address_parser.add_argument('-p', '--{}'.format(PORT), action='append', type=int, default=[])

    loglevel_parser = ArgumentParser(add_help=False)
    loglevel_parser.add_argument('-v', '--{}'.format(VERBOSE), action='store_const', const=logging.DEBUG,
                                 default=logging.INFO)

    main_parser = ArgumentParser()

    subparsers = main_parser.add_subparsers(dest=MODE)

    client_parser = subparsers.add_parser(CLIENT, parents=[address_parser, loglevel_parser])
    client_parser.add_argument(RESOURCE_ID, type=str)
    client_parser.add_argument(OUTPUT, type=FileType('wb'))

    server_parser = subparsers.add_parser(SERVER, parents=[address_parser, loglevel_parser])
    server_parser.add_argument(FILE, type=FileType('rb'))

    return main_parser.parse_args()


def main():
    args = parse_args()

    loglevel = getattr(args, VERBOSE)
    logging.basicConfig(format='[%(levelname)s] %(message)s', level=loglevel)

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
        logger.error('Expected the number of addresses to match the number of port, ',
                     'or the number of addresses or ports to be 1.')
        exit(1)

    parsed_ip_addrs = []
    for ip_addr in ip_addrs:
        try:
            parsed_ip_addr = ip_address(ip_addr)
            parsed_ip_addrs.append(parsed_ip_addr)
        except ValueError:
            logger.error('{} is not a valid IPv4 or IPv6 address.'.format(ip_addr))
            exit(1)

    for port in ports:
        if port < 2**10 or 2**16 - 1 < port:
            logger.error('{} is not within the valid port range [{}, {}]'.format(port, 2**10, 2**16 - 1))
            exit(1)

    addresses = list(zip(ip_addrs, ports))

    if mode == CLIENT:
        if len(addresses) > 2:
            logger.error('Expected at most 2 addresses, {} were given.'.format(len(addresses)))
            exit(1)

        server_address, offloading_server_address = addresses[0], addresses[1] if len(addresses) == 2 else None

        resource_id, output = getattr(args, RESOURCE_ID), getattr(args, OUTPUT)
        try:
            parsed_resource_id = bytes.fromhex(resource_id)
        except ValueError:
            logger.error('{} is not a valid resource id.'.format(resource_id))
            exit(1)
        else:
            if len(parsed_resource_id) != 16:
                logger.error('{} is not a valid resource id.'.format(resource_id))
                exit(1)

            from client import run
            run(resource_id=parsed_resource_id, file_writer=output, server_address=server_address,
                offloading_server_address=offloading_server_address)

    elif mode == SERVER:
        file_type = getattr(args, FILE)
        from server import run
        run(file_type, addresses)


if __name__ == '__main__':
    main()