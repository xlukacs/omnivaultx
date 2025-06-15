#!/bin/bash

#  options: omnivaultx, omnivaultx-core, omnivaultx-min
image_name="omnivaultx"

# Check if .env file exists
if [ ! -f ./.env ]; then
    echo "Error: .env file not found"
    exit 1
fi

# Function to generate a random 32 character encryption key
generate_encryption_key() {
    # Generate 24 random bytes and encode as base64
    # 24 bytes * 1.33 (base64 expansion) = 32 characters
    openssl rand -base64 24 | tr -d '\n' | tr -d '/'
}

# Check if ENCRYPTION_KEY exists and is 32 characters
# wc -c returns 33 because it includes the newline character (32 + 1)
if ! grep -q "^ENCRYPTION_KEY=" ./.env || [ "$(grep "^ENCRYPTION_KEY=" ./.env | cut -d'=' -f2 | wc -c)" -ne 33 ]; then
    echo "Generating new ENCRYPTION_KEY, since it was not found or is not 32 characters..."
    # Remove existing ENCRYPTION_KEY if present
    sed -i '/^ENCRYPTION_KEY=/d' ./.env
    # Add new ENCRYPTION_KEY
    echo "ENCRYPTION_KEY=$(generate_encryption_key)" >> ./.env
    echo "New ENCRYPTION_KEY has been generated and added to .env file"
fi

# Function to check if a command exists
check_command() {
    if ! command -v "$1" &> /dev/null; then
        return 1
    fi
    return 0
}

# Function to offer installation
offer_installation() {
    local engine=$1
    echo "$engine is not installed. Would you like to install it? (y/n)"
    read -r response
    if [[ "$response" =~ ^[Yy]$ ]]; then
        if [ "$engine" = "docker" ]; then
            echo "Installing Docker..."
            if [ -f "./docker-setup.sh" ]; then
                chmod +x ./docker-setup.sh
                ./docker-setup.sh
            else
                echo "Error: docker-setup.sh not found in current directory"
                exit 1
            fi
        elif [ "$engine" = "podman" ]; then
            echo "Installing Podman..."
            sudo apt-get update
            sudo apt-get install -y podman
        fi
    else
        echo "Installation declined. Exiting..."
        exit 1
    fi
}

help_message() {
    echo "Usage: $0 [options]"
    echo "Options:"
    echo " -r, --refresh           Refresh the container image"
    echo " -e, --engine [engine]   Set container engine (docker or podman, default: docker)"
    echo " -h, --help              Display this help message"
}

refresh=false
CONTAINER_ENGINE="docker"

# Parse command-line options
while [[ $# -gt 0 ]]; do
    key="$1"
    case $key in
        -r|--refresh)
            refresh=true
            shift
            ;;
        -e|--engine)
            if [[ -n "$2" && ( "$2" == "docker" || "$2" == "podman" ) ]]; then
                CONTAINER_ENGINE="$2"
                shift 2
            else
                echo "Invalid or missing engine. Use 'docker' or 'podman'."
                exit 1
            fi
            ;;
        -h|--help)
            help_message
            exit 0
            ;;
        *)
            echo "Invalid option: $1" >&2
            help_message
            exit 1
            ;;
    esac
done

# Check if the selected container engine is installed
if ! check_command "$CONTAINER_ENGINE"; then
    offer_installation "$CONTAINER_ENGINE"
fi

# Check if Python is installed
if ! check_command "python3"; then
    echo "Python3 is not installed. Would you like to install it, since it is required for meta extractors? (y/n)"
    read -r response
    if [[ "$response" =~ ^[Yy]$ ]]; then
        echo "Installing Python3..."
        if [ -f "./python-install.sh" ]; then
            chmod +x ./python-install.sh
            ./python-install.sh
        else
            echo "Error: python-install.sh not found in current directory"
            exit 1
        fi
    fi
fi

# Create host directories if they don't exist
for dir in "./data/db" "./data/fs" "./data/rabbitmq" "./data/temp"; do
    if [ ! -d "$dir" ]; then
        echo "Creating missing $dir directory"
        mkdir -p "$dir"
    fi
done

if [ "$refresh" = true ]; then
    echo "Removing existing container if it exists"
    $CONTAINER_ENGINE rm -f $image_name 2>/dev/null || true
fi

echo "Stopping container if it exists"
$CONTAINER_ENGINE stop $image_name 2>/dev/null || true

echo "Pulling container image"
$CONTAINER_ENGINE pull madrent/$image_name:latest

echo "Running container"
$CONTAINER_ENGINE run -d --name $image_name \
    --env-file ./.env \
    -p 80:80 \
    -p 15672:15672 \
    -p 5672:5672 \
    -p 8000:8000 \
    -v "$(pwd)/data/db:/app/backend/database" \
    -v "$(pwd)/data/fs:/app/backend/fs" \
    -v "$(pwd)/data/rabbitmq:/var/lib/rabbitmq" \
    -v "$(pwd)/data/temp:/app/backend/temp" \
    $image_name

echo "Printing logs"
$CONTAINER_ENGINE logs -f $image_name
