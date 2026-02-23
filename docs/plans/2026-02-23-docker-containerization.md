# Docker Containerization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Containerize textractor application with multi-stage Docker build, docker-compose orchestration, and cloud deployment readiness.

**Architecture:** Multi-stage Dockerfile (Node.js builds frontend → Python serves backend + static files). Docker Compose manages volumes, environment, and local orchestration. Documentation covers local dev and AWS/GCP deployment.

**Tech Stack:** Docker, Docker Compose, Node.js 20 Alpine, Python 3.10 Slim, uv package manager

---

## Task 1: Create .dockerignore

**Files:**
- Create: `.dockerignore`

**Step 1: Create .dockerignore file**

Create file to exclude unnecessary files from Docker build context, reducing image size and build time.

```
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
*.egg-info/
dist/
build/
.pytest_cache/
.venv/
venv/
ENV/

# Node
node_modules/
npm-debug.log*
yarn-debug.log*
yarn-error.log*

# Frontend build output (will be copied from build stage)
frontend/dist/

# Development
.git/
.gitignore
.worktrees/
.vscode/
.idea/

# Data (mounted as volumes)
data/

# Environment
.env
.env.local

# Documentation
*.md
!README.md
docs/

# Tests
tests/
pytest.ini

# CI/CD
.github/

# OS
.DS_Store
Thumbs.db
```

**Step 2: Verify file creation**

Run: `ls -la .dockerignore`
Expected: File exists

**Step 3: Commit**

```bash
git add .dockerignore
git commit -m "chore: add .dockerignore for Docker build optimization (Issue #56)"
```

---

## Task 2: Create Dockerfile with Multi-Stage Build

**Files:**
- Create: `Dockerfile`

**Step 1: Create Dockerfile with frontend builder stage**

```dockerfile
# Stage 1: Build frontend
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend

# Copy package files and install dependencies
COPY frontend/package*.json ./
RUN npm ci --only=production

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
ENV PATH="/root/.cargo/bin:$PATH"

# Copy Python dependencies file
COPY pyproject.toml ./

# Install Python dependencies
RUN uv sync --no-dev

# Copy backend source
COPY src/ ./src/

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
```

**Step 2: Verify Dockerfile syntax**

Run: `docker build --dry-run . 2>&1 || cat Dockerfile`
Expected: No syntax errors

**Step 3: Commit**

```bash
git add Dockerfile
git commit -m "feat: add multi-stage Dockerfile for containerization (Issue #56)"
```

---

## Task 3: Create docker-compose.yml

**Files:**
- Create: `docker-compose.yml`

**Step 1: Create docker-compose.yml**

```yaml
version: '3.8'

services:
  textractor:
    build: .
    container_name: textractor
    ports:
      - "8000:8000"
    volumes:
      # Docker-managed volume for user documents
      - textractor-data:/app/data/documents
      # Host mount for SNOMED terminology (read-only)
      - ./data/terminology:/app/data/terminology:ro
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - TEXTRACTOR_DOC_ROOT=/app/data/documents
      - TEXTRACTOR_LLM_MODEL=${TEXTRACTOR_LLM_MODEL:-claude-sonnet-4-5}
      - TEXTRACTOR_FUZZY_THRESHOLD=${TEXTRACTOR_FUZZY_THRESHOLD:-90}
    env_file:
      - .env
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/docs"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

volumes:
  textractor-data:
    name: textractor-data
```

**Step 2: Verify compose file syntax**

