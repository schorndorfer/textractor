# Stage 1: Build frontend
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend

# Copy package files and install dependencies
COPY frontend/package*.json ./
RUN npm ci

# Copy frontend source and build
COPY frontend/ ./
RUN npm run build

# Stage 2: Runtime
FROM python:3.10-slim

WORKDIR /app

# Install system dependencies and uv
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && curl -LsSf https://astral.sh/uv/install.sh | sh

# Add uv to PATH
ENV PATH="/root/.local/bin:$PATH"

# Copy Python dependencies files and source
COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/

# Install Python dependencies with locked versions
RUN uv sync --frozen --no-dev

# Copy built frontend from builder stage
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist/

# Create data directories
RUN mkdir -p /app/data/documents /app/data/terminology

# Create non-root user
RUN useradd -m -u 1000 textractor && \
    chown -R textractor:textractor /app

USER textractor

# Expose application port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/docs || exit 1

# Set environment defaults
ENV TEXTRACTOR_DOC_ROOT=/app/data/documents

# Run application
CMD ["uv", "run", "textractor"]
