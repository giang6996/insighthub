data "aws_ssm_parameter" "al2023_x86_64" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

resource "aws_security_group" "deploy_runner" {
  name        = "${local.name_prefix}-deploy-runner"
  description = "Private deployment runner with HTTPS-only egress"
  vpc_id      = aws_vpc.this.id

  egress {
    description = "HTTPS for AWS APIs, SSM, packages, and GitHub via NAT"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${local.name_prefix}-deploy-runner-sg"
  }
}

resource "aws_vpc_security_group_ingress_rule" "eks_from_deploy_runner" {
  security_group_id            = aws_eks_cluster.this.vpc_config[0].cluster_security_group_id
  referenced_security_group_id = aws_security_group.deploy_runner.id
  from_port                    = 443
  to_port                      = 443
  ip_protocol                  = "tcp"
  description                  = "Private Kubernetes API access from deployment runner"
}

resource "aws_iam_role" "deploy_runner" {
  name = "${local.name_prefix}-deploy-runner"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = {
    Name = "${local.name_prefix}-deploy-runner-role"
  }
}

resource "aws_iam_role_policy_attachment" "deploy_runner_ssm" {
  role       = aws_iam_role.deploy_runner.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy" "deploy_runner_eks_describe" {
  name = "${local.name_prefix}-deploy-runner-eks-describe"
  role = aws_iam_role.deploy_runner.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["eks:DescribeCluster"]
      Resource = aws_eks_cluster.this.arn
    }]
  })
}

resource "aws_iam_instance_profile" "deploy_runner" {
  name = "${local.name_prefix}-deploy-runner"
  role = aws_iam_role.deploy_runner.name
}

resource "aws_eks_access_entry" "deploy_runner" {
  cluster_name      = aws_eks_cluster.this.name
  principal_arn     = aws_iam_role.deploy_runner.arn
  type              = "STANDARD"
  kubernetes_groups = []
}

resource "aws_eks_access_policy_association" "deploy_runner_admin" {
  cluster_name  = aws_eks_cluster.this.name
  principal_arn = aws_iam_role.deploy_runner.arn
  policy_arn    = "arn:${data.aws_partition.current.partition}:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"

  access_scope {
    type = "cluster"
  }

  depends_on = [
    aws_eks_access_entry.deploy_runner,
  ]
}

resource "aws_instance" "deploy_runner" {
  ami                         = data.aws_ssm_parameter.al2023_x86_64.value
  instance_type               = "t3.micro"
  subnet_id                   = aws_subnet.private[0].id
  vpc_security_group_ids      = [aws_security_group.deploy_runner.id]
  associate_public_ip_address = false
  monitoring                  = true
  ebs_optimized               = true
  iam_instance_profile        = aws_iam_instance_profile.deploy_runner.name

  metadata_options {
    http_tokens = "required"
  }

  root_block_device {
    encrypted   = true
    volume_type = "gp3"
    volume_size = 16
  }

  user_data = <<-EOF
    #!/bin/bash
    set -euxo pipefail
    dnf install -y git jq unzip
    if ! command -v aws >/dev/null 2>&1; then
      curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip
      unzip -q /tmp/awscliv2.zip -d /tmp
      /tmp/aws/install
    fi
    if ! command -v kubectl >/dev/null 2>&1; then
      curl --fail --silent --show-error --location "https://s3.us-west-2.amazonaws.com/amazon-eks/1.34.9/2026-07-05/bin/linux/amd64/kubectl" -o /tmp/kubectl
      curl --fail --silent --show-error --location "https://s3.us-west-2.amazonaws.com/amazon-eks/1.34.9/2026-07-05/bin/linux/amd64/kubectl.sha256" -o /tmp/kubectl.sha256
      (cd /tmp && sha256sum -c kubectl.sha256)
      install -m 0755 /tmp/kubectl /usr/local/bin/kubectl
    fi
    if ! command -v helm >/dev/null 2>&1; then
      curl --fail --silent --show-error --location "https://get.helm.sh/helm-v3.18.6-linux-amd64.tar.gz" -o /tmp/helm.tgz
      tar -xzf /tmp/helm.tgz -C /tmp
      install -m 0755 /tmp/linux-amd64/helm /usr/local/bin/helm
    fi
    systemctl enable --now amazon-ssm-agent || true
  EOF

  depends_on = [
    aws_iam_role_policy_attachment.deploy_runner_ssm,
    aws_iam_role_policy.deploy_runner_eks_describe,
  ]

  tags = {
    Name             = "${local.name_prefix}-deploy-runner"
    DeploymentTarget = "insighthub-day3"
  }
}