Run: `docker-compose config 2>&1 | head -5`
Expected: Parsed YAML output (may warn about missing .env, that's OK)

**Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: add docker-compose for local orchestration (Issue #56)"
```

---

## Task 4: Create .env.example Template

**Files:**
- Create: `.env.example`

**Step 1: Create .env.example template**

```bash
# Anthropic API Configuration
# Required for pre-annotation functionality
ANTHROPIC_API_KEY=your_api_key_here

# LLM Configuration
# Model to use for annotation generation
TEXTRACTOR_LLM_MODEL=claude-sonnet-4-5

# Fuzzy matching threshold for span validation (0-100)
TEXTRACTOR_FUZZY_THRESHOLD=90

# Optional: Override document root
# Defaults to Docker volume: /app/data/documents
# TEXTRACTOR_DOC_ROOT=/app/data/documents
```

**Step 2: Verify file creation**

Run: `cat .env.example | grep ANTHROPIC_API_KEY`
Expected: Shows the ANTHROPIC_API_KEY line

**Step 3: Update .gitignore to exclude .env**

Run: `grep -q "^\.env$" .gitignore || echo ".env" >> .gitignore`
Expected: .env added to .gitignore if not already present

**Step 4: Commit**

```bash
git add .env.example .gitignore
git commit -m "feat: add .env.example template for Docker (Issue #56)"
```

---

## Task 5: Update Makefile with Docker Commands

**Files:**
- Modify: `Makefile`

**Step 1: Read current Makefile**

Run: `cat Makefile`
Expected: See existing targets

**Step 2: Add Docker targets to Makefile**

Add these targets at the end of the Makefile:

```makefile

# Docker commands
docker-build:  ## Build Docker image
	docker build -t textractor:latest .

docker-up:  ## Start application with docker-compose
	docker-compose up -d

docker-down:  ## Stop docker-compose containers
	docker-compose down

docker-logs:  ## View container logs
	docker-compose logs -f

docker-restart:  ## Restart containers
	docker-compose restart

docker-shell:  ## Open shell in running container
	docker-compose exec textractor /bin/bash

docker-clean:  ## Remove containers and volumes (WARNING: deletes data)
	@echo "WARNING: This will delete all container data!"
	@read -p "Are you sure? [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		docker-compose down -v; \
		docker volume rm textractor-data 2>/dev/null || true; \
	fi

docker-test:  ## Test Docker build and run
	docker build -t textractor:test .
	@echo "✓ Docker build successful"
```

**Step 3: Verify Makefile syntax**

Run: `make -n docker-build 2>&1`
Expected: Shows docker build command (dry-run)

**Step 4: Test help output**

Run: `make help | grep docker`
Expected: Shows all docker-* targets with descriptions

**Step 5: Commit**

```bash
git add Makefile
git commit -m "feat: add Docker targets to Makefile (Issue #56)"
```

---

## Task 6: Update CLAUDE.md with Docker Section

**Files:**
- Modify: `CLAUDE.md`

**Step 1: Read current CLAUDE.md structure**

Run: `head -50 CLAUDE.md`
Expected: See current structure with "Common Commands" section

**Step 2: Add Docker section after Quick Start section**

Insert this section after the "Quick Start (Makefile - Recommended)" section:

```markdown

### Docker (Containerized)

```bash
# Initial setup
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY

# Start with docker-compose (recommended)
make docker-up              # or: docker-compose up -d

# View logs
make docker-logs            # or: docker-compose logs -f

# Stop
make docker-down            # or: docker-compose down

# Access application
open http://localhost:8000
```

**Requirements:**
- Docker 20.10+ and Docker Compose 2.0+
- SNOMED CT data in `data/terminology/SnomedCT/` (mounted as volume)
- Anthropic API key in `.env` file

**Volume Management:**

Backup data:
```bash
docker run --rm -v textractor-data:/data -v $(pwd):/backup alpine tar czf /backup/textractor-data-backup.tar.gz -C /data .
```

Restore data:
```bash
docker run --rm -v textractor-data:/data -v $(pwd):/backup alpine sh -c "cd /data && tar xzf /backup/textractor-data-backup.tar.gz"
```

**See `docs/DOCKER.md` for comprehensive deployment guide including AWS and GCP.**

```

**Step 3: Verify markdown formatting**

Run: `grep -A 5 "### Docker" CLAUDE.md`
Expected: Shows the new Docker section

**Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add Docker section to CLAUDE.md (Issue #56)"
```

---

## Task 7: Update README.md with Docker Quick Start

**Files:**
- Modify: `README.md`
- Read first to understand structure

**Step 1: Check if README.md exists**

Run: `test -f README.md && echo "EXISTS" || echo "MISSING"`
Expected: EXISTS or MISSING

**Step 2: If README.md exists, add Docker badge and section**

If README.md exists, add near the top (after title):

```markdown

## 🐳 Quick Start with Docker

```bash
# One-time setup
cp .env.example .env
# Edit .env with your ANTHROPIC_API_KEY

# Start application
docker-compose up -d

# Access at http://localhost:8000
```

See [Docker Deployment Guide](docs/DOCKER.md) for comprehensive instructions.

## Prerequisites

**Native Installation:**
- Python 3.10+
- Node.js 20+
- uv package manager

**Docker (Recommended):**
- Docker 20.10+
- Docker Compose 2.0+

```

**Step 3: If README.md doesn't exist, create basic one**

```markdown
# Textractor

Clinical text annotation tool with FastAPI backend and React frontend.

## 🐳 Quick Start with Docker

```bash
cp .env.example .env
# Edit .env with your ANTHROPIC_API_KEY

docker-compose up -d
# Access at http://localhost:8000
```

## Documentation

- [Docker Deployment Guide](docs/DOCKER.md)
- [Project Documentation](CLAUDE.md)

## License

See LICENSE file.
```

**Step 4: Commit**

```bash
git add README.md
git commit -m "docs: add Docker quick start to README (Issue #56)"
```

---

## Task 8: Create Comprehensive docs/DOCKER.md Guide

**Files:**
- Create: `docs/DOCKER.md`

**Step 1: Create docs directory if needed**

Run: `mkdir -p docs`
Expected: Directory exists

**Step 2: Create comprehensive Docker guide**

```markdown
# Docker Deployment Guide

Complete guide for deploying textractor with Docker, including local development and cloud deployments (AWS ECS, GCP Cloud Run).

## Table of Contents

- [Local Development](#local-development)
- [Building the Image](#building-the-image)
- [Running with Docker](#running-with-docker)
- [Docker Compose](#docker-compose)
- [Volume Management](#volume-management)
- [AWS Deployment](#aws-deployment)
- [GCP Deployment](#gcp-deployment)
- [Troubleshooting](#troubleshooting)

---

## Local Development

### Prerequisites

- Docker 20.10 or later
- Docker Compose 2.0 or later
- SNOMED CT data in `data/terminology/SnomedCT/`
- Anthropic API key

### Quick Start

1. **Configure environment:**

```bash
cp .env.example .env
# Edit .env and set your ANTHROPIC_API_KEY
```

2. **Start application:**

```bash
docker-compose up -d
```

3. **Access application:**

Open http://localhost:8000 in your browser.

4. **View logs:**

```bash
docker-compose logs -f
```

5. **Stop application:**

```bash
docker-compose down
```

---

## Building the Image

### Build Locally

```bash
# Using make
make docker-build

# Or directly
docker build -t textractor:latest .
```

### Build Arguments

The Dockerfile uses multi-stage builds for optimization:

- **Stage 1 (frontend-builder):** Builds React frontend with Node.js 20 Alpine
- **Stage 2 (runtime):** Python 3.10 Slim with backend + static files

### Image Size

Expected final image size: ~200-300MB (without SNOMED data)

---

## Running with Docker

### Basic Run Command

```bash
docker run -d \
  --name textractor \
  -p 8000:8000 \
  -v textractor-data:/app/data/documents \
  -v $(pwd)/data/terminology:/app/data/terminology:ro \
  -e ANTHROPIC_API_KEY=your_key_here \
  textractor:latest
```

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | Yes* | - | Anthropic API key (*required for pre-annotation) |
| `TEXTRACTOR_DOC_ROOT` | No | `/app/data/documents` | Document storage directory |
| `TEXTRACTOR_LLM_MODEL` | No | `claude-sonnet-4-5` | Model for annotation generation |
| `TEXTRACTOR_FUZZY_THRESHOLD` | No | `90` | Fuzzy matching threshold (0-100) |

---

## Docker Compose

### Configuration

The `docker-compose.yml` file provides a complete orchestration setup:

```yaml
services:
  textractor:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - textractor-data:/app/data/documents
      - ./data/terminology:/app/data/terminology:ro
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/docs"]
```

### Common Commands

```bash
# Start (detached)
docker-compose up -d

# Start (foreground with logs)
docker-compose up

# Stop
docker-compose down

# Restart
docker-compose restart

# View logs
docker-compose logs -f

# Execute command in container
docker-compose exec textractor /bin/bash

# Rebuild and restart
docker-compose up -d --build
```

---

## Volume Management

### Data Volumes

**textractor-data** (Docker-managed volume):
- Purpose: User documents and annotations
- Location: `/app/data/documents` in container
- Persistence: Survives container restarts

**terminology** (Host bind mount):
- Purpose: SNOMED CT reference data
- Source: `./data/terminology` on host
- Mount: `/app/data/terminology` in container (read-only)

### Backup Data

```bash
# Backup documents and annotations
docker run --rm \
  -v textractor-data:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/textractor-data-backup.tar.gz -C /data .
```

### Restore Data

```bash
# Restore from backup
docker run --rm \
  -v textractor-data:/data \
  -v $(pwd):/backup \
  alpine sh -c "cd /data && tar xzf /backup/textractor-data-backup.tar.gz"
```

### Inspect Volume

```bash
# List volumes
docker volume ls | grep textractor

# Inspect volume details
docker volume inspect textractor-data

# Access volume contents
docker run --rm -v textractor-data:/data alpine ls -la /data
```

### Remove Volumes (DANGER)

```bash
# Stop containers
docker-compose down

# Remove volumes (deletes all data!)
docker-compose down -v
docker volume rm textractor-data
```

---

## AWS Deployment

### Architecture

**Components:**
- Amazon ECR (Elastic Container Registry)
- AWS ECS with Fargate
- Amazon EFS (Elastic File System)
- AWS Secrets Manager
- Application Load Balancer
- Amazon CloudWatch

### Deployment Steps

#### 1. Build and Push Image to ECR

```bash
# Authenticate to ECR
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin \
  123456789012.dkr.ecr.us-east-1.amazonaws.com

# Create ECR repository
aws ecr create-repository --repository-name textractor

# Build and tag image
docker build -t textractor:latest .
docker tag textractor:latest \
  123456789012.dkr.ecr.us-east-1.amazonaws.com/textractor:latest

# Push to ECR
docker push 123456789012.dkr.ecr.us-east-1.amazonaws.com/textractor:latest
```

#### 2. Create EFS File Systems

```bash
# Create EFS for document storage
aws efs create-file-system \
  --performance-mode generalPurpose \
  --throughput-mode bursting \
  --tags Key=Name,Value=textractor-data

# Create EFS for SNOMED terminology
aws efs create-file-system \
  --performance-mode generalPurpose \
  --throughput-mode bursting \
  --tags Key=Name,Value=textractor-terminology
```

#### 3. Store API Key in Secrets Manager

```bash
aws secretsmanager create-secret \
  --name textractor/anthropic-api-key \
  --secret-string "your_api_key_here"
```

#### 4. Create ECS Task Definition

```json
{
  "family": "textractor",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "1024",
  "memory": "2048",
  "containerDefinitions": [
    {
      "name": "textractor",
      "image": "123456789012.dkr.ecr.us-east-1.amazonaws.com/textractor:latest",
      "portMappings": [
        {
          "containerPort": 8000,
          "protocol": "tcp"
        }
      ],
      "environment": [
        {
          "name": "TEXTRACTOR_DOC_ROOT",
          "value": "/app/data/documents"
        }
      ],
      "secrets": [
        {
          "name": "ANTHROPIC_API_KEY",
          "valueFrom": "arn:aws:secretsmanager:us-east-1:123456789012:secret:textractor/anthropic-api-key"
        }
      ],
      "mountPoints": [
        {
          "sourceVolume": "documents",
          "containerPath": "/app/data/documents"
        },
        {
          "sourceVolume": "terminology",
          "containerPath": "/app/data/terminology",
          "readOnly": true
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/textractor",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "ecs"
        }
      },
      "healthCheck": {
        "command": ["CMD-SHELL", "curl -f http://localhost:8000/docs || exit 1"],
        "interval": 30,
        "timeout": 5,
        "retries": 3,
        "startPeriod": 60
      }
    }
  ],
  "volumes": [
    {
      "name": "documents",
      "efsVolumeConfiguration": {
        "fileSystemId": "fs-xxxxxxxxx",
        "transitEncryption": "ENABLED"
      }
    },
    {
      "name": "terminology",
      "efsVolumeConfiguration": {
        "fileSystemId": "fs-yyyyyyyyy",
        "transitEncryption": "ENABLED"
      }
    }
  ]
}
```

#### 5. Create ECS Service

```bash
aws ecs create-service \
  --cluster textractor-cluster \
  --service-name textractor \
  --task-definition textractor:1 \
  --desired-count 2 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx,subnet-yyy],securityGroups=[sg-zzz],assignPublicIp=ENABLED}" \
  --load-balancers "targetGroupArn=arn:aws:elasticloadbalancing:...,containerName=textractor,containerPort=8000"
