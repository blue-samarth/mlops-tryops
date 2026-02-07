variable "github_personal_access_token" {
  description = "GitHub PAT with repo and admin:repo_hook permissions"
  type        = string
  sensitive   = true
  default     = null
}

variable "github_owner" {
  description = "GitHub owner or organization name"
  type        = string
}

variable "github_repo" {
  description = "GitHub repository name"
  type        = string
}

# AWS Outputs (from parent terraform)
variable "aws_role_arn" {
  description = "ARN of the IAM role for GitHub Actions to assume"
  type        = string
}

variable "ecr_api_repository_url" {
  description = "URL of the API ECR repository"
  type        = string
}

variable "ecr_training_repository_url" {
  description = "URL of the Training ECR repository"
  type        = string
}

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "models_bucket_name" {
  description = "Name of the S3 bucket for models"
  type        = string
}