# Terraform Outputs

# GitHub Actions IAM Role
output "github_actions_role_arn" {
  description = "ARN of the IAM role for GitHub Actions to assume"
  value       = aws_iam_role.github_actions_ecr.arn
}

output "github_actions_role_name" {
  description = "Name of the IAM role for GitHub Actions"
  value       = aws_iam_role.github_actions_ecr.name
}

# ECR Repository URLs
output "ecr_api_repository_url" {
  description = "URL of the API ECR repository"
  value       = aws_ecr_repository.api.repository_url
}

output "ecr_training_repository_url" {
  description = "URL of the Training ECR repository"
  value       = aws_ecr_repository.training.repository_url
}

# VPC
output "vpc_id" {
  description = "ID of the VPC"
  value       = aws_vpc.main.id
}

output "private_subnet_ids" {
  description = "IDs of private subnets"
  value       = aws_subnet.private[*].id
}

output "public_subnet_ids" {
  description = "IDs of public subnets"
  value       = aws_subnet.public[*].id
}

# S3
output "models_bucket_name" {
  description = "Name of the S3 bucket for models"
  value       = aws_s3_bucket.models.id
}

output "models_bucket_arn" {
  description = "ARN of the S3 bucket for models"
  value       = aws_s3_bucket.models.arn
}

# AWS Region
output "aws_region" {
  description = "AWS region"
  value       = local.aws_region
}

# GitHub integration outputs
output "github_org" {
  description = "GitHub organization/owner"
  value       = local.github_org
}

output "github_repo" {
  description = "GitHub repository name"
  value       = local.github_repo
}