```

---

## GCP Deployment

### Architecture

**Components:**
- Google Artifact Registry
- Cloud Run
- Cloud Filestore (NFS)
- Secret Manager
- Cloud Load Balancing
- Cloud Logging

### Deployment Steps

#### 1. Build and Push Image to Artifact Registry

```bash
# Configure Docker for Artifact Registry
gcloud auth configure-docker us-central1-docker.pkg.dev

# Create repository
gcloud artifacts repositories create textractor \
  --repository-format=docker \
  --location=us-central1

# Build and tag image
docker build -t textractor:latest .
docker tag textractor:latest \
  us-central1-docker.pkg.dev/PROJECT_ID/textractor/textractor:latest

# Push to Artifact Registry
docker push us-central1-docker.pkg.dev/PROJECT_ID/textractor/textractor:latest
```

#### 2. Create Cloud Filestore Instances

```bash
# Create Filestore for document storage
gcloud filestore instances create textractor-data \
  --zone=us-central1-a \
  --tier=BASIC_HDD \
  --file-share=name=documents,capacity=1TB \
  --network=name=default

# Create Filestore for SNOMED terminology
gcloud filestore instances create textractor-terminology \
  --zone=us-central1-a \
  --tier=BASIC_HDD \
  --file-share=name=terminology,capacity=100GB \
  --network=name=default
