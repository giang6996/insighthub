output "aws_load_balancer_controller_role_arn" {
  description = "IRSA role ARN for the AWS Load Balancer Controller."
  value       = aws_iam_role.aws_load_balancer_controller.arn
}
