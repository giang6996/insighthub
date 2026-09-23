variable "redis_engine_version" {
  description = "Redis engine version for the single-node demo cache."
  type        = string
  default     = "7.1"
}

variable "redis_node_type" {
  description = "Small demo ElastiCache node type."
  type        = string
  default     = "cache.t3.micro"
}

resource "aws_elasticache_subnet_group" "this" {
  name       = "${local.name_prefix}-redis"
  subnet_ids = aws_subnet.private[*].id

  tags = {
    Name = "${local.name_prefix}-redis-subnets"
  }
}

resource "aws_elasticache_replication_group" "this" {
  replication_group_id = "${var.project_name}-${var.environment}"
  description          = "Single-node TLS Redis queue for ${local.name_prefix}"

  engine         = "redis"
  engine_version = var.redis_engine_version
  node_type      = var.redis_node_type
  port           = 6379

  num_cache_clusters         = 1
  automatic_failover_enabled = false
  multi_az_enabled           = false

  transit_encryption_enabled = true
  at_rest_encryption_enabled = true

  subnet_group_name  = aws_elasticache_subnet_group.this.name
  security_group_ids = [aws_security_group.redis.id]

  apply_immediately        = true
  snapshot_retention_limit = 0

  tags = {
    Name = "${local.name_prefix}-redis"
  }
}
