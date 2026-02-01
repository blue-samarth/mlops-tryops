# MLOps Pipeline - Production-Ready Infrastructure

Production-grade MLOps pipeline implementing DevSecOps principles with automated CI/CD, container security, and AWS deployment infrastructure.

## Architecture Overview

The system consists of three core components:

1. **Training Pipeline:** Batch inference with S3-based model registry
2. **API Service:** FastAPI REST endpoint for real-time predictions
3. **Infrastructure:** Terraform-managed AWS resources with OIDC-based authentication

All services run in Docker containers with cryptographic signing, vulnerability scanning, and least-privilege IAM access.

## Current State

### Infrastructure (Terraform)

**Status:** Deployed, 61 resources under management

#### Core Components

- **Authentication:** AWS OIDC provider for GitHub Actions (zero long-lived credentials)
- **Compute:** ECS Fargate task definitions (not deployed yet)
- **Storage:**
  - S3 models bucket (versioning enabled, KMS encryption)
  - S3 logs bucket (access logging, lifecycle policies)
- **Networking:** VPC with public/private subnets, NAT gateways, Internet Gateway
- **Container Registry:** ECR repositories (scan-on-push, KMS encryption)
- **Encryption:** KMS customer-managed keys for all data at rest
- **IAM:** Scoped roles for GitHub Actions, ECS tasks, Lambda functions

**Terraform Features:**
- OIDC thumbprints fetched dynamically
- `force_destroy = true` on all stateful resources for rapid iteration
- Module-based structure for reusability

#### AWS Resources Inventory

| Resource Type | Count | Purpose |
|---------------|-------|---------|
| ECR Repositories | 2 | API + Training images |
| S3 Buckets | 2 | Models + Logs |
| KMS Keys | 3 | ECR, S3, CloudWatch encryption |
| VPC | 1 | Network isolation |
| Subnets | 6 | 3 public + 3 private across AZs |
| IAM Roles | 3 | GitHub Actions, ECS, Lambda |
| Security Groups | 2 | API + Training egress rules |

### CI/CD Workflows

**Status:** Operational with DevSecOps enforcement

#### CI Pipeline ([.github/workflows/ci.yml](.github/workflows/ci.yml))

- **Secrets Scanning:** Gitleaks (800+ credential types)
- **Testing:** pytest with coverage gates (90%/75% thresholds)
- **Linting:** ruff + mypy (non-blocking)
- **Build Verification:** Docker image builds with BuildKit cache
- **Change Detection:** Path-based job optimization

#### CD Pipeline ([.github/workflows/cd.yml](.github/workflows/cd.yml))

- **Vulnerability Scanning:** Trivy (container + filesystem, exit-code enforcement)
- **Image Signing:** Cosign keyless signatures (Sigstore)
- **Deployment:** Multi-tag ECR push (branch, SHA, semver, latest, timestamp)
- **Artifact Management:** Build caching + automatic cleanup
- **Authentication:** AWS OIDC (no static credentials)

### Container Images

**Status:** Built, scanned, signed, not deployed

#### Dockerfile.api (112 lines)

- **Base:** python:3.13-slim-bookworm
- **Build System:** uv 0.9.7 (Python package manager)
- **Security:**
  - Non-root user (mlops:1000)
  - Selective module copying (api, monitoring, utils only)
  - Security patches in builder + runtime stages
  - Minimal attack surface (no build tools in runtime)
- **Dependencies:** 15 packages (FastAPI, Uvicorn, boto3, Prometheus client)

#### Dockerfile.train (118 lines)

- **Base:** python:3.13-slim-bookworm
- **Build System:** uv 0.9.7
- **Security:**
  - Non-root user (mlops:1000)
  - Selective module copying (train, utils only)
  - Scientific computing libs (NumPy, Pandas, scikit-learn)
  - Security patches in builder + runtime stages
- **Dependencies:** 23 packages (scikit-learn, pandas, s3fs, boto3)

### Vulnerability Management

**Status:** All CRITICAL/HIGH vulnerabilities fixed or documented

