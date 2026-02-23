# Docker Containerization Design

**Issue:** #56
**Date:** 2026-02-23
**Status:** Approved

## Overview

Containerize the textractor application using Docker to enable deployment on AWS, GCP, and other cloud platforms. The design uses a multi-stage build for optimal image size and follows best practices for production deployments.

## Goals

1. Create production-ready Docker image for textractor
2. Enable easy local development with Docker Compose
3. Support deployment to AWS (ECS/Fargate) and GCP (Cloud Run)
4. Maintain small image size and fast build times
5. Provide clear documentation for Docker usage

## Architecture Decisions

### Approach: Multi-Stage Dockerfile

**Selected:** Multi-stage build with Node.js frontend builder + Python runtime

**Rationale:**
- Smallest image size (~200-300MB vs 1GB+ for single-stage)
- Matches existing production pattern (FastAPI serves static frontend)
- Single container simplifies cloud deployment
- Industry standard for full-stack applications
- Fast builds with effective layer caching

**Rejected alternatives:**
- Single-stage build: Results in unnecessarily large images with Node.js runtime included
- Separate frontend/backend containers: Overkill for this architecture, adds orchestration complexity

## Docker Architecture

### Multi-Stage Build Structure

**Stage 1: Frontend Builder**
- Base image: `node:20-alpine` (lightweight Node.js)
- Steps:
  1. Copy `frontend/package*.json`
  2. Run `npm ci` (clean install for reproducible builds)
  3. Copy `frontend/` source code
  4. Run `npm run build` → generates `frontend/dist/`
- Output: Built static files ready for production

**Stage 2: Runtime**
- Base image: `python:3.10-slim` (minimal Python environment)
- Steps:
  1. Install `uv` package manager
  2. Copy `pyproject.toml` and run `uv sync`
  3. Copy backend source (`src/textractor/`)
  4. Copy built frontend from Stage 1 → `/app/frontend/dist/`
  5. Create non-root user for security
  6. Expose port 8000
  7. Set entrypoint: `uv run textractor`

### Build Optimizations

**Layer caching strategy:**
- Dependencies installed before source code
- Only rebuilds affected layers when files change
- Package manifests copied before source for cache efficiency

**.dockerignore contents:**
- `node_modules/`
- `.git/`
- `data/`
- `__pycache__/`
- `*.pyc`
- `.env`
- `frontend/dist/`
- `.worktrees/`
- Test files and development artifacts

**Security:**
- Run as non-root user
- Minimal base images (slim variants)
- No secrets in image layers

## Volume & Data Management

### Volume Strategy

**Decision:** Docker-managed volumes for data, host mount for SNOMED terminology

**Volumes:**

1. **`textractor-data`** (Docker-managed volume)
   - Purpose: User documents and annotations
   - Mount point: `/app/data/documents/`
   - Contents: `.json` files and `.ann.json` annotations
   - Lifecycle: Persists across container restarts/rebuilds
   - Backup: `docker cp` or volume inspection commands

2. **`textractor-terminology`** (Host volume mount)
   - Purpose: SNOMED CT reference data (3.8GB)
   - Mount point: `/app/data/terminology/`
   - Contents: `SnomedCT/` directory and auto-generated `snomed.db`
   - Source: User provides from host filesystem
   - Rationale: Read-only reference data, typically shared across environments

### Environment Variables

**Configuration via environment:**

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | Yes (for pre-annotation) | - | Anthropic API key for Claude access |
| `TEXTRACTOR_DOC_ROOT` | No | `/app/data/documents` | Document storage directory |
| `TEXTRACTOR_LLM_MODEL` | No | `claude-sonnet-4-5` | Model for annotation generation |
| `TEXTRACTOR_FUZZY_THRESHOLD` | No | `90` | Fuzzy matching threshold (0-100) |

**Loading strategy:**
- Local development: Load from `.env` file via docker-compose
- Production: Explicit environment variables or cloud secret management
- Fallback: Sensible defaults where possible

