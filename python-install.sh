#!/bin/bash

set -e

echo "Detecting OS..."

if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$ID
elif [[ "$OSTYPE" == "darwin"* ]]; then
    OS="macos"
elif grep -q Microsoft /proc/version 2>/dev/null; then
    OS="wsl"
else
    OS="unknown"
fi

echo "Detected OS: $OS"

install_python_ubuntu() {
    echo "Updating package list..."
    sudo apt-get update
    echo "Installing Python 3, pip, and venv..."
    sudo apt-get install -y python3 python3-pip python3-venv
}

install_python_fedora() {
    echo "Installing Python 3, pip, and venv..."
    sudo dnf install -y python3 python3-pip python3-virtualenv
}

install_python_centos() {
    echo "Installing EPEL repository..."
    sudo yum install -y epel-release
    echo "Installing Python 3 and pip..."
    sudo yum install -y python3 python3-pip
}

install_python_macos() {
    if ! command -v brew &>/dev/null; then
        echo "Homebrew not found. Installing Homebrew..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    fi
    echo "Installing Python 3..."
    brew install python
}

case "$OS" in
    ubuntu|debian)
        install_python_ubuntu
        ;;
    fedora)
        install_python_fedora
        ;;
    centos)
        install_python_centos
        ;;
    macos)
        install_python_macos
        ;;
    wsl)
        echo "Detected WSL. Assuming Ubuntu/Debian base."
        install_python_ubuntu
        ;;
    *)
        echo "Unsupported or unknown OS. Please install Python manually."
        exit 1
        ;;
esac

echo "Python installation complete."
echo "Python version:"
python3 --version
echo "Pip version:"
python3 -m pip --version

echo "You can now use python3 and pip3."
