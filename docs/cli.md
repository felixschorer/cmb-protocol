## client

```
usage: __main__.py client [-h] [-a IP_ADDR] [-p PORT] [-v] [-r SENDING_RATE]
                          resource_id output

positional arguments:
  resource_id
  output

optional arguments:
  -h, --help            show this help message and exit
  -a IP_ADDR, --ip_addr IP_ADDR
  -p PORT, --port PORT
  -v, --verbose
  -r SENDING_RATE, --sending_rate SENDING_RATE
```

## server

```
usage: __main__.py server [-h] [-a IP_ADDR] [-p PORT] [-v] file

positional arguments:
  file

optional arguments:
  -h, --help            show this help message and exit
  -a IP_ADDR, --ip_addr IP_ADDR
  -p PORT, --port PORT
  -v, --verbose
```