# Backend bootstrap is intentionally deferred until the separately managed S3
# state bucket exists. Keeping this block commented prevents a circular
# dependency and allows local validation with -backend=false.
#
# terraform {
#   backend "s3" {
#     bucket       = "<pre-created-state-bucket>"
#     key          = "insighthub/day3/terraform.tfstate"
#     region       = "<state-bucket-region>"
#     encrypt      = true
#     use_lockfile = true
#   }
# }
