#!/bin/bash

# Check if .env file exists
if [ ! -f ./.env ]; then
    echo "Error: .env file not found"
    exit 1
fi

help_message() {
    echo "Usage: $0 [options]"
    echo "Options:"
    echo " -r, --refresh    Refresh the docker image"
    echo " -h, --help       Display this help message"
}

refresh=false

# Parse command-line options
while [[ $# -gt 0 ]]; do
    key="$1"
    case $key in
        -r|--refresh)
            refresh=true
            shift
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
if [ ! -d "./data/db" ]; then
    echo "Creating missing ./data/db directory"
    mkdir -p ./data/db
fi
if [ ! -d "./data/fs" ]; then
    echo "Creating missing ./data/fs directory"
    mkdir -p ./data/fs
fi
if [ ! -d "./data/rabbitmq" ]; then
    echo "Creating missing ./data/rabbitmq directory"
    mkdir -p ./data/rabbitmq
fi
if [ ! -d "./data/temp" ]; then
    echo "Creating missing ./data/temp directory"
    mkdir -p ./data/temp
fi

if [ "$refresh" = true ]; then
    # Remove existing container if it exists
    echo "Removing existing container if it exists"
    docker rm -f dp_all_in_one 2>/dev/null || true
fi

# pull docker image
echo "Pulling docker image"
docker pull madrent/dp_all_in_one:latest

# run docker container with volume mounts
echo "Running docker container"
docker run -d --name dp_all_in_one \
    --env-file ./.env \
    -p 80:80 \
    -v $(pwd)/data/db:/app/backend/database \
    -v $(pwd)/data/fs:/app/backend/fs \
    -v $(pwd)/data/rabbitmq:/var/lib/rabbitmq \
    -v $(pwd)/data/temp:/app/backend/temp \
    madrent/dp_all_in_one:latest

# print logs
echo "Printing logs"
docker logs -f dp_all_in_one


