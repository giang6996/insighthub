resource "aws_kms_key" "data_services" {
  description             = "Day 3 data services encryption for ${local.name_prefix}"
  enable_key_rotation     = true
  deletion_window_in_days = 7

  tags = {
    Name = "${local.name_prefix}-data-services"
  }
}

resource "aws_kms_alias" "data_services" {
  name          = "alias/${local.name_prefix}-data-services"
  target_key_id = aws_kms_key.data_services.key_id
}

resource "aws_kms_key_policy" "data_services" {
  key_id = aws_kms_key.data_services.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "EnableRootAccountPermissions"
      Effect = "Allow"
      Principal = {
        AWS = "arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.current.account_id}:root"
      }
      Action   = "kms:*"
      Resource = "*"
    }]
  })
}

resource "aws_security_group" "rds" {
  name        = "${local.name_prefix}-rds"
  description = "PostgreSQL access from the EKS workload security boundary"
  vpc_id      = aws_vpc.this.id

  tags = {
    Name = "${local.name_prefix}-rds-sg"
  }
}

resource "aws_vpc_security_group_ingress_rule" "rds_from_eks" {
  security_group_id            = aws_security_group.rds.id
  referenced_security_group_id = aws_eks_cluster.this.vpc_config[0].cluster_security_group_id
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
  description                  = "PostgreSQL from EKS workloads"
}

resource "aws_security_group" "redis" {
  name        = "${local.name_prefix}-redis"
  description = "Redis access from the EKS workload security boundary"
  vpc_id      = aws_vpc.this.id

  tags = {
    Name = "${local.name_prefix}-redis-sg"
  }
}

resource "aws_vpc_security_group_ingress_rule" "redis_from_eks" {
  security_group_id            = aws_security_group.redis.id
  referenced_security_group_id = aws_eks_cluster.this.vpc_config[0].cluster_security_group_id
  from_port                    = 6379
  to_port                      = 6379
  ip_protocol                  = "tcp"
  description                  = "TLS Redis from EKS workloads"
}

resource "aws_security_group" "efs" {
  name        = "${local.name_prefix}-efs"
  description = "NFS access from the EKS workload security boundary"
  vpc_id      = aws_vpc.this.id

  tags = {
    Name = "${local.name_prefix}-efs-sg"
  }
}

resource "aws_vpc_security_group_ingress_rule" "efs_from_eks" {
  security_group_id            = aws_security_group.efs.id
  referenced_security_group_id = aws_eks_cluster.this.vpc_config[0].cluster_security_group_id
  from_port                    = 2049
  to_port                      = 2049
  ip_protocol                  = "tcp"
  description                  = "NFS staging storage from EKS workloads"
}
