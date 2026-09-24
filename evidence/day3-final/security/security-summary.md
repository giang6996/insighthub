# Day 3 security summary

Observed deployment facts:

- The EKS API endpoint is private-only: public access is false and private access is true.
- GitHub Actions uses the `insighthub-day3-github-deploy` OIDC role with the expected audience and immutable subject claim.
- The deploy role grants scoped ECR and SSM actions; it has no direct EKS permissions and no AdministratorAccess policy.
- The deployment runner has no public IP, is managed through SSM, and has no inbound SSH/admin rule.
- Runner egress is restricted to HTTPS; TCP 80 was not added for ALB validation.
- RDS is encrypted and private. Redis is private with transit and at-rest encryption enabled.
- EFS is encrypted and mounted through the EKS staging PVC.
- ECR repositories are immutable, scan-on-push enabled, and use KMS encryption.
- Kubernetes workloads use digest-pinned images matching the final ECR image digests.
- The public ALB is internet-facing and HTTP-only for this temporary demo; no custom DNS or ACM certificate was added.

These observations document the deployed demo controls and do not claim production readiness.
