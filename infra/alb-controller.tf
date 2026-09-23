variable "aws_load_balancer_controller_chart_version" {
  description = "Pinned AWS Load Balancer Controller Helm chart version."
  type        = string
  default     = "1.8.3"
}

resource "aws_iam_role" "aws_load_balancer_controller" {
  name = "${local.name_prefix}-aws-load-balancer-controller"

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
          "${local.eks_oidc_issuer_host}:sub" = "system:serviceaccount:kube-system:aws-load-balancer-controller"
        }
      }
    }]
  })

  tags = {
    Name = "${local.name_prefix}-aws-load-balancer-controller-role"
  }
}

resource "aws_iam_role_policy" "aws_load_balancer_controller" {
  name   = "${local.name_prefix}-aws-load-balancer-controller"
  role   = aws_iam_role.aws_load_balancer_controller.id
  policy = file("${path.module}/policies/aws-load-balancer-controller-v2.8.3.json")
}