## Docker Compose Configuration

### docker-compose.yml

```yaml
version: '3.8'

services:
  textractor:
    build: .
    container_name: textractor
    ports:
      - "8000:8000"
    volumes:
      - textractor-data:/app/data/documents
      - ./data/terminology:/app/data/terminology:ro  # read-only mount
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

### .env.example Template

```bash
# Anthropic API Configuration
ANTHROPIC_API_KEY=your_api_key_here

# LLM Configuration
TEXTRACTOR_LLM_MODEL=claude-sonnet-4-5
TEXTRACTOR_FUZZY_THRESHOLD=90

# Optional: Override document root (defaults to Docker volume)
# TEXTRACTOR_DOC_ROOT=/app/data/documents
```

### Usage Commands

```bash
# Initial setup
cp .env.example .env
# Edit .env with your API key

# Start application
docker-compose up -d

# View logs
docker-compose logs -f

# Stop application
docker-compose down

# Stop and remove volumes (deletes data!)
docker-compose down -v
```

## Cloud Deployment

### AWS Deployment (ECS/Fargate)

**Components:**
- **Amazon ECR:** Container image registry
- **ECS/Fargate:** Serverless container orchestration
- **EFS:** Elastic File System for persistent volumes
- **AWS Secrets Manager:** Secure API key storage
- **Application Load Balancer:** HTTPS/SSL termination
- **CloudWatch:** Logging and monitoring

**Deployment steps:**
1. Push image to ECR: `docker push <account>.dkr.ecr.<region>.amazonaws.com/textractor:latest`
2. Create EFS file systems for data and terminology volumes
3. Define ECS Task with EFS mount points
4. Configure Secrets Manager for `ANTHROPIC_API_KEY`
5. Create ECS Service with ALB integration
6. Configure auto-scaling policies

**Key configurations:**
- Task CPU/Memory: 1 vCPU / 2GB RAM (adjustable)
- Health check: `/docs` endpoint
- Container port: 8000
- Volume mounts: EFS → `/app/data/documents` and `/app/data/terminology`

### GCP Deployment (Cloud Run)

**Components:**
- **Artifact Registry:** Container image storage
- **Cloud Run:** Fully managed container platform
- **Cloud Filestore:** NFS for persistent volumes
- **Secret Manager:** Secure credential storage
- **Cloud Load Balancing:** HTTPS/custom domains
- **Cloud Logging:** Centralized logging

**Deployment steps:**
1. Push image to Artifact Registry: `docker push <region>-docker.pkg.dev/<project>/textractor/textractor:latest`
2. Create Cloud Filestore instances for volumes
3. Deploy Cloud Run service with volume mounts
4. Configure Secret Manager for API key
5. Set up Cloud Load Balancer with SSL certificate
6. Configure auto-scaling (request-based)

**Key configurations:**
- Memory: 2GiB
- CPU: 2
- Min instances: 0 (scale to zero)
- Max instances: 10
- Health check: `/docs` endpoint
- Volume mounts: Filestore NFS → container paths

### Image Distribution (Docker Hub)

**Optional public/private image publishing:**

**Tagging strategy:**
- `latest` - Most recent build from main branch
- `v0.1.0` - Semantic version tags
- `sha-<commit>` - Specific commit SHAs for reproducibility

**Automated builds:**
- GitHub Actions workflow for CI/CD
- Build on push to main branch
- Tag on release creation
- Multi-architecture support (amd64, arm64)

**Repository naming:**
- `schorndorfer/textractor:latest`
- Public for open-source distribution
- Private for internal deployments

## Documentation Updates

### CLAUDE.md Additions

New "Docker Deployment" section:

```markdown
## Docker Deployment

### Quick Start

```bash
# Using Docker Compose (recommended)
cp .env.example .env  # Configure your ANTHROPIC_API_KEY
docker-compose up -d

# Access application
open http://localhost:8000
```

### Requirements

- Docker 20.10+ and Docker Compose 2.0+
- SNOMED CT data in `data/terminology/SnomedCT/`
- Anthropic API key

