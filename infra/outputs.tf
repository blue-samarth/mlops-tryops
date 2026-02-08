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

# EKS Cluster
output "eks_cluster_id" {
  description = "EKS cluster ID"
  value       = aws_eks_cluster.main.id
}

output "eks_cluster_name" {
  description = "EKS cluster name"
  value       = aws_eks_cluster.main.name
}

output "eks_cluster_endpoint" {
  description = "Endpoint for EKS control plane"
  value       = aws_eks_cluster.main.endpoint
}

output "eks_cluster_version" {
  description = "EKS cluster Kubernetes version"
  value       = aws_eks_cluster.main.version
}

output "eks_cluster_security_group_id" {
  description = "Security group ID attached to the EKS cluster"
  value       = aws_security_group.eks_cluster.id
}

output "eks_cluster_oidc_issuer_url" {
  description = "The URL on the EKS cluster OIDC Issuer"
  value       = try(aws_eks_cluster.main.identity[0].oidc[0].issuer, "")
}

output "eks_oidc_provider_arn" {
  description = "ARN of the OIDC Provider for EKS"
  value       = aws_iam_openid_connect_provider.eks.arn
}

# EKS Node Groups
output "eks_api_node_group_id" {
  description = "EKS API node group ID"
  value       = aws_eks_node_group.api.id
}

output "eks_training_node_group_id" {
  description = "EKS Training node group ID"
  value       = aws_eks_node_group.training.id
}

output "eks_nodes_security_group_id" {
  description = "Security group ID attached to the EKS nodes"
  value       = aws_security_group.eks_nodes.id
}

# EKS Service Account Roles
output "api_service_account_role_arn" {
  description = "ARN of IAM role for API service account"
  value       = aws_iam_role.api_service_account.arn
}

output "training_service_account_role_arn" {
  description = "ARN of IAM role for Training service account"
  value       = aws_iam_role.training_service_account.arn
}

# Kubeconfig Command
output "configure_kubectl" {
  description = "Command to configure kubectl"
  value       = "aws eks update-kubeconfig --region ${local.aws_region} --name ${aws_eks_cluster.main.name}"
}
