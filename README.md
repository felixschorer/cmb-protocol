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
 