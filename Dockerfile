FROM python:3.12-slim

# Create a user with UID/GID 1000
RUN groupadd -g 1000 spotbot && \
    useradd -u 1000 -g 1000 -m -s /bin/bash spotbot

# Set working directory
WORKDIR /app

# Install system dependencies as root
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies as root
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Set ownership
RUN chown -R 1000:1000 /app

# Switch to non-root user
USER 1000:1000

# Run the bot
CMD ["python", "-u", "main.py"]