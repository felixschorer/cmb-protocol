patch_ubuntu:
	sudo sed -i 's/de.archive/old-releases/g' /etc/apt/sources.list
	sudo sed -i 's/security/old-releases/g' /etc/apt/sources.list
	sudo apt-get update

install_python: patch_ubuntu
	sudo apt-get install python3-dev python3-pip

install_rustup:
	curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
	cd raptorq
	rustup install nightly
	rustup override set nightly

create_virtual_env: install_python
	python3 -m pip3 install virtualenv
	python3 -m virtualenv venv

install_dependencies: create_virtual_env
	source venv/bin/activate && python3 -m pip3 install -r requirements.txt

compile_native_raptorq_module: install_rustup create_virtual_env
	source venv/bin/activate && maturin develop --release