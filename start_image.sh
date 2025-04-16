#!/bin/bash

# Check if .env file exists
if [ ! -f ./.env ]; then
    echo "Error: .env file not found"
    exit 1
fi

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

# Create host directories if they don't exist
for dir in "./data/db" "./data/fs" "./data/rabbitmq" "./data/temp"; do
    if [ ! -d "$dir" ]; then
        echo "Creating missing $dir directory"
        mkdir -p "$dir"
    fi
done

if [ "$refresh" = true ]; then
    echo "Removing existing container if it exists"
    $CONTAINER_ENGINE rm -f dp_all_in_one 2>/dev/null || true
fi

echo "Stopping container if it exists"
$CONTAINER_ENGINE stop dp_all_in_one 2>/dev/null || true

echo "Pulling container image"
$CONTAINER_ENGINE pull madrent/dp_all_in_one:latest

echo "Running container"
$CONTAINER_ENGINE run -d --name dp_all_in_one \
    --env-file ./.env \
    -p 80:80 \
    -p 15672:15672 \
    -p 5672:5672 \
    -v "$(pwd)/data/db:/app/backend/database" \
    -v "$(pwd)/data/fs:/app/backend/fs" \
    -v "$(pwd)/data/rabbitmq:/var/lib/rabbitmq" \
    -v "$(pwd)/data/temp:/app/backend/temp" \
    madrent/dp_all_in_one:latest

echo "Printing logs"
$CONTAINER_ENGINE logs -f dp_all_in_one
