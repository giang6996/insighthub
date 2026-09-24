variable "rds_engine_version" {
  description = "PostgreSQL version supported by the selected RDS region and pgvector requirement."
  type        = string
  default     = "16.15"
}

variable "rds_instance_class" {
  description = "Small demo RDS instance class."
  type        = string
  default     = "db.t3.micro"
}

variable "rds_allocated_storage" {
  description = "Initial RDS storage in GiB."
  type        = number
  default     = 20
}

variable "rds_max_allocated_storage" {
  description = "Maximum autoscaled RDS storage in GiB."
  type        = number
  default     = 50
}

variable "rds_database_name" {
  description = "Initial PostgreSQL database name."
  type        = string
  default     = "insighthub"
}

variable "rds_master_username" {
  description = "RDS master username. The password is generated and managed by RDS."
  type        = string
  default     = "insighthub"
}

variable "rds_deletion_protection" {
  description = "Whether the demo RDS instance prevents deletion."
  type        = bool
  default     = false
}

resource "aws_db_subnet_group" "this" {
  name       = "${local.name_prefix}-rds"
  subnet_ids = aws_subnet.private[*].id

  tags = {
    Name = "${local.name_prefix}-rds-subnets"
  }
}

resource "aws_db_instance" "this" {
  # checkov:skip=CKV_AWS_293:Short-lived Day 3 demo must remain immediately destroyable; deletion protection is deferred and this is not production guidance.
  # checkov:skip=CKV_AWS_157:Day 3 intentionally uses a single-AZ RDS instance for cost control; Multi-AZ is deferred and this is not production guidance.
  # checkov:skip=CKV_AWS_118:Enhanced RDS monitoring is deferred to the observability stage for this short-lived Day 3 demo; this is not production guidance.
  # checkov:skip=CKV_AWS_353:Performance Insights is deferred to the observability stage for this short-lived Day 3 demo; this is not production guidance.
  # checkov:skip=CKV2_AWS_30:PostgreSQL query logging is deferred to the observability stage for this short-lived Day 3 demo; this is not production guidance.
  identifier = "${local.name_prefix}-postgres"

  engine         = "postgres"
  engine_version = var.rds_engine_version
  instance_class = var.rds_instance_class

  allocated_storage     = var.rds_allocated_storage
  max_allocated_storage = var.rds_max_allocated_storage
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name  = var.rds_database_name
  username = var.rds_master_username

  manage_master_user_password = true

  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  publicly_accessible    = false

  backup_retention_period = 1
  deletion_protection     = var.rds_deletion_protection
  skip_final_snapshot     = true
  copy_tags_to_snapshot   = true

  enabled_cloudwatch_logs_exports     = ["postgresql"]
  iam_database_authentication_enabled = true

  apply_immediately          = true
  auto_minor_version_upgrade = true

  tags = {
    Name = "${local.name_prefix}-postgres"
  }
}