```

#### 3. Store API Key in Secret Manager

```bash
echo -n "your_api_key_here" | \
  gcloud secrets create anthropic-api-key \
  --data-file=-
```

#### 4. Deploy to Cloud Run

```bash
gcloud run deploy textractor \
  --image=us-central1-docker.pkg.dev/PROJECT_ID/textractor/textractor:latest \
  --platform=managed \
  --region=us-central1 \
  --memory=2Gi \
  --cpu=2 \
  --port=8000 \
  --set-env-vars="TEXTRACTOR_DOC_ROOT=/app/data/documents" \
  --set-secrets="ANTHROPIC_API_KEY=anthropic-api-key:latest" \
  --execution-environment=gen2 \
  --min-instances=0 \
  --max-instances=10 \
  --allow-unauthenticated
```

**Note:** Cloud Run currently has limited NFS volume support. For production with persistent volumes, consider using GKE (Google Kubernetes Engine) instead.

---

## Troubleshooting

### Container Won't Start

**Check logs:**
```bash
docker-compose logs textractor
```

**Common issues:**
- Missing `ANTHROPIC_API_KEY` in `.env`
- SNOMED directory not found at `./data/terminology/SnomedCT/`
- Port 8000 already in use

### SNOMED Search Not Working

**Verify SNOMED mount:**
```bash
docker-compose exec textractor ls -la /app/data/terminology/SnomedCT/
```

**Expected:** RF2 files visible in container

**Fix:** Ensure `data/terminology/SnomedCT/` exists on host with proper files

### Data Not Persisting

**Check volume:**
```bash
docker volume inspect textractor-data
```

**Verify mount:**
```bash
docker-compose exec textractor ls -la /app/data/documents/
```

**Fix:** Ensure volume is properly defined in `docker-compose.yml`

### Health Check Failing

**Test endpoint manually:**
```bash
docker-compose exec textractor curl http://localhost:8000/docs
```

**Expected:** HTML response from FastAPI docs

**Fix:** Ensure application starts correctly and port 8000 is listening

### Permission Errors

**Issue:** Container can't write to volumes

**Fix:** The container runs as user `textractor` (UID 1000). Ensure volume permissions allow writes.

```bash
# If using host mount instead of Docker volume
sudo chown -R 1000:1000 ./data/documents/
```

### Build Fails

**Check Docker version:**
```bash
docker --version
docker-compose --version
```

**Required:** Docker 20.10+, Compose 2.0+

**Clear build cache:**
```bash
docker builder prune -a
docker-compose build --no-cache
```

### Frontend Not Loading

**Verify frontend files in image:**
```bash
docker-compose exec textractor ls -la /app/frontend/dist/
```

**Expected:** `index.html` and asset files present

**Fix:** Rebuild image with `docker-compose build --no-cache`

---

## Performance Tuning

### Resource Limits

**docker-compose.yml:**
```yaml
services:
  textractor:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '1'
          memory: 1G
