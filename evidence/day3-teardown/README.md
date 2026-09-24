# InsightHub Day 3 teardown evidence

This package records the authorized teardown of the temporary InsightHub Day 3 AWS environment.

- Teardown timestamp: 2026-09-24T13:10:54.9606494+07:00
- AWS account: `596261186564`
- AWS region: `ap-southeast-1`
- AWS profile: `personal`
- Permanent evidence commit: `0fd92791eed38e6cd29e75190426355720c5cee9`
- Final implementation commit: `120843f337943d6fd8f55a7c3115d76b1bb3d129`
- Terraform destroy plan: `0 added, 0 changed, 71 destroyed`
- Terraform apply: successful, `0 added, 0 changed, 71 destroyed`
- Final Terraform state: empty

## Ordered cleanup

1. Verified the clean `main` worktree, permanent evidence commit, and AWS identity.
2. Initialized Terraform against the existing S3 backend and captured state/output evidence.
3. Inspected and deleted only the `insighthub/web` Kubernetes ingress through the private SSM runner.
4. Confirmed the ALB was gone, then deleted the `insighthub` namespace and confirmed it absent.
5. Emptied only the three Day 3 ECR repositories, including their untagged manifest-list child digests.
6. Reviewed and applied the exact destroy plan from `terraform/teardown.tfplan`.
7. Removed the clearly Day 3-only EKS CloudWatch log group `/aws/eks/insighthub-day3/cluster`.

## Intentional survivor

The Terraform S3 backend was not destroyed. Bucket `insighthub-tfstate-596261186564-ap-southeast-1` remains enabled and the `insighthub/day3/` state prefix retains the current empty state plus historical versions and lock history. No state objects were deleted.

The two Terraform-managed customer KMS keys are in `PendingDeletion` and are recorded in `post-destroy/kms-data-services.json` and `post-destroy/kms-eks-secrets.json`:

- data services key `602e16f8-3482-4834-a02e-f374ffeaca1a`, scheduled for 2026-10-01 05:56:04 UTC
- EKS secrets key `f42cf14a-039a-4f1e-ac94-c2ae52f6f4c8`, scheduled for 2026-10-01 06:03:00 UTC

Their Day 3 aliases are absent. This pending-deletion state is the expected AWS KMS lifecycle after Terraform key deletion.

## Audit result

The Day 3 EKS cluster/node group, private deployment runner, RDS, Redis, EFS, ECR repositories, ALB/target group, VPC/network resources, IAM roles/OIDC providers, project EBS artifacts, and Day 3 log group are absent. The runner is terminated. No unexpected resource or Terraform failure was observed.

Evidence files are enumerated with SHA-256 and byte size in `MANIFEST.json`. The package was scanned for credentials and secrets before commit; no actual secret material was retained.
