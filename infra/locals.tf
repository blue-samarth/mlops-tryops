data "aws_caller_identity" "current" {}
data "aws_region" "current" {}


locals {
  aws_account_id = data.aws_caller_identity.current.account_id
  aws_region     = data.aws_region.current.id

  name        = coalesce(var.project_name, "Samarths-ML-Ops-Project")
  short_name  = coalesce(var.short_name, "sam-mlops")
  environment = coalesce(var.environment, "production")
  namespace   = coalesce(var.namespace, "terraform")
  name_prefix = "${local.short_name}-${local.environment}"

  # S3 Configuration
  bucket_name               = coalesce(var.s3_bucket_name, "${local.name_prefix}-models-${local.aws_account_id}")
  s3_expiration_days        = coalesce(var.s3_expiration_days, 90)
  block_public_access       = coalesce(var.block_public_access, true)
  versioning_enabled        = coalesce(var.versioning_enabled, true)
  server_side_encryption    = coalesce(var.server_side_encryption, true)
  prevent_s3_bucket_destroy = coalesce(var.prevent_s3_bucket_destroy, false)
  s3_force_destroy          = coalesce(var.s3_force_destroy, false)

  # EKS Configuration
  eks_cluster_name        = "${local.name_prefix}-eks"
  eks_cluster_version     = coalesce(var.eks_cluster_version, "1.33")
  eks_node_instance_types = coalesce(var.eks_node_instance_types, ["t3.medium"])
  eks_node_desired_size   = coalesce(var.eks_node_desired_size, 2)
  eks_node_min_size       = coalesce(var.eks_node_min_size, 1)
  eks_node_max_size       = coalesce(var.eks_node_max_size, 5)

  # VPC Configuration
  vpc_cidr           = coalesce(var.vpc_cidr, "10.0.0.0/16")
  availability_zones = coalesce(var.availability_zones, ["us-east-1a", "us-east-1b", "us-east-1c"])
  enable_nat_gateway = coalesce(var.enable_nat_gateway, true)
  single_nat_gateway = coalesce(var.single_nat_gateway, false)

  # ECR Configuration
  ecr_api_repo_name         = "${local.name_prefix}-api"
  ecr_training_repo_name    = "${local.name_prefix}-training"
  ecr_image_retention_count = coalesce(var.ecr_image_retention_count, 5)
  ecr_scan_on_push          = coalesce(var.ecr_scan_on_push, true)

  # Monitoring Configuration
  enable_prometheus      = coalesce(var.enable_prometheus, true)
  enable_grafana         = coalesce(var.enable_grafana, true)
  metrics_retention_days = coalesce(var.metrics_retention_days, 30)

  # GitHub OIDC Configuration
  github_org  = coalesce(var.github_org, "your-github-org")
  github_repo = coalesce(var.github_repo, "try_ops")

  # Common Tags
  common_tags = {
    Project     = local.name
    Environment = local.environment
    Namespace   = local.namespace
    ManagedBy   = "Terraform"
  }
}