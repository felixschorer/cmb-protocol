patch_ubuntu:

install_python: patch_ubuntu
	sudo apt install python3-dev python3-pip

install_rustup:
	curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
	cd raptorq
	rustup install nightly
	rustup override set nightly

create_virtual_env: install_python
	python3 -m pip3 install virtualenv
	python3 -m virtualenv venv

activate_virtual_env: create_virtual_env
	source venv/bin/activate

install_dependencies: activate_virtual_env
	python3 -m pip3 install -r requirements.txt

compile_native_raptorq_module: install_rustup activate_virtual_env
	maturin develop --release