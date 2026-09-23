locals {
  name_prefix = "${var.project_name}-${var.environment}"

  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  }

  azs = data.aws_availability_zones.available.names

  public_subnet_cidrs = [
    for index in range(var.availability_zone_count) : cidrsubnet(var.vpc_cidr, 4, index)
  ]

  private_subnet_cidrs = [
    for index in range(var.availability_zone_count) : cidrsubnet(var.vpc_cidr, 4, index + var.availability_zone_count)
  ]
}
