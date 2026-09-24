variable "eks_cluster_version" {
  description = "Kubernetes version for the EKS control plane."
  type        = string
  default     = "1.34"
}

variable "eks_node_instance_types" {
  description = "Instance types for the single demo managed node group."
  type        = list(string)
  default     = ["t3.small"]
}

variable "eks_node_desired_size" {
  description = "Desired node count for the demo managed node group."
  type        = number
  default     = 2
}

variable "eks_node_min_size" {
  description = "Minimum node count for the demo managed node group."
  type        = number
  default     = 2
}

variable "eks_node_max_size" {
  description = "Maximum node count for the demo managed node group."
  type        = number
  default     = 3
}

resource "aws_kms_key" "eks_secrets" {
  description             = "EKS Kubernetes Secrets encryption for ${local.name_prefix}"
  enable_key_rotation     = true
  deletion_window_in_days = 7

  tags = {
    Name = "${local.name_prefix}-eks-secrets"
  }
}

resource "aws_kms_alias" "eks_secrets" {
  name          = "alias/${local.name_prefix}-eks-secrets"
  target_key_id = aws_kms_key.eks_secrets.key_id
}

resource "aws_eks_cluster" "this" {
  name     = local.name_prefix
  role_arn = aws_iam_role.eks_cluster.arn
  version  = var.eks_cluster_version

  access_config {
    authentication_mode                         = "API_AND_CONFIG_MAP"
    bootstrap_cluster_creator_admin_permissions = true
  }

  enabled_cluster_log_types = [
    "api",
    "audit",
    "authenticator",
    "controllerManager",
    "scheduler",
  ]

  vpc_config {
    subnet_ids              = aws_subnet.private[*].id
    endpoint_private_access = true
    endpoint_public_access  = false
  }

  encryption_config {
    provider {
      key_arn = aws_kms_key.eks_secrets.arn
    }
    resources = ["secrets"]
  }

  depends_on = [
    aws_iam_role_policy_attachment.eks_cluster,
  ]

  tags = {
    Name = local.name_prefix
  }
}

resource "aws_eks_node_group" "this" {
  cluster_name    = aws_eks_cluster.this.name
  node_group_name = "${local.name_prefix}-nodes"
  node_role_arn   = aws_iam_role.eks_nodes.arn
  subnet_ids      = aws_subnet.private[*].id

  instance_types = var.eks_node_instance_types

  scaling_config {
    desired_size = var.eks_node_desired_size
    min_size     = var.eks_node_min_size
    max_size     = var.eks_node_max_size
  }

  depends_on = [
    aws_iam_role_policy_attachment.eks_nodes_worker,
    aws_iam_role_policy_attachment.eks_nodes_cni,
    aws_iam_role_policy_attachment.eks_nodes_ecr,
  ]

  tags = {
    Name = "${local.name_prefix}-nodes"
  }
}
