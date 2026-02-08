resource "aws_kms_key" "eks" {
  description             = "${local.name_prefix} EKS cluster encryption key"
  deletion_window_in_days = 30
  enable_key_rotation     = true

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "Enable IAM User Permissions"
        Effect    = "Allow"
        Principal = { AWS = "arn:aws:iam::${local.aws_account_id}:root" }
        Action    = "kms:*"
        Resource  = "*"
      },
      {
        Sid       = "Allow CloudWatch Logs"
        Effect    = "Allow"
        Principal = { Service = "logs.${local.aws_region}.amazonaws.com" }
        Action    = ["kms:Encrypt", "kms:Decrypt", "kms:ReEncrypt*", "kms:GenerateDataKey*", "kms:CreateGrant", "kms:DescribeKey"]
        Resource  = "*"
        Condition = {
          ArnLike = {
            "kms:EncryptionContext:aws:logs:arn" = "arn:aws:logs:${local.aws_region}:${local.aws_account_id}:log-group:/aws/eks/${local.eks_cluster_name}/*"
          }
        }
      },
      {
        Sid       = "Allow EKS to use the key"
        Effect    = "Allow"
        Principal = { Service = "eks.amazonaws.com" }
        Action    = ["kms:Decrypt", "kms:DescribeKey", "kms:Encrypt", "kms:ReEncrypt*", "kms:GenerateDataKey*"]
        Resource  = "*"
      },
      {
        Sid    = "Allow EC2 service to use the key for EBS"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
        Action   = ["kms:Decrypt", "kms:Encrypt", "kms:ReEncrypt*", "kms:GenerateDataKey*", "kms:CreateGrant", "kms:DescribeKey"]
        Resource = "*"
      },
      {
        Sid       = "Allow EKS Node IAM Role"
        Effect    = "Allow"
        Principal = { AWS = aws_iam_role.eks_nodes.arn }
        Action    = ["kms:Decrypt", "kms:Encrypt", "kms:ReEncrypt*", "kms:GenerateDataKey*", "kms:CreateGrant", "kms:DescribeKey"]
        Resource  = "*"
      },
      {
        Sid       = "Allow AutoScaling service to use the key"
        Effect    = "Allow"
        Principal = { Service = "autoscaling.amazonaws.com" }
        Action    = ["kms:Decrypt", "kms:Encrypt", "kms:ReEncrypt*", "kms:GenerateDataKey*", "kms:CreateGrant", "kms:DescribeKey"]
        Resource  = "*"
      },
      {
        Sid       = "Allow AutoScaling Service-Linked Role"
        Effect    = "Allow"
        Principal = { AWS = "arn:aws:iam::${local.aws_account_id}:role/aws-service-role/autoscaling.amazonaws.com/AWSServiceRoleForAutoScaling" }
        Action    = ["kms:Encrypt", "kms:Decrypt", "kms:ReEncrypt*", "kms:GenerateDataKey*", "kms:DescribeKey", "kms:CreateGrant"]
        Resource  = "*"
        Condition = {
          Bool = { "kms:GrantIsForAWSResource" = "true" }
        }
      }
    ]
  })

  tags = merge(local.common_tags, { Name = "${local.name_prefix}-eks-encryption-key" })
}

resource "aws_kms_alias" "eks" {
  name          = "alias/${local.name_prefix}-eks"
  target_key_id = aws_kms_key.eks.key_id
}

resource "aws_cloudwatch_log_group" "eks_cluster" {
  name              = "/aws/eks/${local.eks_cluster_name}/cluster"
  retention_in_days = local.metrics_retention_days
  kms_key_id        = aws_kms_key.eks.arn

  tags = merge(local.common_tags, { Name = "${local.name_prefix}-eks-cluster-logs" })
}

resource "aws_iam_role" "eks_cluster" {
  name = "${local.name_prefix}-eks-cluster-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Service = "eks.amazonaws.com" }
        Action    = "sts:AssumeRole"
      }
    ]
  })
  tags = local.common_tags
}

resource "aws_iam_role_policy_attachment" "eks_cluster_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
  role       = aws_iam_role.eks_cluster.name
}

resource "aws_iam_role_policy_attachment" "eks_vpc_resource_controller" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSVPCResourceController"
  role       = aws_iam_role.eks_cluster.name
}

resource "aws_security_group" "eks_cluster" {
  name        = "${local.name_prefix}-eks-cluster-sg"
  description = "Security group for EKS cluster control plane"
  vpc_id      = aws_vpc.main.id

  tags = merge(local.common_tags, { Name = "${local.name_prefix}-eks-cluster-sg" })
}

resource "aws_security_group_rule" "eks_cluster_ingress_nodes" {
  type                     = "ingress"
  from_port                = 443
  to_port                  = 443
  protocol                 = "tcp"
  security_group_id        = aws_security_group.eks_cluster.id
  source_security_group_id = aws_security_group.eks_nodes.id
  description              = "Allow HTTPS traffic from worker nodes"
}

resource "aws_security_group_rule" "eks_cluster_egress" {
  type              = "egress"
  from_port         = 0
  to_port           = 0
  protocol          = "-1"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.eks_cluster.id
  description       = "Allow all outbound traffic"
}

resource "aws_security_group_rule" "eks_cluster_egress_to_nodes" {
  type                     = "egress"
  from_port                = 1025
  to_port                  = 65535
  protocol                 = "tcp"
  security_group_id        = aws_security_group.eks_cluster.id
  source_security_group_id = aws_security_group.eks_nodes.id
  description              = "Allow cluster control plane to communicate with worker nodes"
}

resource "aws_eks_cluster" "main" {
  name     = local.eks_cluster_name
  role_arn = aws_iam_role.eks_cluster.arn
  version  = local.eks_cluster_version

  vpc_config {
    subnet_ids              = concat(aws_subnet.private[*].id, aws_subnet.public[*].id)
    endpoint_private_access = true
    endpoint_public_access  = true
    public_access_cidrs     = ["0.0.0.0/0"]
    security_group_ids      = [aws_security_group.eks_cluster.id]
  }

  encryption_config {
    provider { key_arn = aws_kms_key.eks.arn }
    resources = ["secrets"]
  }

  enabled_cluster_log_types = ["api", "audit", "authenticator", "controllerManager", "scheduler"]

  timeouts {
    create = "30m"
    update = "30m"
    delete = "15m"
  }

  depends_on = [aws_iam_role_policy_attachment.eks_cluster_policy, aws_iam_role_policy_attachment.eks_vpc_resource_controller, aws_cloudwatch_log_group.eks_cluster]
  tags       = merge(local.common_tags, { Name = local.eks_cluster_name })
}

data "tls_certificate" "eks_oidc" { url = aws_eks_cluster.main.identity[0].oidc[0].issuer }

resource "aws_iam_openid_connect_provider" "eks" {
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.eks_oidc.certificates[0].sha1_fingerprint]
  url             = aws_eks_cluster.main.identity[0].oidc[0].issuer

  tags = merge(local.common_tags, { Name = "${local.name_prefix}-eks-oidc-provider" })
}
