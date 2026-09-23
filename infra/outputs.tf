output "vpc_id" {
  description = "VPC ID for later infrastructure layers."
  value       = aws_vpc.this.id
}

output "public_subnet_ids" {
  description = "Public subnet IDs for later load balancer integration."
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "Private subnet IDs for later EKS and data services."
  value       = aws_subnet.private[*].id
}

output "nat_gateway_id" {
  description = "Single demo NAT Gateway ID."
  value       = aws_nat_gateway.this.id
}

output "public_route_table_id" {
  description = "Public route table ID."
  value       = aws_route_table.public.id
}

output "private_route_table_id" {
  description = "Private route table ID."
  value       = aws_route_table.private.id
}

output "eks_cluster_name" {
  description = "EKS cluster name."
  value       = aws_eks_cluster.this.name
}

output "eks_cluster_endpoint" {
  description = "Private EKS Kubernetes API endpoint."
  value       = aws_eks_cluster.this.endpoint
}

output "eks_cluster_security_group_id" {
  description = "EKS cluster security group ID."
  value       = aws_eks_cluster.this.vpc_config[0].cluster_security_group_id
}

output "eks_node_group_name" {
  description = "Managed EKS node group name."
  value       = aws_eks_node_group.this.node_group_name
}

output "ecr_repository_urls" {
  description = "ECR repository URLs for the three application images."
  value       = { for name, repository in aws_ecr_repository.this : name => repository.repository_url }
}

output "eks_cluster_role_arn" {
  description = "EKS cluster IAM role ARN."
  value       = aws_iam_role.eks_cluster.arn
}

output "eks_node_role_arn" {
  description = "EKS node IAM role ARN."
  value       = aws_iam_role.eks_nodes.arn
}

output "github_iac_role_arn" {
  description = "GitHub Actions IaC OIDC role ARN."
  value       = aws_iam_role.github_iac.arn
}

output "rds_endpoint" {
  description = "Private RDS endpoint hostname."
  value       = aws_db_instance.this.address
}

output "rds_port" {
  description = "RDS PostgreSQL port."
  value       = aws_db_instance.this.port
}

output "rds_master_secret_arn" {
  description = "AWS-managed RDS master password secret ARN."
  value       = aws_db_instance.this.master_user_secret[0].secret_arn
  sensitive   = true
}

output "redis_primary_endpoint" {
  description = "Private TLS Redis primary endpoint."
  value       = aws_elasticache_replication_group.this.primary_endpoint_address
}

output "redis_port" {
  description = "Redis port."
  value       = aws_elasticache_replication_group.this.port
}

output "efs_file_system_id" {
  description = "Encrypted EFS filesystem ID for shared staging."
  value       = aws_efs_file_system.staging.id
}

output "efs_access_point_id" {
  description = "EFS access point ID for the shared staging path."
  value       = aws_efs_access_point.staging.id
}

output "rds_security_group_id" {
  description = "RDS security group ID."
  value       = aws_security_group.rds.id
}

output "redis_security_group_id" {
  description = "ElastiCache Redis security group ID."
  value       = aws_security_group.redis.id
}

output "efs_security_group_id" {
  description = "EFS security group ID."
  value       = aws_security_group.efs.id
}

output "insighthub_secrets_role_arn" {
  description = "IRSA role ARN for API, worker, and DB bootstrap secret access."
  value       = aws_iam_role.insighthub_secrets.arn
}
