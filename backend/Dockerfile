FROM python:3.12-slim

# Security: run as non-root user
RUN addgroup --system jobpulse && adduser --system --ingroup jobpulse jobpulse

WORKDIR /app

# Install dependencies first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY . .

# Switch to non-root
USER jobpulse

# Expose port
EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
