# Base image
FROM python:3.10-slim


# Set environment variables based on the build arguments
ENV RABBIT_HOST=${RABBIT_HOST}
ENV RABBIT_USER=${RABBIT_USER}
ENV RABBIT_PASS=${RABBIT_PASS}
ENV RABBIT_VHOST=${RABBIT_VHOST}
ENV RABBIT_PORT=${RABBIT_PORT}

# Set the working directory
WORKDIR /app

# Install required system dependencies
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libpoppler-cpp-dev \
    ffmpeg \
    libavcodec-extra \
    tesseract-ocr \
    build-essential \
    && apt-get clean

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code into the container
COPY . .

# Command to run the RabbitMQ consumer
CMD ["python", "main.py"]
