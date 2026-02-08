# MLOps Infrastructure Documentation

## Table of Contents

1. [Infrastructure Overview](#infrastructure-overview)
2. [Architecture](#architecture)
3. [GitHub Integration](#github-integration)
4. [AWS Resources](#aws-resources)
5. [Kubernetes Workloads](#kubernetes-workloads)
6. [Security Architecture](#security-architecture)
7. [Deployment Pipeline](#deployment-pipeline)
8. [Operations](#operations)
9. [Cost Considerations](#cost-considerations)
10. [Troubleshooting](#troubleshooting)

---

## Infrastructure Overview

### Purpose

This infrastructure provides a production-grade MLOps platform for training machine learning models and serving predictions via API. The system is designed for high availability, security, and automated model lifecycle management.

### Technology Stack

**Infrastructure as Code:** Terraform 1.x  
**Container Orchestration:** Amazon EKS 1.33  
**Container Registry:** Amazon ECR with immutable tags  
**Object Storage:** Amazon S3 with encryption and versioning  
**CI/CD:** GitHub Actions with OIDC authentication  
**Image Signing:** Cosign with keyless signing  
**Policy Enforcement:** Kyverno admission controller  
**Language Runtime:** Python 3.13

### Key Components

- **API Service:** FastAPI-based prediction endpoint with horizontal autoscaling
- **Training Pipeline:** Scheduled CronJob for model training with auto-promotion
- **Model Storage:** S3-based versioned storage with serving pointer pattern
- **Security:** Image signing, admission policies, KMS encryption, IAM IRSA
- **Monitoring:** CloudWatch Logs, VPC Flow Logs, S3 access logs

---

## Architecture

### Network Architecture

**VPC Configuration:**
- CIDR Block: 10.0.0.0/16 (65,536 IP addresses)
- Availability Zones: 3 (us-east-1a, us-east-1b, us-east-1c)
- DNS Hostnames: Enabled for service discovery
- DNS Support: Enabled for internal resolution

**Subnet Design:**

Public Subnets (3):
- 10.0.0.0/20 (4,096 IPs) - us-east-1a
- 10.0.16.0/20 (4,096 IPs) - us-east-1b
- 10.0.32.0/20 (4,096 IPs) - us-east-1c
- Purpose: Load balancers, NAT gateways, internet-facing resources
- Internet access: Via Internet Gateway

Private Subnets (3):
- 10.0.48.0/20 (4,096 IPs) - us-east-1a
- 10.0.64.0/20 (4,096 IPs) - us-east-1b
- 10.0.80.0/20 (4,096 IPs) - us-east-1c
- Purpose: EKS worker nodes, application workloads
- Internet access: Via NAT Gateways (one per AZ for high availability)

**VPC Endpoints:**
- S3 Gateway Endpoint: Private access to S3 without internet routing
- ECR API Interface Endpoint: Private ECR API calls
- ECR DKR Interface Endpoint: Private container image pulls
- Purpose: Reduce data transfer costs and enhance security

**Flow Logs:**
- Destination: CloudWatch Logs (/aws/vpc/sam-mlops-production)
- Traffic Type: ALL (accepted and rejected traffic)
- Purpose: Network forensics, compliance, troubleshooting
- Retention: Default CloudWatch retention policy

### EKS Cluster Architecture

**Control Plane:**
- Version: 1.33
- Endpoint Access: Public (production should restrict to specific CIDRs)
- Logging: API, audit, authenticator, controller manager, scheduler
- Encryption: KMS-encrypted secrets and etcd data

**OIDC Provider:**
- Purpose: IAM Roles for Service Accounts (IRSA)
- Issuer: oidc.eks.us-east-1.amazonaws.com/id/CF1DA800D1CCEA8ECE6B9E6C95DF9EF2
- Thumbprint: Automatically verified via TLS certificate
- Usage: Pod-level IAM permissions without node-level credentials

**Node Groups:**

API Node Group:
- Instance Type: t3.medium (2 vCPU, 4 GiB RAM)
- Capacity: 2-5 nodes (autoscaling)
- AMI: Amazon EKS-optimized Linux
- Labels: workload=api, tier=web
- Taint: None (general purpose)
- Disk: 20 GiB gp3 (encrypted with EKS KMS key)

Training Node Group:
- Instance Type: t3.large (2 vCPU, 8 GiB RAM)
- Capacity: 1-3 nodes (autoscaling)
- AMI: Amazon EKS-optimized Linux
- Labels: workload=training, tier=batch
- Taint: training=true:NoSchedule (dedicated for training workloads)
- Disk: 50 GiB gp3 (encrypted with EKS KMS key)

**EKS Addons:**

vpc-cni (v1.21.1):
- Purpose: Pod networking with AWS VPC integration
- Configuration: Prefix delegation enabled, warm prefix target=1
- IRSA: Dedicated service account role for VPC operations

coredns (v1.13.2):
- Purpose: Cluster DNS resolution
- Replicas: Based on cluster size (typically 2)
- Dependencies: Requires at least one node group active

kube-proxy (v1.33.7):
- Purpose: Network proxy for Service resources
- Mode: iptables (default)

aws-ebs-csi-driver (v1.55.0):
- Purpose: Dynamic EBS volume provisioning for persistent storage
- IRSA: Dedicated role with KMS permissions for volume encryption
- Storage Class: gp3 with encryption enabled

### Container Registry Architecture

**ECR Repositories:**

API Repository (sam-mlops-production-api):
- Image Scanning: Enabled on push
- Encryption: KMS-encrypted at rest
- Tag Immutability: Enabled (prevents tag overwrites)
- Lifecycle Policy: Keep last 10 images, expire untagged after 7 days

Training Repository (sam-mlops-production-training):
- Image Scanning: Enabled on push
- Encryption: KMS-encrypted at rest
- Tag Immutability: Enabled
- Lifecycle Policy: Keep last 10 images, expire untagged after 7 days

**Image Tagging Strategy:**
- Format: sha-{git-commit-hash} (e.g., sha-8ff7556)
- Reasoning: Immutable tags prevent latest/master tag conflicts with signature files
- Signature Storage: ECR stores Cosign signatures as separate artifacts with .sig suffix
- Terraform Lookup: External data source filters for sha- prefixed tags to avoid pulling signatures

### Model Storage Architecture

**S3 Bucket (sam-mlops-production-models-{account-id}):**

Configuration:
- Versioning: Enabled for model lineage and rollback capability
- Encryption: AES256 server-side encryption with S3-managed keys
- Access Logging: Enabled to separate logs bucket
- Public Access: Blocked at all levels
- Lifecycle Policy: Transition to Glacier after 90 days, expire after 365 days

Directory Structure:
- models/ - ONNX model files (versioned by model_version)
- metadata/ - Model metadata JSON (schema, metrics, hyperparameters)
- baselines/ - Statistical baselines for drift detection
- serving/ - Serving pointer files (production.json, staging.json)
- serving/history/ - Historical serving pointer snapshots

**Serving Pointer Pattern:**

Purpose: Single source of truth for which model version to serve

serving/production.json structure:
- model_version: Unique version identifier
- model_path: S3 URI to ONNX model
- metadata_path: S3 URI to metadata JSON
- baseline_path: S3 URI to baseline statistics
- schema_hash: Schema fingerprint for validation
- promoted_at: Timestamp of promotion
- promoted_by: Entity that promoted (training-pipeline, manual, etc.)
- promotion_reason: Justification for promotion
- previous_version: Version being replaced
- rollback_to: Quick rollback target
- environment: production, staging, etc.
- approved: Boolean approval flag

Benefits:
- Atomic model updates without pod restarts
- Hot-reload capability via background polling
- Rollback mechanism via pointer update
- Audit trail via history snapshots
- Multi-environment support (prod/staging isolation)

---

## GitHub Integration

### Overview

GitHub Actions workflows are authenticated to AWS using OpenID Connect (OIDC) federation, eliminating the need for long-lived AWS credentials in GitHub secrets. This integration automatically manages repository secrets via Terraform.

### OIDC Authentication Flow

**Setup:**
1. Terraform creates IAM OIDC provider for token.actions.githubusercontent.com
2. IAM role created with trust policy allowing GitHub repository
3. Role ARN stored in GitHub secret for workflow consumption

**Runtime:**
1. GitHub Actions workflow requests OIDC token from GitHub
2. Token contains claims: repository, workflow, commit SHA, actor
3. AWS STS AssumeRoleWithWebIdentity validates token against OIDC provider
4. Temporary credentials issued (valid 1 hour) with scoped permissions
5. Workflow uses credentials for ECR push, S3 access

**Trust Policy Conditions:**
- sub: Exact match on repository (blue-samarth/mlops-tryops)
- aud: Audience must be sts.amazonaws.com
- No branch restrictions (workflow can run from any branch)

### GitHub Secrets Management

**Automated Secret Provisioning:**

Terraform module (github_infra/) creates/updates GitHub repository secrets:
- AWS_ROLE_ARN - IAM role for OIDC assumption
- ECR_API_REPOSITORY_URL - Full ECR URL for API images
- ECR_TRAINING_REPOSITORY_URL - Full ECR URL for training images
- AWS_REGION - us-east-1
- MODELS_BUCKET_NAME - S3 bucket name
- GH_PAT - GitHub Personal Access Token for API operations

**PAT Management:**

First Run:
1. Terraform detects missing .github_pat_store file
2. Executes github_pat_script.sh via null_resource provisioner
3. Script uses gh CLI to create fine-grained PAT with repo scope
4. PAT cached locally in .github_pat_store (gitignored)
5. Terraform reads PAT and provisions secrets

Subsequent Runs:
1. Terraform reads cached PAT from .github_pat_store
2. Updates secrets to match current AWS infrastructure
3. PAT script not re-executed unless cache deleted

**PAT Permissions Required:**
- Administration: Read and write (for secret management)
- Metadata: Read (repository information)
- Expires: 90 days (configurable in script)

### CI/CD Pipeline Architecture

**Workflow: .github/workflows/cd.yml**

Trigger Conditions:
- Push to master branch
- Paths: src/, container_imgs/, pyproject.toml, uv.lock
- Purpose: Build and deploy on application changes only

Build Strategy:
- Multi-stage Docker builds with UV package manager
- BuildKit cache mounts for faster rebuilds
- Separate images for API and training workloads
- Python 3.13 slim-bookworm base images

Image Signing:
- Tool: Cosign v2.4.1
- Method: Keyless signing with Fulcio certificate authority
- OIDC: GitHub Actions identity embedded in signature
- Verification: Kyverno admission controller validates on pod creation
- Transparency Log: Signatures recorded in Rekor for auditability

Tagging Strategy:
- SHA tags only: sha-{short-commit-hash}
- No latest or branch tags (prevents immutable tag conflicts)
- Format enforced via docker/metadata-action configuration
- Terraform external data source filters for sha- prefix

Deployment:
- ECR push: Parallel push of API and training images
- Signature upload: Separate cosign sign step for each image
- Terraform: Manual terraform apply required (no auto-deploy)
- Rationale: Separation of build and deploy for production safety

---

## AWS Resources

### IAM Architecture

**EKS Cluster Role:**
- Managed Policies: AmazonEKSClusterPolicy, AmazonEKSVPCResourceController
- Purpose: Control plane operations, VPC integration
- Trust: eks.amazonaws.com service principal

**EKS Node Role:**
- Managed Policies: AmazonEKSWorkerNodePolicy, AmazonEC2ContainerRegistryReadOnly
- Custom Policy: S3 VPC endpoint access, CloudWatch logs
- Purpose: Node-level permissions for kubelet, container runtime
- Trust: ec2.amazonaws.com service principal

**VPC CNI Role (IRSA):**
- Managed Policy: AmazonEKS_CNI_Policy
- Purpose: ENI management, IP address assignment
- Service Account: kube-system:aws-node
- Trust: EKS OIDC provider with namespace/SA condition

**EBS CSI Driver Role (IRSA):**
- Managed Policy: AmazonEBSCSIDriverPolicy
- Custom Policy: KMS permissions for volume encryption
- Purpose: Dynamic EBS volume provisioning
- Service Account: kube-system:ebs-csi-controller-sa
- Trust: EKS OIDC provider with namespace/SA condition

**API Service Account Role (IRSA):**
- Custom Policy: S3 read (models bucket), KMS decrypt, CloudWatch
- Purpose: Model download and serving
- Service Account: mlops:api-service-account
- Trust: EKS OIDC provider with mlops namespace condition
- Usage: Mounted as pod credentials via token projection

**Training Service Account Role (IRSA):**
- Custom Policy: S3 read/write (models bucket), KMS encrypt/decrypt, CloudWatch
- Purpose: Model upload and metadata management
- Service Account: mlops:training-service-account
- Trust: EKS OIDC provider with mlops namespace condition
- Usage: Mounted as pod credentials via token projection

**GitHub Actions ECR Role:**
- Custom Policy: ECR push/pull, GetAuthorizationToken
- Purpose: CI/CD image builds and pushes
- Trust: GitHub OIDC provider with repository condition
- Principal: token.actions.githubusercontent.com federated identity

**VPC Flow Logs Role:**
- Custom Policy: CloudWatch Logs write permissions
- Purpose: VPC flow log delivery
- Trust: vpc-flow-logs.amazonaws.com service principal

### KMS Encryption

**EKS KMS Key:**
- Purpose: Kubernetes secrets encryption, etcd encryption
- Usage: EKS cluster encryption configuration
- Key Policy: EKS service, cluster role, root account
- Alias: alias/sam-mlops-production-eks

**S3 KMS Key:**
- Purpose: S3 bucket server-side encryption
- Usage: Models bucket, logs bucket
- Key Policy: S3 service, service account roles, root account
- Alias: alias/sam-mlops-production-s3

**ECR KMS Key:**
- Purpose: Container image encryption at rest
- Usage: API and training ECR repositories
- Key Policy: ECR service, GitHub Actions role, root account
- Alias: alias/sam-mlops-production-ecr

**Key Rotation:**
- Status: Enabled (automatic annual rotation)
- Rationale: AWS manages rotation, old keys retained for decryption

### Security Groups

**EKS Cluster Security Group:**
- Purpose: Control plane network access
- Ingress: Worker nodes on port 443 (HTTPS)
- Egress: Worker nodes on all ports
- Managed: Partially managed by EKS

**EKS Nodes Security Group:**
- Purpose: Worker node network isolation
- Ingress: Control plane, inter-node communication, load balancers
- Egress: All traffic (internet, VPC endpoints, control plane)
- Managed: Fully managed by Terraform

**VPC Endpoints Security Group:**
- Purpose: Interface endpoints access control
- Ingress: All traffic from VPC CIDR (10.0.0.0/16)
- Egress: None (inbound only)
- Usage: ECR API/DKR endpoints

### CloudWatch Logging

**VPC Flow Logs:**
- Log Group: /aws/vpc/sam-mlops-production
- Aggregation: 5-minute intervals
- Traffic: ALL (accepted and rejected)
- Format: Default flow log format
- Retention: Default (never expire)

**EKS Control Plane Logs:**
- Log Group: /aws/eks/sam-mlops-production-eks/cluster
- Streams: api, audit, authenticator, controllerManager, scheduler
- Purpose: Control plane diagnostics, security auditing
- Retention: Default (never expire)

**Application Logs:**
- API: stdout/stderr captured by Fluent Bit (future enhancement)
- Training: Job logs via kubectl logs, not persisted
- Recommendation: Deploy Fluent Bit DaemonSet for centralized logging

---

## Kubernetes Workloads

### Namespace Organization

**mlops Namespace:**
- Purpose: Application workloads (API, training)
- Resources: Deployments, CronJobs, Services, ConfigMaps, ServiceAccounts
- Network Policies: None (default allow all)
- Resource Quotas: None (unlimited)

**kyverno Namespace:**
- Purpose: Policy engine and admission controller
- Resources: Deployments, ValidatingWebhookConfigurations, ClusterPolicies
- Critical: Deletion blocked during Terraform destroy (requires manual cleanup)

### API Deployment

**Deployment Specification:**

Replicas:
- Initial: 2 pods (high availability)
- HPA: 2-10 pods based on CPU utilization (70% target)
- Scaling Behavior: Scale up quickly, scale down gradually

Pod Template:
- Image: ECR API repository with SHA digest (immutable reference)
- Image Pull Policy: IfNotPresent (cache images on nodes)
- Service Account: api-service-account (IRSA for S3 access)
- Security Context: runAsNonRoot=true, runAsUser=1000, fsGroup=1000

Resource Requirements:
- Requests: 200m CPU, 512Mi memory
- Limits: 1000m CPU, 1Gi memory
- Rationale: Conservative requests for bin-packing, limits prevent noisy neighbor

Environment Variables (ConfigMap):
- AWS_REGION: us-east-1
- S3_BUCKET: Model storage bucket name
- LOG_LEVEL: INFO
- ENVIRONMENT: production
- MODEL_RELOAD_INTERVAL: 300 seconds

Liveness Probe:
- Path: /health
- Initial Delay: 30 seconds
- Period: 10 seconds
- Timeout: 5 seconds
- Failure Threshold: 3
- Purpose: Restart unhealthy pods

Readiness Probe:
- Path: /ready
- Initial Delay: 10 seconds
- Period: 5 seconds
- Timeout: 3 seconds
- Failure Threshold: 3
- Purpose: Remove unready pods from load balancer

**Service Configuration:**

Type: LoadBalancer (AWS Classic Load Balancer)
- Port: 80 (HTTP)
- Target Port: 8000 (container port)
- Health Check: /health endpoint
- Cross-Zone Load Balancing: Enabled by default
- Connection Draining: 300 seconds
- Idle Timeout: 60 seconds

DNS:
- Cluster DNS: api-service.mlops.svc.cluster.local
- External DNS: Load balancer hostname (ad4aa646b35c94d6ba6ff8f9110705c0-1191961482.us-east-1.elb.amazonaws.com)

### Training CronJob

**CronJob Specification:**

Schedule:
- Cron: 0 2 * * * (2:00 AM UTC daily)
- Timezone: UTC (no timezone support in Kubernetes CronJob)
- Concurrency Policy: Forbid (prevent overlapping jobs)
- Starting Deadline: None (job runs whenever scheduler permits)

Job History:
- Successful: Keep last 3
- Failed: Keep last 1
- Purpose: Debugging and audit trail

Job Template:
- Backoff Limit: 2 retries
- Restart Policy: Never (create new pod on failure)
- Active Deadline: None (no timeout)

Pod Template:
- Image: ECR training repository with SHA digest
- Service Account: training-service-account (IRSA for S3 write)
- Security Context: runAsNonRoot=true, runAsUser=1000, fsGroup=1000
- Node Selector: workload=training, tier=batch
- Tolerations: training=true:NoSchedule

Resource Requirements:
- Requests: 500m CPU, 1Gi memory
- Limits: 1500m CPU, 2Gi memory
- Rationale: Training requires more resources than API serving

Command:
- Shell: /bin/sh -c
- Script: python scripts/generate_dummy_data.py --output data/training_data.csv --samples 5000 && python -m src.train.train --data data/training_data.csv --target approved
- Data Generation: 5000 synthetic samples with age, income, credit_score, employment_years, debt_ratio
- Training: Logistic regression with 80/20 train/test split

Auto-Promotion:
- Enabled by default (--auto-promote flag)
- Creates serving/production.json pointer after successful training
- Reason: Automated training deployment - Accuracy: {accuracy}
- Promoter: training-pipeline

### Kyverno Policy Engine

**Admission Controller:**

Deployment:
- Replicas: 2 (high availability)
- Resource Requests: 200m CPU, 256Mi memory
- Webhook: ValidatingWebhookConfiguration with failurePolicy=Fail
- Scope: Cluster-wide (all namespaces except kube-system, kyverno)

**ClusterPolicy: verify-image-signatures**

Purpose: Enforce signed container images
- Rule: Verify Cosign signatures for all images from ECR
- OIDC Issuer: https://token.actions.githubusercontent.com
- Subject: repo:blue-samarth/mlops-tryops:ref:refs/heads/master
- Rekor URL: https://rekor.sigstore.dev
- Action: Deny pods with unsigned images

**ClusterPolicy: require-non-root**

Purpose: Prevent root containers
- Rule: Enforce runAsNonRoot=true in pod securityContext
- Validation: securityContext.runAsNonRoot must be true
- Action: Deny pods running as root (UID 0)

**ClusterPolicy: disallow-privileged-containers**

Purpose: Block privileged escalation
- Rule: Enforce privileged=false and allowPrivilegeEscalation=false
- Validation: Container securityContext restrictions
- Action: Deny privileged containers

**ClusterPolicy: require-resource-limits**

Purpose: Enforce resource governance
- Rule: All containers must specify CPU and memory requests/limits
- Validation: resources.requests and resources.limits required
- Action: Deny pods without resource specifications

---

## Security Architecture

### Defense in Depth

**Layer 1: Network Isolation**
- Private subnets for all workloads
- Security groups with least privilege
- VPC endpoints for AWS service access
- NAT gateways for controlled egress
- Flow logs for network forensics

**Layer 2: IAM and IRSA**
- Pod-level IAM roles via OIDC
- No node-level credentials for application workloads
- Temporary credentials with 1-hour expiration
- Service account namespace isolation
- Condition-based trust policies

**Layer 3: Encryption**
- KMS encryption for EKS secrets and etcd
- S3 server-side encryption for model artifacts
- ECR encryption for container images
- EBS volume encryption for persistent storage
- TLS for data in transit (future enhancement)

**Layer 4: Admission Control**
- Image signature verification
- Non-root container enforcement
- Privileged container blocking
- Resource limit requirements
- Immutable infrastructure (signed images)

**Layer 5: Runtime Security**
- Pod security context (non-root, fsGroup)
- Read-only root filesystem (future enhancement)
- Seccomp profiles (future enhancement)
- AppArmor/SELinux (future enhancement)

### Image Supply Chain Security

**Build Time:**
1. GitHub Actions workflow builds container image
2. Multi-stage build with minimal attack surface
3. Non-root user created in Dockerfile
4. UV package manager for reproducible dependencies
5. Git commit SHA embedded in image metadata

**Sign Time:**
1. Cosign generates ephemeral key pair
2. Fulcio issues short-lived code signing certificate
3. Certificate embedded in signature
4. Signature uploaded to Rekor transparency log
5. Signature stored in ECR alongside image

**Deploy Time:**
1. Terraform external data source retrieves SHA-tagged image
2. Helm chart references image by SHA digest (immutable)
3. Kubernetes scheduler pulls image to worker node
4. Kyverno admission controller intercepts pod creation
5. Cosign verification checks signature against OIDC claims
6. Pod admitted if signature valid, rejected otherwise

**Runtime:**
1. Container runtime enforces security context
2. Pod runs as non-root user (UID 1000)
3. Service account provides scoped IAM credentials
4. Resource limits prevent resource exhaustion
5. Network policies control pod-to-pod communication (future)

### Secrets Management

**Kubernetes Secrets:**
- Encryption: KMS-encrypted at rest in etcd
- Access: RBAC-controlled per namespace
- Rotation: Manual (future: External Secrets Operator)
- Storage: Never committed to Git

**Service Account Tokens:**
- Type: Projected volume with OIDC token
- Expiration: 1 hour (automatically refreshed)
- Audience: sts.amazonaws.com
- Usage: AWS STS AssumeRoleWithWebIdentity

**GitHub Secrets:**
- Storage: GitHub encrypted secrets vault
- Access: Per-repository, per-environment
- Rotation: Manual via Terraform re-apply
- Audit: GitHub audit log

**AWS Credentials:**
- Type: Temporary STS credentials
- Lifetime: 1 hour
- Scope: IAM role policy boundaries
- Rotation: Automatic on expiration
- Storage: Never stored, only in-memory

---

## Deployment Pipeline

### Build Process

**Trigger:**
- Event: Push to master branch
- Filter: Changes to src/, container_imgs/, pyproject.toml, uv.lock
- Concurrency: Cancel in-progress runs on new push

**Dependency Management:**
- Tool: UV (fast Rust-based Python package manager)
- Lock File: uv.lock (pinned versions, hashes)
- Cache: BuildKit cache mount for /root/.cache/uv
- Sync: uv sync --frozen (no lock file updates during build)

**Multi-Stage Build:**

Stage 1 - Builder:
- Base: ghcr.io/astral-sh/uv:python3.13-bookworm-slim
- Purpose: Install dependencies and build environment
- System Packages: build-essential, gfortran, libopenblas-dev (for NumPy/SciPy)
- Python Dependencies: All project dependencies including dev tools
- Output: Virtual environment in /build/.venv

Stage 2 - Runtime (API):
- Base: python:3.13-slim-bookworm
- Purpose: Minimal runtime image
- Copy: Virtual environment from builder
- Copy: Application code (src/api/, src/utils/)
- Exclude: Training code to reduce image size
- User: mlops (UID 1000, GID 1000)
- Entrypoint: uvicorn with hot-reload disabled

Stage 2 - Runtime (Training):
- Base: python:3.13-slim-bookworm
- Purpose: Batch training execution
- Copy: Virtual environment from builder
- Copy: Application code (src/train/, src/utils/, scripts/)
- Exclude: API code to reduce image size
- User: mlops (UID 1000, GID 1000)
- Entrypoint: python -m src.train.train with help text

**Build Optimization:**
- BuildKit: Enabled for parallel layer builds
- Cache Mounts: UV cache, pip cache, apt cache
- Layer Ordering: Dependencies before application code
- Multi-Platform: linux/amd64 only (EKS nodes)

### Image Publishing

**ECR Authentication:**
- Method: OIDC with AWS STS
- Action: aws-actions/amazon-ecr-login@v2
- Credentials: Temporary (1 hour)
- Registries: Both API and training ECR repositories

**Tagging:**
- Format: sha-{short-git-hash}
- Example: sha-8ff7556
- Immutability: Enforced by ECR repository configuration
- Metadata: Build date, git commit, version in image labels

**Parallel Push:**
- API Image: docker/build-push-action for API Dockerfile
- Training Image: docker/build-push-action for training Dockerfile
- Platforms: linux/amd64
- Cache: Registry cache with mode=max

**Signing:**
- Tool: sigstore/cosign-installer@v3.4.0
- Version: Cosign v2.4.1
- Method: cosign sign --yes (keyless, OIDC-based)
- Identity: GitHub Actions OIDC token
- Certificate: Fulcio-issued short-lived cert
- Transparency: Rekor immutable log entry

### Deployment Process

**Infrastructure Changes:**

Prerequisites:
1. AWS credentials configured (OIDC or static)
2. Terraform initialized (terraform init)
3. GitHub PAT available (or auto-generated)

Apply:
1. terraform plan (review changes)
2. terraform apply (manual approval required)
3. Kubernetes resources updated via Helm provider
4. Pods rolled out with new image references

**Application Updates:**

Automatic (on image push):
1. CI builds and pushes new images to ECR
2. Terraform external data source remains unchanged (manual update required)
3. No automatic deployment (separation of build and deploy)

Manual (on terraform apply):
1. External data source queries ECR for latest SHA-tagged image
2. Helm chart updated with new image digest
3. Kubernetes rolling update deployed
4. Old pods terminated after new pods ready
5. Load balancer health checks validate new pods

**Model Updates:**

Training CronJob:
1. Runs daily at 2:00 AM UTC
2. Generates synthetic data (5000 samples)
3. Trains logistic regression model
4. Uploads model, metadata, baseline to S3
5. Promotes to production serving pointer
6. API pods detect new pointer on next reload cycle (5 minutes)

Manual Training:
1. kubectl create job --from=cronjob/training training-manual-{timestamp} -n mlops
2. Job runs immediately with same logic as CronJob
3. Auto-promotion to production on success
4. API hot-reloads model without pod restart

---

## Operations

### Deployment Commands

**Initial Infrastructure Setup:**

```bash
cd infra/
terraform init
terraform plan -out=initial.tfplan
terraform apply initial.tfplan
aws eks update-kubeconfig --region us-east-1 --name sam-mlops-production-eks
kubectl get nodes
```

**Infrastructure Updates:**

```bash
cd infra/
terraform plan
terraform apply --auto-approve
```

**Complete Teardown:**

```bash
# Remove Kyverno manually (Terraform destroy hangs)
kubectl delete namespace kyverno --force --grace-period=0
terraform state rm helm_release.kyverno helm_release.kyverno_policies

# Empty S3 buckets
aws s3 rm s3://sam-mlops-production-models-{account-id} --recursive
aws s3api delete-objects --bucket sam-mlops-production-models-{account-id} \
  --delete "$(aws s3api list-object-versions --bucket sam-mlops-production-models-{account-id} \
  --query '{Objects: Versions[].{Key:Key,VersionId:VersionId}}' --max-items 1000)"
aws s3api delete-objects --bucket sam-mlops-production-models-{account-id} \
  --delete "$(aws s3api list-object-versions --bucket sam-mlops-production-models-{account-id} \
  --query '{Objects: DeleteMarkers[].{Key:Key,VersionId:VersionId}}' --max-items 1000)"

# Destroy infrastructure
terraform destroy --auto-approve
```

### Kubernetes Operations

**View API Pods:**

```bash
kubectl get pods -n mlops -l app.kubernetes.io/name=mlops-api
kubectl logs -n mlops -l app.kubernetes.io/name=mlops-api --tail=100 -f
```

**Restart API (force reload):**

```bash
kubectl rollout restart deployment -n mlops -l app.kubernetes.io/name=mlops-api
kubectl rollout status deployment -n mlops -l app.kubernetes.io/name=mlops-api
```

**Manual Training Execution:**

```bash
kubectl create job --from=cronjob/training training-manual-$(date +%Y%m%d-%H%M%S) -n mlops
kubectl get jobs -n mlops
kubectl logs -n mlops -l job-name=training-manual-{timestamp} --follow
```

**View Training Job History:**

```bash
kubectl get cronjobs -n mlops
kubectl get jobs -n mlops --sort-by=.metadata.creationTimestamp
```

**Debug Training Pod:**

```bash
kubectl describe pod -n mlops {training-pod-name}
kubectl logs -n mlops {training-pod-name}
kubectl get events -n mlops --field-selector involvedObject.name={training-pod-name}
```

### Model Management

**List Models:**

```bash
aws s3 ls s3://sam-mlops-production-models-{account-id}/models/
aws s3 ls s3://sam-mlops-production-models-{account-id}/metadata/
```

**View Current Serving Pointer:**

```bash
aws s3 cp s3://sam-mlops-production-models-{account-id}/serving/production.json - | jq .
```

**Manual Model Promotion (Emergency):**

```bash
# Create promotion script
cat > promote_model.py << 'EOF'
import sys
sys.path.insert(0, '/path/to/try_ops')
from src.utils.serving_pointer import ServingPointerManager

pointer = ServingPointerManager(
    s3_bucket="sam-mlops-production-models-{account-id}",
    environment="production",
    region="us-east-1"
)

result = pointer.promote_model(
    model_version="v20260208_160016_2b35ca",
    promoted_by="ops-team",
    promotion_reason="Emergency rollback due to production issue"
)
print(f"Promoted {result['model_version']}")
EOF

python3 promote_model.py
```

**Model Rollback:**

```bash
# View history
aws s3 ls s3://sam-mlops-production-models-{account-id}/serving/history/

# Get previous pointer
aws s3 cp s3://sam-mlops-production-models-{account-id}/serving/history/production_{timestamp}.json - | jq .

# Promote previous version (use promotion script above with previous version)
```

### API Testing

**Health Check:**

```bash
LOAD_BALANCER=$(kubectl get svc -n mlops api-service -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
curl http://$LOAD_BALANCER/health | jq .
```

**Single Prediction:**

```bash
curl -X POST http://$LOAD_BALANCER/v1/predict \
  -H "Content-Type: application/json" \
  -d '{
    "features": {
      "age": 35,
      "income": 75000,
      "credit_score": 720,
      "employment_years": 8,
      "debt_ratio": 0.25
    }
  }' | jq .
```

**Batch Prediction:**

```bash
curl -X POST http://$LOAD_BALANCER/v1/predict/batch \
  -H "Content-Type: application/json" \
  -d '{
    "instances": [
      {"age": 45, "income": 95000, "credit_score": 780, "employment_years": 15, "debt_ratio": 0.20},
      {"age": 30, "income": 45000, "credit_score": 620, "employment_years": 5, "debt_ratio": 0.45}
    ]
  }' | jq .
```

**Model Info:**

```bash
curl http://$LOAD_BALANCER/v1/model/info | jq .
```

### Monitoring and Debugging

**EKS Control Plane Logs:**

```bash
aws logs tail /aws/eks/sam-mlops-production-eks/cluster --follow
aws logs filter-pattern /aws/eks/sam-mlops-production-eks/cluster --filter-pattern "ERROR"
```

**VPC Flow Logs:**

```bash
aws logs tail /aws/vpc/sam-mlops-production --follow
aws logs filter-pattern /aws/vpc/sam-mlops-production --filter-pattern "REJECT"
```

**Kyverno Policy Violations:**

```bash
kubectl get policyreport -A
kubectl describe policyreport -n mlops
kubectl logs -n kyverno -l app.kubernetes.io/component=admission-controller --tail=100
```

**Node Resource Usage:**

```bash
kubectl top nodes
kubectl top pods -n mlops
kubectl describe node {node-name}
```

**Service Account Token Validation:**

```bash
kubectl exec -n mlops {api-pod-name} -- env | grep AWS
kubectl exec -n mlops {api-pod-name} -- cat /var/run/secrets/eks.amazonaws.com/serviceaccount/token
```

---

## Cost Considerations

### Monthly Cost Estimates (us-east-1)

**Compute (EKS Nodes):**
- API Node Group: 2 x t3.medium = $0.0416/hr x 2 x 730 hrs = $60.74/month
- Training Node Group: 1 x t3.large (on-demand) = $0.0832/hr x 730 hrs = $60.74/month
- Total Compute: $121.48/month

**EKS Control Plane:**
- Cluster: $0.10/hr x 730 hrs = $73.00/month

**Load Balancer:**
- Classic Load Balancer: $0.025/hr x 730 hrs = $18.25/month
- Data Transfer: ~$0.01/GB (varies by usage)

**NAT Gateways:**
- 3 NAT Gateways: $0.045/hr x 3 x 730 hrs = $98.55/month
- Data Processing: $0.045/GB (varies by usage)

**VPC Endpoints:**
- 3 Interface Endpoints: $0.01/hr x 3 x 730 hrs = $21.90/month
- Data Processing: $0.01/GB (minimal)

**S3 Storage:**
- Standard: $0.023/GB (depends on model size)
- Example: 10GB models = $0.23/month
- Requests: Minimal (GET/PUT for models)

**ECR Storage:**
- Private Repo: $0.10/GB-month
- Example: 5GB images = $0.50/month

**KMS:**
- 3 Customer Managed Keys: $1.00/month each = $3.00/month
- API Requests: $0.03/10,000 (minimal)

**CloudWatch Logs:**
- Ingestion: $0.50/GB
- Storage: $0.03/GB-month
- Example: 10GB/month = $5.30/month

**Data Transfer:**
- Out to Internet: $0.09/GB (varies by usage)
- Between AZs: $0.01/GB (internal traffic)

**Total Estimated Monthly Cost: $342-$400/month**

### Cost Optimization Strategies

**Compute Savings:**
1. Use Spot Instances for training node group (70% cost reduction)
2. Implement cluster autoscaler to scale nodes to zero during idle
3. Use Fargate for API workloads (pay per pod, eliminate node overhead)
4. Reserved Instances or Savings Plans for predictable workloads (40% discount)

**Storage Optimization:**
1. Implement S3 lifecycle policies (models to Glacier after 90 days)
2. Enable ECR image scanning scheduled (reduce scan frequency)
3. Automated cleanup of old model versions (keep last 10)
4. Compress training data before S3 upload

**Network Cost Reduction:**
1. Consolidate NAT Gateways to 1 (acceptable for non-production)
2. Use VPC endpoints for all AWS services (avoid NAT gateway data charges)
3. Enable S3 Transfer Acceleration for large uploads (faster, potentially cheaper)
4. Implement VPC peering instead of NAT for cross-VPC communication

**Monitoring Efficiency:**
1. CloudWatch Logs retention policy (7-30 days instead of indefinite)
2. Log filtering at source (reduce ingestion volume)
3. Aggregate logs to S3 for long-term storage ($0.023/GB vs $0.50/GB)
4. Use CloudWatch Logs Insights queries instead of exporting

**Resource Right-Sizing:**
1. Monitor actual resource usage (kubectl top, CloudWatch metrics)
2. Adjust pod resource requests to actual consumption
3. Use Vertical Pod Autoscaler for automatic right-sizing
4. Downsize node instance types based on actual workload

---

## Troubleshooting

### Common Issues

**Issue: Pods stuck in Pending state**

Symptoms:
- kubectl get pods shows Pending status
- kubectl describe pod shows "0/3 nodes available" or similar

Diagnosis:
```bash
kubectl describe pod -n mlops {pod-name}
kubectl get events -n mlops --field-selector involvedObject.name={pod-name}
```

Possible Causes:
1. Insufficient node capacity (CPU/memory)
2. Node selector mismatch (pod requires specific node labels)
3. Taints not tolerated (pod needs toleration for node taint)
4. Image pull errors (ECR authentication, repository not found)
5. Kyverno admission denial (unsigned image, policy violation)

Resolution:
```bash
# Check node capacity
kubectl describe nodes | grep -A 5 "Allocated resources"

# Check node labels
kubectl get nodes --show-labels

# Check taints
kubectl describe node {node-name} | grep Taints

# View Kyverno policy violations
kubectl get policyreport -n mlops
kubectl describe clusterpolicy

# Manually scale node group
aws eks update-nodegroup-config --cluster-name sam-mlops-production-eks \
  --nodegroup-name sam-mlops-production-api-nodes --scaling-config desiredSize=3
```

**Issue: Training job fails with S3 access denied**

Symptoms:
- Training pod logs show "AccessDenied" or "Forbidden" errors
- Model upload to S3 fails

Diagnosis:
```bash
kubectl logs -n mlops {training-pod-name} | grep -i "error\|denied\|forbidden"
kubectl describe pod -n mlops {training-pod-name} | grep "service-account"
```

Possible Causes:
1. Service account role ARN incorrect
2. Trust policy namespace mismatch (mlops vs mlops-training)
3. IAM policy missing S3 permissions
4. KMS key policy missing service account role
5. S3 bucket policy blocking access

Resolution:
```bash
# Verify service account annotation
kubectl get sa -n mlops training-service-account -o yaml | grep "eks.amazonaws.com/role-arn"

# Check IAM role trust policy
aws iam get-role --role-name sam-mlops-production-training-service-account-role \
  --query 'Role.AssumeRolePolicyDocument' | jq .

# Test S3 access from pod
kubectl exec -n mlops {training-pod-name} -- aws s3 ls s3://sam-mlops-production-models-{account-id}/

# Update trust policy (if namespace mismatch)
# Edit infra/aws_eks_iam.tf and change mlops-training to mlops in trust policy
terraform apply --auto-approve
```

**Issue: API pods cannot load model**

Symptoms:
- API health check shows model_loaded: false
- API logs show "No serving pointer found"

Diagnosis:
```bash
kubectl logs -n mlops -l app.kubernetes.io/name=mlops-api | grep -i "serving\|model\|pointer"
aws s3 ls s3://sam-mlops-production-models-{account-id}/serving/
```

Possible Causes:
1. No model trained yet (serving/production.json missing)
2. S3 bucket permissions incorrect
3. Service account role misconfigured
4. Model reload interval too long (API hasn't polled yet)

Resolution:
```bash
# Run manual training to create serving pointer
kubectl create job --from=cronjob/training training-manual-$(date +%Y%m%d-%H%M%S) -n mlops
kubectl logs -n mlops -l job-name=training-manual-{timestamp} --follow

# Verify serving pointer created
aws s3 cp s3://sam-mlops-production-models-{account-id}/serving/production.json - | jq .

# Force API reload
kubectl rollout restart deployment -n mlops -l app.kubernetes.io/name=mlops-api
kubectl logs -n mlops -l app.kubernetes.io/name=mlops-api --tail=100 -f | grep "model"
```

**Issue: Kyverno blocking pod creation**

Symptoms:
- Pod creation fails immediately
- Events show "admission webhook denied"

Diagnosis:
```bash
kubectl describe pod -n mlops {pod-name} | grep -A 10 Events
kubectl logs -n kyverno -l app.kubernetes.io/component=admission-controller --tail=50
kubectl get clusterpolicy
```

Possible Causes:
1. Image not signed (verify-image-signatures policy)
2. Container running as root (require-non-root policy)
3. Missing resource limits (require-resource-limits policy)
4. Privileged container (disallow-privileged-containers policy)

Resolution:
```bash
# Temporarily disable policy (NOT recommended for production)
kubectl patch clusterpolicy verify-image-signatures -p '{"spec":{"validationFailureAction":"Audit"}}'

# Verify image signature
cosign verify --certificate-identity-regexp=".*" \
  --certificate-oidc-issuer=https://token.actions.githubusercontent.com \
  {ecr-repository-url}@{image-digest}

# Check pod security context
kubectl get pod -n mlops {pod-name} -o yaml | grep -A 10 securityContext

# Re-enable policy
kubectl patch clusterpolicy verify-image-signatures -p '{"spec":{"validationFailureAction":"Enforce"}}'
```

**Issue: Terraform destroy hangs on Kyverno**

Symptoms:
- terraform destroy stuck on helm_release.kyverno
- Timeout after 10 minutes

Diagnosis:
```bash
helm list -n kyverno
kubectl get validatingwebhookconfiguration
kubectl get namespace kyverno -o yaml | grep finalizers
```

Possible Causes:
1. Webhook finalizers blocking namespace deletion
2. Custom resources with finalizers
3. Helm release stuck in "uninstalling" state

Resolution:
```bash
# Force delete validating webhooks
kubectl delete validatingwebhookconfigurations -l app.kubernetes.io/part-of=kyverno --force --grace-period=0

# Remove from Terraform state
cd infra/
terraform state rm helm_release.kyverno helm_release.kyverno_policies

# Force delete namespace
kubectl delete namespace kyverno --force --grace-period=0

# Continue destroy
terraform destroy --auto-approve
```

**Issue: ECR external data source pulling signature files**

Symptoms:
- Terraform plan shows .sig files as image tags
- Pods fail to pull images (invalid manifest)

Diagnosis:
```bash
aws ecr describe-images --repository-name sam-mlops-production-api \
  --query 'imageDetails[*].imageTags' --output json
```

Possible Causes:
1. ECR immutable tags enabled
2. Cosign signatures stored as separate images with .sig extension
3. External data source not filtering for sha- prefix

Resolution:
```bash
# Verify external data source filters sha- tags
cat infra/helm_api.tf | grep -A 10 "external.api_latest_image"

# Should contain: grep 'sha-' | head -1

# Update tagging strategy in .github/workflows/cd.yml
# Remove latest and master tags, use only sha-{commit} format
```

**Issue: GitHub Actions OIDC authentication fails**

Symptoms:
- Workflow fails at "Configure AWS credentials" step
- Error: "Not authorized to perform sts:AssumeRoleWithWebIdentity"

Diagnosis:
```bash
# Check OIDC provider
aws iam list-open-id-connect-providers

# Check role trust policy
aws iam get-role --role-name sam-mlops-production-github-actions-ecr \
  --query 'Role.AssumeRolePolicyDocument' | jq .
```

Possible Causes:
1. OIDC provider not created
2. Trust policy subject mismatch (wrong repository name)
3. Workflow running from wrong branch
4. GitHub token claims incorrect

Resolution:
```bash
# Verify repository name in terraform.tfvars
cat infra/terraform.tfvars | grep github

# Update trust policy if repository changed
# Edit infra/aws_iam_ga_runners.tf
terraform apply --auto-approve

# Test OIDC manually from workflow
# Add step: env | grep ACTIONS_ to see GitHub-provided claims
```

### Log Analysis

**API Request Tracing:**

```bash
# Get request ID from response headers
curl -i http://{load-balancer}/health | grep X-Request-ID

# Find logs for specific request
kubectl logs -n mlops -l app.kubernetes.io/name=mlops-api | grep "{request-id}"
```

**Training Job Debugging:**

```bash
# View job configuration
kubectl get job -n mlops {job-name} -o yaml

# Check pod spec
kubectl describe job -n mlops {job-name}

# View logs from all containers (if multi-container pod)
kubectl logs -n mlops {pod-name} --all-containers=true

# Export logs for analysis
kubectl logs -n mlops {pod-name} > training-debug.log
```

**Network Traffic Analysis:**

```bash
# View VPC flow logs for pod IP
POD_IP=$(kubectl get pod -n mlops {pod-name} -o jsonpath='{.status.podIP}')
aws logs filter-pattern /aws/vpc/sam-mlops-production --filter-pattern "$POD_IP"

# Check security group rules
aws ec2 describe-security-groups --group-ids {sg-id} --query 'SecurityGroups[*].IpPermissions'

# Test connectivity from pod
kubectl exec -n mlops {pod-name} -- curl -v http://{destination}
kubectl exec -n mlops {pod-name} -- nslookup {hostname}
```

---

## Appendix

### Terraform State Management

Current Configuration:
- Backend: Local filesystem (terraform.tfstate)
- Location: infra/ directory
- Locking: None (single operator assumed)

Production Recommendations:
1. Migrate to S3 backend with DynamoDB state locking
2. Enable versioning on state bucket
3. Encrypt state with KMS
4. Implement workspace isolation (dev, staging, prod)

Example S3 Backend Configuration:
```hcl
terraform {
  backend "s3" {
    bucket         = "terraform-state-{account-id}"
    key            = "mlops/production/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    kms_key_id     = "alias/terraform-state"
    dynamodb_table = "terraform-state-lock"
  }
}
```

### Future Enhancements

**High Priority:**
1. Implement Fluent Bit DaemonSet for centralized logging
2. Deploy Prometheus and Grafana for metrics and dashboards
3. Add Horizontal Pod Autoscaler metrics (custom metrics from model performance)
4. Implement NetworkPolicies for pod-to-pod isolation
5. Enable API Gateway or Ingress Controller for advanced routing

**Medium Priority:**
1. Implement External Secrets Operator for secrets management
2. Add Argo Rollouts for blue-green deployments
3. Deploy Istio service mesh for observability and traffic management
4. Implement pod disruption budgets for high availability
5. Add pod priority classes for scheduling guarantees

**Low Priority:**
1. Implement read-only root filesystem for containers
2. Add seccomp and AppArmor profiles for runtime security
3. Deploy Falco for runtime threat detection
4. Implement OPA Gatekeeper for additional policy enforcement
5. Add chaos engineering with Chaos Mesh

### Reference Documentation

**AWS EKS:**
- EKS User Guide: https://docs.aws.amazon.com/eks/
- EKS Best Practices: https://aws.github.io/aws-eks-best-practices/
- IRSA Documentation: https://docs.aws.amazon.com/eks/latest/userguide/iam-roles-for-service-accounts.html

**Kubernetes:**
- Kubernetes Documentation: https://kubernetes.io/docs/
- Pod Security Standards: https://kubernetes.io/docs/concepts/security/pod-security-standards/
- Resource Management: https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/

**Kyverno:**
- Kyverno Documentation: https://kyverno.io/docs/
- Policy Library: https://kyverno.io/policies/
- Cosign Integration: https://kyverno.io/docs/writing-policies/verify-images/

**Sigstore:**
- Cosign Documentation: https://docs.sigstore.dev/cosign/overview/
- Keyless Signing: https://github.com/sigstore/cosign/blob/main/KEYLESS.md
- Rekor Transparency Log: https://docs.sigstore.dev/rekor/overview/

**Terraform:**
- Terraform AWS Provider: https://registry.terraform.io/providers/hashicorp/aws/latest/docs
- Terraform Helm Provider: https://registry.terraform.io/providers/hashicorp/helm/latest/docs
- Terraform Best Practices: https://www.terraform-best-practices.com/

### Glossary

**IRSA (IAM Roles for Service Accounts):** Kubernetes feature allowing pods to assume IAM roles via OIDC, providing scoped AWS permissions without node-level credentials.

**OIDC (OpenID Connect):** Authentication protocol used for federation between GitHub Actions and AWS, enabling temporary credential issuance based on JWT claims.

**Cosign:** Tool for signing and verifying container images using cryptographic signatures, part of the Sigstore project.

**Kyverno:** Kubernetes-native policy engine that validates, mutates, and generates resources based on declarative policies.

**Serving Pointer:** Design pattern where a JSON file in S3 (serving/production.json) points to the current production model version, enabling atomic updates and rollbacks.

**Immutable Tags:** ECR repository configuration preventing tag overwrites, ensuring that sha-8ff7556 always refers to the same image digest.

**External Data Source:** Terraform data source executing external program (shell script, Python) to dynamically fetch values during plan/apply.

**HPA (Horizontal Pod Autoscaler):** Kubernetes controller that automatically scales pod replicas based on CPU utilization or custom metrics.

**Taint and Toleration:** Kubernetes mechanism for node affinity where taints repel pods unless they have matching tolerations, used to dedicate training nodes.

**KMS CMK (Customer Managed Key):** AWS KMS encryption key owned and managed by the customer, providing granular control over encryption and key policies.

**VPC Endpoint:** Private connection between VPC and AWS services without traversing the internet, reducing costs and enhancing security.

**NAT Gateway:** Managed NAT service providing outbound internet access for resources in private subnets.

**Service Account:** Kubernetes identity for pods, projected as a mounted token with OIDC claims for AWS STS authentication.

---

**Document Version:** 1.0  
**Last Updated:** 2026-02-08  
**Maintained By:** MLOps Team  
**Contact:** [Repository Issues](https://github.com/blue-samarth/mlops-tryops/issues)
