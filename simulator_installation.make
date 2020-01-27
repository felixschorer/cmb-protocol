patch_ubuntu:

install_python: patch_ubuntu
	sudo apt install python3-dev

install_rustup:
	curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

create_virtual_env: install_python install_rustup
	pip3 install virtualenv
	python3 -m virtualenv venv

activate_virtual_env: create_virtual_env
	source venv/bin/activate

prepare_compile_native_raptorq_module: install_rustup
	cd raptorq
	rustup install nightly
	rustup override set nightly

install_dependencies: create_virtual_env activate_virtual_env
	pip3 install -r requirements.txt

compile_native_raptorq_module: prepare_compile_native_raptorq_module activate_virtual_env
	maturin develop --release