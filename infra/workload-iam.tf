resource "aws_iam_role" "insighthub_secrets" {
  name = "${local.name_prefix}-workload-secrets"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Federated = aws_iam_openid_connect_provider.eks.arn
      }
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "${local.eks_oidc_issuer_host}:aud" = "sts.amazonaws.com"
        }
        StringLike = {
          "${local.eks_oidc_issuer_host}:sub" = [
            "system:serviceaccount:insighthub:api",
            "system:serviceaccount:insighthub:ingestion-worker",
            "system:serviceaccount:insighthub:db-bootstrap",
          ]
        }
      }
    }]
  })

  tags = {
    Name = "${local.name_prefix}-workload-secrets-role"
  }
}

resource "aws_iam_role_policy" "insighthub_secrets" {
  name = "${local.name_prefix}-read-rds-secret"
  role = aws_iam_role.insighthub_secrets.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "secretsmanager:DescribeSecret",
        "secretsmanager:GetSecretValue",
      ]
      Resource = aws_db_instance.this.master_user_secret[0].secret_arn
    }]
  })
}

resource "aws_eks_addon" "secrets_store_provider" {
  cluster_name = aws_eks_cluster.this.name
  addon_name   = "aws-secrets-store-csi-driver-provider"
  # Keep the proven Day 3 build deterministic; upgrades require deliberate review.
  addon_version = var.secrets_store_provider_addon_version

  depends_on = [
    aws_iam_role_policy_attachment.efs_csi,
  ]

  tags = {
    Name = "${local.name_prefix}-secrets-store-provider"
  }
}
