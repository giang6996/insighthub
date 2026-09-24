locals {
  ecr_repositories = toset(["web", "api", "ingestion-worker"])
}

resource "aws_ecr_repository" "this" {
  for_each = local.ecr_repositories

  name                 = "${local.name_prefix}-${each.value}"
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "KMS"
    kms_key         = aws_kms_key.data_services.arn
  }

  tags = {
    Name = "${local.name_prefix}-${each.value}"
  }
}

resource "aws_ecr_lifecycle_policy" "this" {
  for_each = local.ecr_repositories

  repository = aws_ecr_repository.this[each.value].name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep the 10 most recent images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 10
      }
      action = {
        type = "expire"
      }
    }]
  })
}
