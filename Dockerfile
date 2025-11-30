FROM python:3.12-alpine

# Set working directory
WORKDIR /app

# Install system dependencies for spotdl
# Note: Alpine uses apk instead of apt-get
RUN apk add --no-cache \
    ffmpeg \
    gcc \
    musl-dev \
    python3-dev \
    libffi-dev

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create download directory
RUN mkdir -p /downloads

# Run the bot
CMD ["python", "-u", "main.py"]