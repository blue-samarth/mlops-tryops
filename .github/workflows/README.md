# CI/CD Workflows Documentation

This directory contains GitHub Actions workflows implementing DevSecOps principles for automated continuous integration and deployment of MLOps services.

## Architecture Overview

The pipeline follows a security-first, shift-left approach with integrated vulnerability scanning, secrets detection, and cryptographic signing. All workflows utilize OIDC for zero-credential AWS authentication and implement least-privilege access patterns.

## Workflows

### ci.yml - Continuous Integration

**Trigger:** Pull requests to `master` or `develop` branches, manual dispatch

**Purpose:** Validates code quality, security posture, and build integrity before merge

#### Jobs

1. **changes** - Path-based change detection using `dorny/paths-filter@v3`
   - Outputs: `python`, `api`, `training` boolean flags
   - Optimizes CI execution by running only affected jobs
   - Patterns: `src/**/*.py`, `tests/**/*.py`, `pyproject.toml`, `uv.lock`, Dockerfiles

2. **secrets-scan** - Static secrets detection
   - Tool: Gitleaks v2
   - Scans: Entire repository history (`fetch-depth: 0`)
   - Detects: 800+ credential types (AWS keys, tokens, private keys, API keys)
   - Enforcement: Fails build on detection
   - Permissions: `contents: read`, `security-events: write`

3. **test** - Automated testing with coverage enforcement
   - Conditional: Runs if `python` files changed
   - Framework: pytest with pytest-cov
   - Coverage gates:
     - `>= 90%`: Pass (excellent)
     - `75-89%`: Warning (acceptable)
     - `< 75%`: Fail (insufficient)
   - Reports: JSON format for programmatic parsing

4. **lint** - Static code analysis
   - Conditional: Runs if `python` files changed, executes even if tests fail
   - Tools:
     - `ruff`: Linting and formatting validation
     - `mypy`: Static type checking
   - Mode: `continue-on-error: true` (non-blocking)

5. **build-api** - Docker image build verification
   - Conditional: Runs if API-related files changed
   - BuildKit features: Layer caching (`type=gha`)
   - Output: Image artifact to `/tmp/api-image.tar`
   - Tags: branch name, PR number, short SHA

6. **build-training** - Training container build verification
   - Conditional: Runs if training-related files changed
   - Configuration: Same as build-api
   - Output: Image artifact to `/tmp/training-image.tar`

### cd.yml - Continuous Deployment

**Trigger:** Push to `main`/`master` branches, manual dispatch

**Purpose:** Security scanning, container signing, and deployment to AWS ECR

#### Environment Variables

Centralized in workflow `env` block for maintainability:

```yaml
AWS_ROLE_ARN: ${{ secrets.AWS_ROLE_ARN }}
AWS_REGION: ${{ vars.AWS_REGION }}
ECR_API_REPOSITORY_URL: ${{ secrets.ECR_API_REPOSITORY_URL }}
ECR_TRAINING_REPOSITORY_URL: ${{ secrets.ECR_TRAINING_REPOSITORY_URL }}
MODELS_BUCKET_NAME: ${{ secrets.MODELS_BUCKET_NAME }}
ENVIRONMENT: ${{ vars.ENVIRONMENT }}
DOCKER_BUILDKIT: ${{ vars.DOCKER_BUILDKIT }}
```

#### Jobs

1. **changes** - Path-based deployment filtering
   - Same mechanism as CI workflow
   - Outputs: `api`, `training` boolean flags

2. **security-scan-api** - Vulnerability assessment
   - Conditional: API changes OR manual trigger
   - Steps:
     1. Build image with BuildKit cache
     2. Trivy container scan (SARIF format) → GitHub Security tab
     3. Vulnerability enforcement (exit-code: 1 on CRITICAL/HIGH)
     4. Trivy filesystem scan (source code analysis)
     5. Filesystem vulnerability enforcement
     6. Export image to artifact (1-day retention)
   - Trivy configuration: `trivyignores: .trivyignore` for documented exceptions
   - Severity filter: `CRITICAL,HIGH`

3. **security-scan-training** - Training container security assessment
   - Same pattern as security-scan-api
   - Independent execution path

