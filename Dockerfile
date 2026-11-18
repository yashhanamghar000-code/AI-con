# AI-CON: Containerized Multi-Agent Admission Intelligence Engine & Web Application
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

# Set working directory
WORKDIR /app

# Install system dependencies (build-essential/curl if needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install PyTorch CPU first to avoid pulling heavy CUDA packages inside container
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu

# Copy and install python dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy application files
COPY scripts/ ./scripts/
COPY cutoffs/ ./cutoffs/
COPY vector_index/ ./vector_index/
COPY frontend/ ./frontend/
COPY interactive_terminal.py extract_data_v4.py build_college_list.py ./

# Expose server port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD curl -f http://127.0.0.1:8000/api/health || exit 1

# Start FastAPI application
CMD ["python", "scripts/api_server.py", "--host", "0.0.0.0", "--port", "8000"]

