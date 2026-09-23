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
