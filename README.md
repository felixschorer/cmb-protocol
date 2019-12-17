# CMB Protocol
## Installation
Makes sure Python is installed in version 3.6 or higher.

### Create a new virtual environment
```
$ python3 -m venv venv
```

In case creating the virtual environment fails make sure `python3-venv` is installed.
```
$ sudo apt-get update
$ sudo apt-get install python3-venv
```

### Activate the virtual environment
```
$ source venv/bin/activate
```

### Installing dependencies
```
(venv) $ pip3 install requirements.txt
```

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

## Development
### Setting up PyCharm on Windows using WSL
Follow the steps listed under [Installation](#installation) using the Windows Subsystem for Linux.

1. In PyCharm navigate to `File` > `Settings` > `Project` > `Project Interpreter`.
2. Click the cogwheel and select `Add...`.
3. Select `WSL`.
4. The interpreter path should be `<path to project>/venv/bin/python3`.
 