### Volume Management

**Data backup:**
```bash
docker run --rm -v textractor-data:/data -v $(pwd):/backup alpine tar czf /backup/textractor-data.tar.gz -C /data .
```

**Data restore:**
```bash
docker run --rm -v textractor-data:/data -v $(pwd):/backup alpine sh -c "cd /data && tar xzf /backup/textractor-data.tar.gz"
```

### Cloud Deployment

See `docs/DOCKER.md` for detailed AWS and GCP deployment guides.
```

### README.md Additions

Add Docker section near top:

```markdown
## 🐳 Docker Deployment

Run textractor in a container:

```bash
docker-compose up -d
```

See [Docker deployment guide](docs/DOCKER.md) for details.

## Prerequisites

**Native:**
- Python 3.10+, uv, Node.js 20+

**Docker:**
- Docker 20.10+ and Docker Compose 2.0+
```

### Makefile Additions

```makefile
docker-build:  ## Build Docker image
	docker build -t textractor:latest .

docker-up:  ## Start with docker-compose
	docker-compose up -d

docker-down:  ## Stop containers
	docker-compose down

docker-logs:  ## View container logs
	docker-compose logs -f

docker-clean:  ## Remove containers and volumes (WARNING: deletes data)
	docker-compose down -v
	docker volume rm textractor-data 2>/dev/null || true

docker-shell:  ## Open shell in running container
	docker-compose exec textractor /bin/bash
```

### New Files

1. **`Dockerfile`** - Multi-stage build configuration
2. **`docker-compose.yml`** - Local orchestration setup
3. **`.dockerignore`** - Build context exclusions
4. **`.env.example`** - Environment variable template
5. **`docs/DOCKER.md`** - Comprehensive Docker deployment guide

## Testing Strategy

### Local Testing

```bash
# Build image
docker build -t textractor:test .

# Run with test data
docker run -p 8000:8000 \
  -v $(pwd)/data/terminology:/app/data/terminology:ro \
  -e ANTHROPIC_API_KEY=test \
  textractor:test

# Access docs
curl http://localhost:8000/docs
```

### Integration Testing

- Verify frontend loads at `http://localhost:8000`
- Test document upload/annotation workflow
- Verify SNOMED search functionality
- Test pre-annotation with Claude API
- Confirm data persists after container restart

### Cloud Testing

- Deploy to staging environment (AWS/GCP)
- Verify volume mounts and data persistence
- Test auto-scaling behavior under load
- Validate secret management integration
- Check logging and monitoring

## Security Considerations

1. **No secrets in image:** API keys via environment only
2. **Non-root user:** Container runs as unprivileged user
3. **Minimal base images:** Reduce attack surface
4. **Read-only SNOMED mount:** Prevent accidental modifications
5. **Health checks:** Enable container orchestration monitoring
6. **HTTPS in production:** Use cloud load balancers for SSL

## Success Criteria

- ✅ Docker image builds successfully under 500MB
- ✅ Application runs and serves frontend correctly
- ✅ Data persists across container restarts
- ✅ SNOMED terminology loads and searches work
- ✅ docker-compose provides single-command startup
- ✅ Documentation covers local and cloud deployment
- ✅ Image can be deployed to AWS ECS and GCP Cloud Run

## Future Enhancements

- Multi-architecture builds (ARM64 for AWS Graviton)
- GitHub Actions CI/CD pipeline
- Docker image scanning for vulnerabilities
- Kubernetes manifests (Helm charts)
- Development container with hot-reload
- Database migrations automation
- Backup/restore automation scripts

## References

- [Docker Multi-Stage Builds](https://docs.docker.com/build/building/multi-stage/)
- [AWS ECS Best Practices](https://docs.aws.amazon.com/AmazonECS/latest/bestpracticesguide/)
- [GCP Cloud Run Documentation](https://cloud.google.com/run/docs)
- [Docker Compose Specification](https://docs.docker.com/compose/compose-file/)
