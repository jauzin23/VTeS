FROM python:3.11-slim

# Install system utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browser and dependencies
RUN playwright install chromium
RUN playwright install-deps chromium

# Copy application source
COPY . .

# Expose backend port
EXPOSE 3001

# Run the app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "3001"]