```

### Health Check Tuning

Adjust health check timing for slower environments:

```yaml
healthcheck:
  interval: 60s
  timeout: 20s
  start_period: 120s
  retries: 5
```

---

## Security Best Practices

1. **Never commit `.env`** - Use `.env.example` as template
2. **Use secrets management** - AWS Secrets Manager / GCP Secret Manager in production
3. **Read-only SNOMED mount** - Prevent accidental modifications
4. **Non-root user** - Container runs as UID 1000
5. **HTTPS in production** - Use load balancer for SSL termination
6. **Regular updates** - Keep base images updated for security patches

---

## Additional Resources

- [Docker Documentation](https://docs.docker.com/)
- [Docker Compose Reference](https://docs.docker.com/compose/compose-file/)
- [AWS ECS Best Practices](https://docs.aws.amazon.com/AmazonECS/latest/bestpracticesguide/)
- [GCP Cloud Run Documentation](https://cloud.google.com/run/docs)
- [Textractor Project Documentation](../CLAUDE.md)
```

**Step 3: Commit**

```bash
git add docs/DOCKER.md
git commit -m "docs: add comprehensive Docker deployment guide (Issue #56)"
```

---

## Task 9: Test Docker Build

**Files:**
- Test: `Dockerfile`

**Step 1: Clean any existing builds**