#### Fixed Vulnerabilities

- CVE-2026-0994: protobuf 6.33.4 → 6.33.5 (HIGH severity DoS)
- CVE-2025-15467: OpenSSL (via apt-get upgrade in runtime)
- CVE-2025-69419: OpenSSL (via apt-get upgrade in runtime)

#### Documented Exceptions ([.trivyignore](.trivyignore))

| CVE | Component | Severity | Justification | Review Date |
|-----|-----------|----------|---------------|-------------|
| CVE-2025-7458 | SQLite | MEDIUM | No fix available, low exploit probability | 2026-03-01 |
| CVE-2023-45853 | zlib | CRITICAL | Won't fix (Debian), not in attack path | 2026-03-01 |
| CVE-2026-0861 | glibc | HIGH | No fix available, limited exposure | 2026-03-01 |
| CVE-2026-24882 | GnuPG | MEDIUM | No fix available, GPG not used in runtime | 2026-03-01 |
| CVE-2023-2953 | libldap | MEDIUM | No fix available, LDAP not used | 2026-03-01 |

**Review Schedule:** Monthly on 1st of each month, owner: blue-samarth

### DevSecOps Maturity Score

**Current:** 81/100 (Phase 1 complete)

| Category | Score | Max | Notes |
|----------|-------|-----|-------|
| Supply Chain Security | 18 | 20 | Missing: Dependabot config |
| Vulnerability Management | 19 | 20 | Missing: CodeQL SAST |
| Authentication & Secrets | 18 | 20 | Zero static credentials |
| Data Protection | 15 | 15 | KMS encryption everywhere |
| Container Security | 11 | 15 | Missing: Read-only filesystem, distroless |
| Runtime Security | 0 | 10 | Missing: GuardDuty, CloudTrail |

## What We Have

### Code Structure

```
src/
├── api/                 # FastAPI REST endpoints
│   ├── routes/         # Endpoint definitions
│   ├── schemas/        # Pydantic models
│   └── services/       # Business logic
├── monitoring/         # Prometheus metrics + Grafana dashboards
├── train/              # Training pipeline
│   ├── baseline_generator.py
│   ├── feature_baseline_generator.py
│   ├── prediction_baseline_generator.py
│   ├── schema_generator.py
│   └── train.py
└── utils/              # Shared modules
    ├── config.py       # Configuration management
    ├── model_storage.py # S3 model versioning
    ├── s3_operations.py
    └── serving_pointer.py
```

### Monitoring (Docker Compose)

- **Prometheus:** Metrics collection on port 9090
- **Grafana:** Dashboards on port 3000
- **Metrics Exported:**
  - API request rate, latency, error rate
  - Training job duration
  - S3 operation metrics
  - Container resource usage

### Dependencies

- **Python:** 3.13 (uv package manager)
- **API:** FastAPI, Uvicorn, Pydantic
- **ML:** scikit-learn, pandas, numpy
- **Cloud:** boto3, s3fs
- **Observability:** prometheus-client
- **Testing:** pytest, pytest-cov

## What's Next

### Phase 1: Kubernetes Deployment (Pending)

#### EKS Cluster

- **Version:** 1.31
- **Node Groups:** Spot + on-demand (cost optimization)
- **Networking:** VPC CNI with security groups for pods
- **Storage:** EBS CSI driver for persistent volumes
- **Access:** IRSA (IAM Roles for Service Accounts)

#### Kubernetes Manifests

- **Deployment:** Rolling update strategy, pod anti-affinity
- **Service:** ClusterIP + LoadBalancer for API
- **HPA:** Horizontal pod autoscaling (target CPU 70%)
- **ConfigMap:** Environment-specific configuration
- **Secret:** S3 bucket names, ECR URLs
- **ServiceAccount:** IRSA annotation for AWS access

#### Service Mesh (Future)

- **Istio:** Traffic management, mTLS, observability
- **Virtual Services:** Canary deployments, traffic splitting
- **Telemetry:** Distributed tracing with Jaeger

### Phase 2: Scheduled Training (Pending)

