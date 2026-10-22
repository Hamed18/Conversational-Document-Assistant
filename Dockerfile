FROM python:3.13-slim

WORKDIR /app

# Prevent Python from writing .pyc and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

# Install ca-certificates and curl for health probes
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Create uploads directory for PDF documents
RUN mkdir -p /app/uploads

# Copy application source code
COPY main.py data_loader.py vector_db.py custom_types.py database.py auth.py ./

EXPOSE 8000

# Run FastAPI app dynamically binding to $PORT provided by Render
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