Run: `docker rmi textractor:test 2>/dev/null || echo "No existing image"`
Expected: Image removed or doesn't exist

**Step 2: Build Docker image**

Run: `make docker-build`
Expected: Build succeeds, outputs "Successfully tagged textractor:latest"

**Step 3: Check image size**

Run: `docker images textractor:latest --format "{{.Size}}"`
Expected: Size around 200-500MB (reasonable for Python + frontend)

**Step 4: Inspect image layers**

Run: `docker history textractor:latest | head -10`
Expected: Shows multi-stage build layers

**Step 5: Verify non-root user**

Run: `docker run --rm textractor:latest whoami`
Expected: "textractor" (not root)

**Step 6: Verify frontend dist exists**

Run: `docker run --rm textractor:latest ls /app/frontend/dist/`
Expected: Shows index.html and assets

---

## Task 10: Test Docker Compose

**Files:**
- Test: `docker-compose.yml`

**Step 1: Create test .env file**

```bash
cat > .env << 'EOF'
ANTHROPIC_API_KEY=test_key_for_docker_compose
TEXTRACTOR_LLM_MODEL=claude-sonnet-4-5
TEXTRACTOR_FUZZY_THRESHOLD=90
EOF
```

**Step 2: Start with docker-compose**

Run: `make docker-up`
Expected: Container starts successfully

**Step 3: Wait for health check**

Run: `sleep 45 && docker-compose ps`
Expected: textractor service shows "healthy" status

**Step 4: Test application endpoint**