4. **push-and-sign-api** - Image deployment with cryptographic attestation
   - Dependencies: `changes`, `security-scan-api`
   - Steps:
     1. Download cached image artifact
     2. Load image from tar archive
     3. AWS OIDC authentication (`configure-aws-credentials@v4`)
     4. ECR login (`amazon-ecr-login@v2`)
     5. Extract metadata tags (branch, SHA, semver, latest, timestamp)
     6. Tag and push to ECR (multi-tag loop)
     7. Extract image digest from RepoDigests
     8. Cosign keyless signing (OIDC-based, no private key storage)
     9. Signature verification
     10. Deployment summary to GitHub Step Summary
   - Authentication: Temporary credentials via OIDC (no long-lived secrets)
   - Signing: Sigstore Fulcio keyless workflow

5. **push-and-sign-training** - Training image deployment
   - Same pattern as push-and-sign-api
   - Independent execution path

6. **cleanup** - Artifact lifecycle management
   - Dependencies: All push jobs
   - Execution: `if: always()` (runs on success or failure)
   - Actions:
     - Delete `api-image` artifact (`failOnError: false`)
     - Delete `training-image` artifact (`failOnError: false`)
   - Purpose: Prevent artifact storage quota exhaustion

## DevSecOps Implementation

### Supply Chain Security

- **Image Signing:** Cosign keyless signatures using Sigstore (OIDC-based)
- **Signature Verification:** Automated verification post-signing
- **Provenance:** Git commit SHA embedded in image labels and deployment metadata
- **Artifact Integrity:** SHA256 digests tracked for all pushed images
- **Secrets Scanning:** Gitleaks prevents credential leakage

### Vulnerability Management

- **Container Scanning:** Trivy (CRITICAL/HIGH severity enforcement)
- **Filesystem Scanning:** Trivy source code analysis
- **SARIF Integration:** Results uploaded to GitHub Advanced Security
- **Risk Acceptance:** Documented exceptions in `.trivyignore` with justification
- **Threshold Enforcement:** Build fails on actionable vulnerabilities (exit-code: 1)

### Authentication & Authorization

- **Zero Static Credentials:** AWS OIDC eliminates long-lived access keys
- **Least Privilege IAM:** Scoped to specific ECR repositories and S3 buckets
- **OIDC Constraints:** Repository-scoped federated identity
- **Temporary Credentials:** 1-hour TTL, auto-rotated per workflow run
- **GitHub Token:** Auto-generated ephemeral token with minimal permissions

### Data Protection

- **Registry Encryption:** ECR images encrypted at rest (KMS)
- **Transit Security:** TLS 1.3 for all AWS API calls
- **Artifact Encryption:** GitHub Actions artifacts encrypted at rest
- **No Credential Exposure:** OIDC flow prevents secret sprawl

### Shift-Left Security

- **Pre-Merge Scanning:** CI validates security before code enters main branch
- **Fast Feedback:** Security findings visible in PR checks
- **Automated Remediation:** Dependabot PRs for vulnerable dependencies
- **Policy as Code:** Workflow definitions version-controlled

## Prerequisites

### GitHub Repository Configuration

#### Secrets (Repository Settings → Secrets and Variables → Actions → Secrets)

| Name | Description | Example |
|------|-------------|---------|
| `AWS_ROLE_ARN` | IAM role ARN for OIDC authentication | `arn:aws:iam::123456789012:role/github-actions-ecr` |
| `ECR_API_REPOSITORY_URL` | Full ECR repository URL for API image | `123456789012.dkr.ecr.us-east-1.amazonaws.com/mlops-api` |
| `ECR_TRAINING_REPOSITORY_URL` | Full ECR repository URL for training image | `123456789012.dkr.ecr.us-east-1.amazonaws.com/mlops-training` |
| `MODELS_BUCKET_NAME` | S3 bucket name for model artifacts | `mlops-models-production` |

#### Variables (Repository Settings → Secrets and Variables → Actions → Variables)

| Name | Description | Example |
|------|-------------|---------|
| `AWS_REGION` | AWS region for resource deployment | `us-east-1` |
| `ENVIRONMENT` | Deployment environment identifier | `production` |
| `DOCKER_BUILDKIT` | Enable BuildKit for Docker builds | `1` |

### AWS Infrastructure Requirements

The workflows assume the following AWS resources exist:

