# AWS OIDC Role ARN
resource "github_actions_secret" "aws_role_arn" {
  repository      = var.github_repo
  secret_name     = "AWS_ROLE_ARN"
  plaintext_value = var.aws_role_arn
}

# ECR Repository URLs
resource "github_actions_secret" "ecr_api_repository_url" {
  repository      = var.github_repo
  secret_name     = "ECR_API_REPOSITORY_URL"
  plaintext_value = var.ecr_api_repository_url
}

resource "github_actions_secret" "ecr_training_repository_url" {
  repository      = var.github_repo
  secret_name     = "ECR_TRAINING_REPOSITORY_URL"
  plaintext_value = var.ecr_training_repository_url
}

# AWS Region
resource "github_actions_secret" "aws_region" {
  repository      = var.github_repo
  secret_name     = "AWS_REGION"
  plaintext_value = var.aws_region
}

# S3 Models Bucket
resource "github_actions_secret" "models_bucket_name" {
  repository      = var.github_repo
  secret_name     = "MODELS_BUCKET_NAME"
  plaintext_value = var.models_bucket_name
}

# GitHub PAT (for workflows that need to interact with GitHub API)
resource "github_actions_secret" "github_token" {
  repository      = var.github_repo
  secret_name     = "GH_PAT"
  plaintext_value = var.github_personal_access_token
}

# Outputs
output "secrets_created" {
  description = "List of GitHub secrets created"
  value = [
    github_actions_secret.aws_role_arn.secret_name,
    github_actions_secret.ecr_api_repository_url.secret_name,
    github_actions_secret.ecr_training_repository_url.secret_name,
    github_actions_secret.aws_region.secret_name,
    github_actions_secret.models_bucket_name.secret_name,
    github_actions_secret.github_token.secret_name,
  ]
}

output "repository_full_name" {
  description = "Full name of the GitHub repository"
  value       = "${var.github_owner}/${var.github_repo}"
}
