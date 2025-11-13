FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies needed for mysqlclient
RUN apt-get update && apt-get install -y \
    build-essential \
    default-libmysqlclient-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . /app/

# Expose Django port
EXPOSE 8000

# Run Django development server (overridden by docker-compose command)
CMD ["sh", "-c", "python manage.py migrate && gunicorn z1_backend.wsgi:application --bind 0.0.0.0:8000 --workers 2 --threads 2 --worker-class gthread --max-requests 1000 --timeout 30"]