Run: `curl -f http://localhost:8000/docs 2>&1 | grep -q "FastAPI" && echo "SUCCESS" || echo "FAILED"`
Expected: "SUCCESS"

**Step 5: Check logs for errors**

Run: `docker-compose logs textractor | grep -i error`
Expected: No critical errors (SNOMED warnings OK if data not present)

**Step 6: Test volume persistence**

```bash
# Create test file in volume
docker-compose exec textractor sh -c 'echo "test" > /app/data/documents/test.txt'

# Restart container
docker-compose restart

# Check file persists
docker-compose exec textractor cat /app/data/documents/test.txt
```
Expected: "test" content persists after restart

**Step 7: Stop and clean up**

Run: `make docker-down`
Expected: Containers stopped, volumes persist

---

## Task 11: Final Integration Test and Commit

**Files:**
- Test: All Docker components

**Step 1: Run complete integration test**

```bash
# Start fresh
make docker-clean || true

# Build and start
make docker-build
make docker-up

# Wait for startup
sleep 45

# Test endpoints
curl -f http://localhost:8000/docs > /dev/null 2>&1 && echo "✓ Docs accessible"
curl -f http://localhost:8000/api/documents > /dev/null 2>&1 && echo "✓ API accessible"
curl -f http://localhost:8000/ > /dev/null 2>&1 && echo "✓ Frontend accessible"

# Check logs
docker-compose logs --tail=50 textractor

# Stop
make docker-down
```

Expected: All curl tests pass, no critical errors in logs

**Step 2: Verify all files are committed**

Run: `git status`
Expected: Clean working directory or only untracked .env

**Step 3: Create feature branch and push**

```bash
git checkout -b feature/docker-containerization-issue-56

# Ensure all changes are committed
git log --oneline -10

# Push to remote
git push -u origin feature/docker-containerization-issue-56
```

Expected: Branch pushed successfully

**Step 4: Create summary commit if needed**

If individual commits weren't made, create one now:

```bash
git add -A
git commit -m "feat: complete Docker containerization (Issue #56)

- Multi-stage Dockerfile (Node.js builder + Python runtime)
- docker-compose.yml with volume management
- .dockerignore for build optimization
- .env.example template
- Makefile targets for Docker commands
- Updated CLAUDE.md and README.md
- Comprehensive docs/DOCKER.md deployment guide
- Tested local build and docker-compose orchestration

Image size: ~200-300MB
Supports: Local dev, AWS ECS, GCP Cloud Run

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

**Step 5: Verify complete implementation**

Checklist:
- [ ] `.dockerignore` created
- [ ] `Dockerfile` with multi-stage build
- [ ] `docker-compose.yml` configured
- [ ] `.env.example` template
- [ ] `Makefile` updated with docker-* targets
- [ ] `CLAUDE.md` has Docker section
- [ ] `README.md` has Docker quick start
- [ ] `docs/DOCKER.md` comprehensive guide
- [ ] Docker build succeeds (image < 500MB)
- [ ] docker-compose starts successfully
- [ ] Application accessible at localhost:8000
- [ ] Health checks passing
- [ ] Volume persistence working

---

## Task 12: Create Pull Request

**Files:**
- GitHub PR

**Step 1: Generate PR description**

```bash
cat << 'EOF'
## Summary

