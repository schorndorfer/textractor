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
```

**Note:** Health checks are defined in the Dockerfile and automatically inherited by Docker Compose. No need to redefine them in `docker-compose.yml`.

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

**Important:** Cloud Run is a stateless platform and does NOT support persistent volumes (including NFS/Filestore). Each container instance has ephemeral storage only, and data will be lost when instances scale down or restart.

**For production deployments requiring persistent storage** (document annotations, SNOMED database), use **Google Kubernetes Engine (GKE)** instead, which provides full support for persistent volumes via Cloud Filestore or Persistent Disks.

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