1. **IAM OIDC Provider**
   - URL: `https://token.actions.githubusercontent.com`
   - Audience: `sts.amazonaws.com`
   - Thumbprint: Auto-updated via Terraform

2. **IAM Role for GitHub Actions**
   - Trust policy: Federated identity with repository constraint
   - Permissions:
     - `ecr:GetAuthorizationToken` (global)
     - `ecr:BatchCheckLayerAvailability`
     - `ecr:PutImage`
     - `ecr:InitiateLayerUpload`
     - `ecr:UploadLayerPart`
     - `ecr:CompleteLayerUpload`
     - `ecr:BatchGetImage`
     - `ecr:GetDownloadUrlForLayer` (for Cosign verification)
     - `ecr:DescribeImages`
     - `ecr:DescribeRepositories`

3. **ECR Repositories**
   - API repository with scan-on-push enabled
   - Training repository with scan-on-push enabled
   - Tag immutability: `MUTABLE` (allows tag updates)
   - Image encryption: KMS (CMK)

4. **S3 Bucket**
   - Models bucket with versioning enabled
   - Server-side encryption: KMS
   - Public access: Blocked

### Local Development Requirements

- Python 3.13
- uv 0.9.7 (package manager)
- Docker with BuildKit support
- Git 2.30+

## Monitoring and Troubleshooting

### Viewing Workflow Results

1. **GitHub Actions Tab:** Real-time execution logs
2. **Security Tab → Code Scanning:** Trivy SARIF results
3. **Security Tab → Secret Scanning:** Gitleaks findings
4. **Checks Tab (PR):** Inline status for each job

### Common Failure Scenarios

#### Trivy Scan Failure

**Symptom:** `exit code 1` in vulnerability check step

**Resolution:**
1. Update vulnerable dependencies in `pyproject.toml`
2. Run `uv sync` to update `uv.lock`
3. If unfixable, document in `.trivyignore` with risk justification
4. Commit and push changes

#### OIDC Authentication Failure

**Symptom:** `Error: Could not assume role`

**Resolution:**
```bash
# Verify trust policy in IAM role
aws iam get-role --role-name github-actions-ecr

# Check OIDC provider
aws iam list-open-id-connect-providers
```

#### ECR Push Failure

**Symptom:** `denied: User is not authorized to perform: ecr:PutImage`

**Resolution:**
```bash
# Verify repository exists
aws ecr describe-repositories --repository-names mlops-api

# Check IAM role permissions
aws iam get-role-policy --role-name github-actions-ecr --policy-name ecr-policy
```

## Performance Optimization

### Build Time Reduction

1. **BuildKit Caching:** GitHub Actions cache (`type=gha`) reduces layer rebuild time
2. **Parallel Execution:** Independent jobs run concurrently
3. **Change Detection:** Skip unchanged components (avg 40% time savings)
4. **Artifact Reuse:** Build once in scan job, reuse in push job

### Cost Optimization

1. **Conditional Execution:** Only run necessary jobs based on file changes
2. **Artifact Cleanup:** Auto-delete after 1 day (prevents storage quota exhaustion)
3. **OIDC:** No KMS costs for credential encryption (vs. GitHub encrypted secrets)
4. **BuildKit Cache:** Reduces compute time (billed per minute)

## Future Enhancements

1. **Dependency Review:** GitHub Dependency Review Action for PR checks
2. **CodeQL SAST:** Static application security testing for Python vulnerabilities
3. **Action Pinning:** SHA-based action references for supply chain security
4. **Multi-Arch Builds:** ARM64 + AMD64 image support
5. **Policy Enforcement:** OPA/Conftest for Dockerfile linting
6. **SBOM Generation:** CycloneDX software bill of materials
7. **Deployment Gates:** Manual approval for production deployments
8. **Canary Deployments:** Progressive rollout with traffic splitting

## References

- [GitHub Actions OIDC](https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/about-security-hardening-with-openid-connect)
- [Trivy Documentation](https://aquasecurity.github.io/trivy/)
- [Cosign Keyless Signatures](https://docs.sigstore.dev/cosign/keyless/)
- [Docker BuildKit](https://docs.docker.com/build/buildkit/)
- [SARIF Format](https://sarifweb.azurewebsites.net/)
