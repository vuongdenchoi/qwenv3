FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
# Đặt domain public để Wan API truy cập ảnh gốc (override bằng -e hoặc docker-compose)
ENV PUBLIC_BASE_URL=https://your-domain.com

WORKDIR /app

# System libs often needed by scientific/python image stack.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first for better layer caching.
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install -r /app/backend/requirements.txt

# Copy project sources.
COPY backend /app/backend
COPY frontend /app/frontend
COPY design_rules /app/design_rules

WORKDIR /app/backend

RUN python knowledge_base/build_index.py

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
