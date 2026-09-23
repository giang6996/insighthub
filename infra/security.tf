# The default VPC security group is explicitly managed without rules. Service-
# specific security groups belong to the EKS, RDS, ElastiCache, and EFS layers.
resource "aws_default_security_group" "this" {
  vpc_id = aws_vpc.this.id

  tags = {
    Name = "${local.name_prefix}-default-sg"
  }
}