#### EventBridge Schedule

- **Frequency:** Monthly on 1st (configurable)
- **Target:** ECS Fargate task (training container)
- **IAM:** Task execution role with S3 write permissions
- **Monitoring:** CloudWatch Logs, EventBridge metrics

#### Model Versioning

- S3 prefix: `s3://models-bucket/models/{timestamp}/model.pkl`
- Metadata: Git SHA, training metrics, dataset version
- Serving pointer: `s3://models-bucket/serving/model_metadata.json`

### Phase 3: Security Hardening (Pending)

#### Missing DevSecOps Components

1. **Dependabot Configuration**
   - Weekly dependency updates
   - Auto-merge for patch versions
   - Security-only updates for production

2. **CodeQL SAST**
   - Python vulnerability scanning
   - CWE detection (injection, XSS, hardcoded secrets)
   - Auto-fix suggestions

3. **Action Version Pinning**
   - SHA-based action references (not @v4)
   - Prevents supply chain attacks

4. **Dockerfile Hardening**
   - Read-only root filesystem
   - Drop all capabilities
   - No setuid/setgid binaries
   - Resource limits (memory, CPU)

5. **GuardDuty**
   - Threat detection (unusual API activity)
   - Malware scanning
   - Crypto mining detection

6. **CloudTrail**
   - Audit logging (all API calls)
   - S3 object-level logging
   - Log file integrity validation

### Phase 4: Advanced Observability (Future)

- **Distributed Tracing:** OpenTelemetry + Jaeger
- **Log Aggregation:** CloudWatch Insights queries
- **Alerting:** SNS + PagerDuty integration
- **SLO Tracking:** 99.9% availability, <200ms p95 latency
- **Cost Monitoring:** AWS Cost Explorer tags

### Phase 5: Multi-Region Deployment (Future)

- **Active-Passive DR:** us-west-2 standby region
- **S3 Replication:** Cross-region model sync
- **Route53:** Failover routing policy
- **RTO/RPO:** <1 hour recovery time, <5 min data loss

## Quick Start

### Prerequisites

- AWS account with admin access
- GitHub repository with OIDC configured
- Docker + Docker Compose
- Terraform 1.5+
- uv 0.9.7

### Local Development

```bash
# Install dependencies
uv sync

# Run tests
uv run pytest

# Lint code
uv run ruff check .
uv run mypy src/

# Start monitoring stack
docker-compose up -d
```

### Infrastructure Deployment

```bash
cd infra
terraform init
terraform plan
terraform apply

# Export secrets to GitHub
gh secret set AWS_ROLE_ARN --body "$(terraform output -raw github_actions_role_arn)"
gh secret set ECR_API_REPOSITORY_URL --body "$(terraform output -raw ecr_api_url)"
gh secret set ECR_TRAINING_REPOSITORY_URL --body "$(terraform output -raw ecr_training_url)"
gh secret set MODELS_BUCKET_NAME --body "$(terraform output -raw models_bucket_name)"
```

### Manual Image Build

```bash
# Build API image
docker build -f container_imgs/Dockerfile.api -t mlops-api:local .

# Build training image
docker build -f container_imgs/Dockerfile.train -t mlops-training:local .

# Scan for vulnerabilities
trivy image mlops-api:local
```

## Contributing

### Pre-Commit Checks

- Code coverage >= 75%
- No secrets detected (Gitleaks)
- Linting passes (ruff)
- Type checking passes (mypy)
- Docker build succeeds

### Branching Strategy

- `main`: Production deployments
- `develop`: Integration testing
- `feature/*`: Feature branches (PR to develop)

### Security Reporting

Report vulnerabilities to: blue-samarth (repository owner)

## References

- [Workflows Documentation](.github/workflows/README.md)
- [Terraform AWS Provider](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- [Trivy Vulnerability Database](https://aquasecurity.github.io/trivy/)
- [Cosign Keyless Signing](https://docs.sigstore.dev/cosign/keyless/)
- [GitHub OIDC](https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/about-security-hardening-with-openid-connect)