Implements Docker containerization for textractor application (closes #56).

## Changes

### Core Docker Files
- **Dockerfile**: Multi-stage build (Node.js → Python, ~250MB final image)
- **docker-compose.yml**: Local orchestration with volumes and environment
- **.dockerignore**: Build optimization (excludes dev files)
- **.env.example**: Environment variable template

### Documentation
- **docs/DOCKER.md**: Comprehensive deployment guide (local, AWS ECS, GCP Cloud Run)
- **CLAUDE.md**: Added Docker section with quick start
- **README.md**: Added Docker quick start

### Developer Tools
- **Makefile**: Added docker-build, docker-up, docker-down, docker-logs, docker-clean

## Architecture

**Multi-stage build:**
1. Node.js 20 Alpine builds frontend → `dist/`
2. Python 3.10 Slim installs backend + copies frontend

**Volumes:**
- `textractor-data`: Docker-managed volume for documents/annotations
- `./data/terminology`: Host mount for SNOMED CT (3.8GB, read-only)

**Environment:**
- `ANTHROPIC_API_KEY` via .env or secrets manager
- Defaults for all optional configs

## Testing

- ✅ Docker build succeeds (~250MB image)
- ✅ docker-compose starts application
- ✅ Application accessible at :8000
- ✅ Health checks passing
- ✅ Frontend loads correctly
- ✅ API endpoints functional
- ✅ Volume persistence verified

## Deployment Ready

- **Local dev**: `docker-compose up -d`
- **AWS ECS/Fargate**: See docs/DOCKER.md § AWS Deployment
- **GCP Cloud Run**: See docs/DOCKER.md § GCP Deployment

## Usage

```bash
# Quick start
cp .env.example .env
# Edit .env with ANTHROPIC_API_KEY
make docker-up

# Access at http://localhost:8000
```

Closes #56
EOF
```

**Step 2: Create PR using GitHub CLI**

Run: `gh pr create --title "feat: Docker containerization for AWS/GCP deployment (Issue #56)" --body "$(cat << 'EOF'
[Paste the PR description from Step 1]
EOF
)"`

Expected: PR created and URL returned

**Step 3: Link PR to issue**

The "Closes #56" in PR description automatically links it.

**Step 4: Announce completion**

```
✅ Docker containerization complete!

📦 Files created:
- Dockerfile (multi-stage)
- docker-compose.yml
- .dockerignore
- .env.example
- docs/DOCKER.md

📝 Documentation updated:
- CLAUDE.md
- README.md
- Makefile

🧪 Testing verified:
- Docker build: SUCCESS (~250MB)
- docker-compose up: SUCCESS
- Application: Running on :8000
- Health checks: PASSING

🚀 Ready for deployment:
- Local: docker-compose up -d
- AWS ECS: See docs/DOCKER.md
- GCP Cloud Run: See docs/DOCKER.md

PR: [link from gh pr create output]
```

---

## Testing Checklist

After implementation, verify:

- [ ] `docker build .` succeeds
- [ ] Image size is reasonable (< 500MB)
- [ ] `docker-compose up` starts without errors
- [ ] Application accessible at `http://localhost:8000`
- [ ] Frontend loads (check browser)
- [ ] API docs accessible at `http://localhost:8000/docs`
- [ ] Health check endpoint returns 200
- [ ] Volume persists data after restart
- [ ] SNOMED mount is read-only
- [ ] Logs show no critical errors
- [ ] `make docker-*` commands work
- [ ] Documentation is accurate

---

## Success Criteria

✅ Docker image builds successfully
✅ Image size < 500MB (without SNOMED)
✅ docker-compose provides single-command startup
✅ Application runs and serves frontend correctly
✅ Data persists across container restarts
✅ SNOMED terminology mounts correctly
✅ Documentation covers local and cloud deployment
✅ Makefile includes Docker convenience commands
✅ Ready for AWS ECS and GCP Cloud Run deployment

---

## Notes for Implementation

- **Commit frequency:** After each major file creation (Tasks 1-8) and after testing (Tasks 9-11)
- **Testing approach:** Test build first (Task 9), then integration (Task 10), then full workflow (Task 11)
- **SNOMED data:** Tests work without SNOMED present (application handles gracefully)
- **Environment:** .env file is gitignored, only .env.example committed
- **Non-root user:** Container runs as UID 1000 for security
- **Health checks:** Use `/docs` endpoint (auto-generated by FastAPI)

## Cloud Deployment Notes

**AWS ECS:**
- Use EFS for persistent volumes
- Secrets Manager for API keys
- ALB for load balancing
- Fargate for serverless

**GCP Cloud Run:**
- Cloud Filestore for NFS volumes (or GKE for better support)
- Secret Manager for API keys
- Cloud Load Balancing for HTTPS
- Auto-scaling built-in

Both platforms support direct compose file imports for easier migration from local development.
