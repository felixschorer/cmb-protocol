# CMB Protocol

For the following, the mininet-based virtual machine from 
[http://home.in.tum.de/~tonetto/mininet.ova](http://home.in.tum.de/~tonetto/mininet.ova) 
is assumed as environment.

## Installation

```
$ make install
```

The command above will make sure, 
- Python 3.5 and Rust are installed. 
- Since the installed Ubuntu on the above mentioned VM is out of support, it is patched. 
- Project dependencies are installed in a virtual environment.


The compilation might fail if a 32bit version of Python is used on a 64bit machine.

## Running server and client
Activate the virtual environment if it is not already activated.
```
$ source venv/bin/activate
```

### Running the server
```
(venv) $ python3 -m cmb_protocol server
```

### Running the client
```
(venv) $ python3 -m cmb_protocol client
```
 
### Usage examples
#### Basic example
When no IP address or port is specified, the server will start listening on 127.0.0.1:9999.
The server expects its first positional argument to be a path to a file.
```
(venv) $ python3 -m cmb_protocol server ./some_file.pdf
[INFO]	Reading from C:/Users/felix/Desktop/CMB/enhanced_tfrc.pdf
[INFO]	Serving resource 9227dae20e7cbcd561f55d2a31363843000000000020df7a
[INFO]	Started listening
```

Similarly, the client will connect to 127.0.0.1:9999 with a sending rate of 2 Mbit/s.
The client expects its first positional argument to be the resource ID which is printed to the console by the server, as seen above.
The second argument must be the destination file, e.g. `/dev/null` or `-` for stdout.
```
(venv) $ python3 -m cmb_protocol client 9227dae20e7cbcd561f55d2a31363843000000000020df7a /dev/null
[INFO]	Writing to /dev/null
[INFO]	Downloading 2.154362 Mb
[INFO]	Combined target transmission rate 2.000000 Mbit/s
```

#### Serving on more than one interface
The server can listen on more than one interface. 
To specify multiple IP address and port combinations, do as follows.
```
(venv) $ python3 -m cmb_protocol server -a 127.0.0.1 -p 1337 -a ::1 -p 1338 ./some_file.pdf
[INFO]	Reading from C:/Users/felix/Desktop/CMB/enhanced_tfrc.pdf
[INFO]	Serving resource 9227dae20e7cbcd561f55d2a31363843000000000020df7a
[INFO]	Started listening
[INFO]	Started listening
```

#### Downloading using two connections
The client supports downloading a file via up to 2 connections in parallel.
```
(venv) $ python3 -m cmb_protocol client -a 127.0.0.1 -p 1337 -a ::1 -p 1338 9227dae20e7cbcd561f55d2a31363843000000000020df7a /dev/null
[INFO]	Writing to /dev/null
[INFO]	Downloading 2.154362 Mb
[INFO]	Combined target transmission rate 4.000000 Mbit/s
```

#### Setting the target sending rate
The client is able to specify a different desired target sending rate in bps per connection.
```
(venv) $ python3 -m cmb_protocol client -a 127.0.0.1 -p 1337 -r 50000 -a ::1 -p 1338 -r 25000 9227dae20e7cbcd561f55d2a31363843000000000020df7a /dev/null
[INFO]	Writing to /dev/null
[INFO]	Downloading 2.154362 Mb
[INFO]	Combined target transmission rate 0.600000 Mbit/s
```