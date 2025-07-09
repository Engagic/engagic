# Dockerfile for engagic API
FROM python:3.11-slim

LABEL maintainer="engagic"
LABEL description="engagic API - Civic engagement made simple"

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY app/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ .

# Create directories for data and logs
RUN mkdir -p /app/data /app/logs

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash engagic
RUN chown -R engagic:engagic /app
USER engagic

# Set environment variables
ENV PYTHONPATH=/app
ENV ENGAGIC_DB_PATH=/app/data/meetings.db
ENV ENGAGIC_LOG_PATH=/app/logs/engagic.log
ENV ENGAGIC_HOST=0.0.0.0
ENV ENGAGIC_PORT=8000

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Run the application
CMD ["python", "app.py"]