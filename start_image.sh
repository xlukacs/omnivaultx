#!/bin/bash

# Check if .env file exists
if [ ! -f ./.env ]; then
    echo "Error: .env file not found, please use the provided template in .env.exmaple"
    exit 1
fi

# Create host directories if they don't exist
mkdir -p ./data/db
mkdir -p ./data/fs
mkdir -p ./data/rabbitmq
mkdir -p ./data/temp

# Remove existing container if it exists
echo "Removing existing container if it exists"
docker rm -f dp_all_in_one 2>/dev/null || true

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


