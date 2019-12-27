# CMB Protocol
## Installation
### Prerequisites
- [Python](https://www.python.org/downloads/) in version 3.6 or higher
  - check the installed version with `python3 --version`
- [rustup](https://rustup.rs/) for managing Rust toolchains

### Create a new virtual environment
Make sure `virtualenv` is installed.
```
$ pip3 install virtualenv
```

Create a new virtual environment and activate it.
```
$ python3 -m virtualenv venv
$ source venv/bin/activate
```

### Installing dependencies
```
(venv) $ pip3 install -r requirements.txt
```

### Compiling the native raptorq module
Change into the `raptorq` directory.
```
$ cd raptorq
```

Install the rust `nightly` toolchain and set it as the local toolchain.
```
$ rustup install nightly
$ rustup override set nightly
```

Compile the module and install it in the virtual environment.
```
(venv) $ maturin develop --release
```

On some operating systems (e.g. Ubuntu) the compilation will fail without the `python3-dev` package.
```
$ sudo apt install python3-dev
```

The compilation might also fail if a 32bit version of Python is used on a 64bit machine.

## Running server and client
Activate the virtual environment if it is not already activated.
```
$ source venv/bin/activate
```

### Running the server
```
(venv) $ python3 src/server.py
```

### Running the client
```
(venv) $ python3 src/client.py
```

## Installing and running on Windows
On Windows `python3` and `pip3` will not be available.
Instead use `py -3` and `py -3 -m pip`.

### Activating the virtual environment
```
$ venv/Scripts/activate.bat
```
 