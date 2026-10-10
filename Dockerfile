FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies required for building C extensions (psycopg2)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application codebase
COPY . .

# Expose default API port
EXPOSE 8000

# Default command starts the background worker and FastAPI server (supports Render $PORT)
CMD ["sh", "-c", "python -m app.worker.runner & uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]

