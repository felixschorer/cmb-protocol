.PHONY: patch_ubuntu install_python install_rustup create_virtualenv install_dependencies compile_raptorq install clean

patch_ubuntu: /etc/apt/sources.list
	sudo sed -i 's/http:\/\/de.archive/http:\/\/old-releases/g' /etc/apt/sources.list
	sudo sed -i 's/http:\/\/security/http:\/\/old-releases/g' /etc/apt/sources.list

install_python: .make.install_python

install_rustup: .make.install_rustup

create_virtualenv: .make.create_virtualenv

install_dependencies: create_virtualenv requirements.txt
	. venv/bin/activate && python3 -m pip install -r requirements.txt

compile_raptorq: install_rustup create_virtualenv install_dependencies $(shell find raptorq/src -type f) raptorq/Cargo.toml
	. venv/bin/activate && maturin develop --release

install: install_dependencies compile_raptorq

clean:
	rm .make.*

.make.install_python: patch_ubuntu
	sudo apt-get update
	sudo apt-get install python3 python3-dev python3-pip
	touch .make.install_python

.make.install_rustup:
	curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
	cd raptorq
	source ~/.bashrc
	rustup install nightly
	rustup override set nightly
	touch .make.install_rustup

.make.create_virtualenv: install_python
	python3 -m pip install virtualenv
	python3 -m virtualenv venv
	touch .make.create_virtualenv
