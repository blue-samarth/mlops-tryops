variable "aws_region" { default = "us-east-1" }
variable "project_name" { default = null }
variable "environment" { default = null }
variable "namespace" { default = null }
variable "short_name" { default = null }

variable "s3_bucket_name" { default = null }
variable "s3_expiration_days" { default = 90 }
variable "block_public_access" { default = true }
variable "versioning_enabled" { default = true }
variable "server_side_encryption" { default = true }
variable "prevent_s3_bucket_destroy" { default = false }
variable "s3_force_destroy" { default = false }

variable "eks_cluster_version" { default = "1.29" }
variable "eks_node_instance_types" { default = ["t3.medium"] }
variable "eks_node_desired_size" { default = 2 }
variable "eks_node_min_size" { default = 1 }
variable "eks_node_max_size" { default = 5 }

variable "vpc_cidr" { default = "10.0.0.0/16" }
variable "availability_zones" { default = ["us-east-1a", "us-east-1b", "us-east-1c"] }
variable "enable_nat_gateway" { default = true }
variable "single_nat_gateway" { default = false } # HA = false

variable "enable_prometheus" { default = true }
variable "enable_grafana" { default = true }
variable "metrics_retention_days" { default = 30 }

variable "ecr_image_retention_count" { default = 10 }
variable "ecr_scan_on_push" { default = true }
