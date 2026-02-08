resource "aws_security_group" "eks_nodes" {
  name        = "${local.name_prefix}-eks-nodes-sg"
  description = "Security group for EKS worker nodes"
  vpc_id      = aws_vpc.main.id

  tags = merge(
    local.common_tags,
    {
      Name                                              = "${local.name_prefix}-eks-nodes-sg"
      "kubernetes.io/cluster/${local.eks_cluster_name}" = "owned"
    }
  )
}

resource "aws_security_group_rule" "eks_nodes_internal" {
  type              = "ingress"
  from_port         = 0
  to_port           = 65535
  protocol          = "-1"
  self              = true
  security_group_id = aws_security_group.eks_nodes.id
  description       = "Allow nodes to communicate with each other"
}

resource "aws_security_group_rule" "eks_nodes_cluster_ingress" {
  type                     = "ingress"
  from_port                = 1025
  to_port                  = 65535
  protocol                 = "tcp"
  security_group_id        = aws_security_group.eks_nodes.id
  source_security_group_id = aws_security_group.eks_cluster.id
  description              = "Allow worker Kubelets and pods to receive communication from the cluster control plane"
}

resource "aws_security_group_rule" "eks_nodes_egress" {
  type              = "egress"
  from_port         = 0
  to_port           = 0
  protocol          = "-1"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.eks_nodes.id
  description       = "Allow all outbound traffic"
}

resource "aws_iam_role" "eks_nodes" {
  name = "${local.name_prefix}-eks-nodes-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Service = "ec2.amazonaws.com" }
        Action    = "sts:AssumeRole"
      }
    ]
  })
  tags = local.common_tags
}

resource "aws_iam_role_policy_attachment" "eks_worker_node_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy"
  role       = aws_iam_role.eks_nodes.name
}

resource "aws_iam_role_policy_attachment" "eks_container_registry_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
  role       = aws_iam_role.eks_nodes.name
}

resource "aws_iam_role_policy" "eks_nodes_additional" {
  name = "${local.name_prefix}-eks-nodes-additional-policy"
  role = aws_iam_role.eks_nodes.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "S3ModelRead"
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = ["${aws_s3_bucket.models.arn}/models/*", "${aws_s3_bucket.models.arn}/baselines/*"]
      },
      {
        Sid      = "S3ListBucket"
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = [aws_s3_bucket.models.arn]
        Condition = {
          StringLike = { "s3:prefix" = ["models/*", "baselines/*"] }
        }
      },
      {
        Sid      = "CloudWatchMetrics"
        Effect   = "Allow"
        Action   = ["cloudwatch:PutMetricData"]
        Resource = "*"
        Condition = {
          StringLike = { "cloudwatch:namespace" = "MLOps/*" }
        }
      },
      {
        Sid      = "CloudWatchLogs"
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogStreams"]
        Resource = ["${aws_cloudwatch_log_group.eks_cluster.arn}:*"]
      },
      {
        Sid    = "KMSEBSEncryption"
        Effect = "Allow"
        Action = [
          "kms:Decrypt",
          "kms:Encrypt",
          "kms:ReEncrypt*",
          "kms:GenerateDataKey*",
          "kms:CreateGrant",
          "kms:DescribeKey"
        ]
        Resource = aws_kms_key.eks.arn
      }
    ]
  })
}

resource "aws_launch_template" "api_nodes" {
  name_prefix = "${local.name_prefix}-api-nodes-"
  description = "Launch template for API node group"

  block_device_mappings {
    device_name = "/dev/xvda"

    ebs {
      volume_size           = 20
      volume_type           = "gp3"
      iops                  = 3000
      throughput            = 125
      delete_on_termination = true
    }
  }

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required" # Enforce IMDSv2
    http_put_response_hop_limit = 1
    instance_metadata_tags      = "enabled" # Enable instance tags in metadata
  }

  tag_specifications {
    resource_type = "instance"
    tags          = merge(local.common_tags, { Name = "${local.name_prefix}-api-node" })
  }

  tag_specifications {
    resource_type = "volume"
    tags          = merge(local.common_tags, { Name = "${local.name_prefix}-api-node-volume" })
  }
  tags = local.common_tags
}

resource "aws_launch_template" "training_nodes" {
  name_prefix = "${local.name_prefix}-training-nodes-"
  description = "Launch template for training node group"

  block_device_mappings {
    device_name = "/dev/xvda"

    ebs {
      volume_size           = 30
      volume_type           = "gp3"
      iops                  = 3000
      throughput            = 125
      delete_on_termination = true
    }
  }

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required" # Enforce IMDSv2
    http_put_response_hop_limit = 1
    instance_metadata_tags      = "enabled" # Enable instance tags in metadata
  }

  tag_specifications {
    resource_type = "instance"
    tags          = merge(local.common_tags, { Name = "${local.name_prefix}-training-node" })
  }

  tag_specifications {
    resource_type = "volume"
    tags          = merge(local.common_tags, { Name = "${local.name_prefix}-training-node-volume" })
  }
  tags = local.common_tags
}

resource "aws_eks_node_group" "api" {
  cluster_name    = aws_eks_cluster.main.name
  node_group_name = "${local.name_prefix}-api-nodes"
  node_role_arn   = aws_iam_role.eks_nodes.arn
  subnet_ids      = aws_subnet.private[*].id
  version         = local.eks_cluster_version

  scaling_config {
    desired_size = local.eks_node_desired_size
    min_size     = local.eks_node_min_size
    max_size     = local.eks_node_max_size
  }

  update_config { max_unavailable = 1 }

  launch_template {
    id      = aws_launch_template.api_nodes.id
    version = "$Latest"
  }

  instance_types = local.eks_node_instance_types

  labels = {
    workload = "api"
    tier     = "frontend"
  }

  depends_on = [aws_iam_role_policy_attachment.eks_worker_node_policy, aws_iam_role_policy_attachment.eks_container_registry_policy, aws_iam_role_policy.eks_nodes_additional]
  tags       = merge(local.common_tags, { Name = "${local.name_prefix}-api-node-group" })

  lifecycle {
    create_before_destroy = true
    ignore_changes        = [scaling_config[0].desired_size]
  }
}

resource "aws_eks_node_group" "training" {
  cluster_name    = aws_eks_cluster.main.name
  node_group_name = "${local.name_prefix}-training-nodes"
  node_role_arn   = aws_iam_role.eks_nodes.arn
  subnet_ids      = aws_subnet.private[*].id
  version         = local.eks_cluster_version

  scaling_config {
    desired_size = 1
    min_size     = 0
    max_size     = 3
  }

  update_config { max_unavailable = 1 }

  launch_template {
    id      = aws_launch_template.training_nodes.id
    version = "$Latest"
  }

  instance_types = local.eks_node_instance_types

  labels = {
    workload = "training"
    tier     = "batch"
  }

  taint {
    key    = "training"
    value  = "true"
    effect = "NO_SCHEDULE"
  }

  depends_on = [aws_iam_role_policy_attachment.eks_worker_node_policy, aws_iam_role_policy_attachment.eks_container_registry_policy, aws_iam_role_policy.eks_nodes_additional]
  tags       = merge(local.common_tags, { Name = "${local.name_prefix}-training-node-group" })

  lifecycle {
    create_before_destroy = true
    ignore_changes        = [scaling_config[0].desired_size]
  }
}
