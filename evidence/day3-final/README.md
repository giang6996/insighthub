# InsightHub Day 3 final evidence

This package preserves reviewable evidence for the deployed Day 3 demo before teardown. Raw command outputs are retained where practical; derived summaries are labeled as such. No credentials, tokens, kubeconfig, database passwords, secret values, or key material are included.

## 1. Final source

The implementation is anchored to commit `120843f337943d6fd8f55a7c3115d76b1bb3d129`. The source fingerprint and deployment artifact SHA are recorded in `source/final-source.txt` and the official verifier files under `source/`.

## 2. CI

GitHub run metadata and full logs are preserved for the starter run `35949605078`, IaC run `35949605102`, deploy run `35949774330`, and official verifier run `35953587899`.

## 3. CD

The deploy run completed successfully through the private SSM runner. The final SSM command ID was `681f3ea5-23e9-4efc-b3d8-be72ff4f12b8`. Final API, worker, and web image digests are recorded under `aws/ecr-final-images.json` and `kubernetes/images.txt`.

## 4. Official verifier

The official verifier passed in GitHub Actions. Its preserved result reports `runtime_verified=true` and `scope=partial-runtime-contract`; it also truthfully reports `specification_review_required=true` and `milestone_complete=false`. The verifier note states that deployment health is not attested by that verifier.

## 5. AWS infrastructure

Read-only snapshots cover EKS, the managed node group, the private deployment runner and SSM status, RDS, Redis, EFS, KMS, ECR, and the public ALB. The account is `596261186564` in `ap-southeast-1`.

## 6. Kubernetes runtime

The EKS API is private-only. Both `t3.small` nodes are Ready; API, ingestion-worker, and web deployments are `1/1`; pods have zero restarts; the database-init job is Complete; the staging PVC is Bound; and the AWS Load Balancer Controller is `2/2`.

## 7. Public smoke test

The public root returned HTTP 200, health returned `status=ok`, and the documents endpoint returned valid JSON. One unique fixture Markdown document was uploaded through the public upload proxy, reached `ready` with one chunk, answered a fixture chat request with the document as source/context, and was deleted by its exact ID. The final public document list is empty.

## 8. Security controls

See `security/security-summary.md` and the raw IAM, runner security-group, encryption, endpoint, and image evidence. No static AWS credentials were used by the CD workflow.

## 9. Known limitations

- The demo ALB is HTTP-only; there is no custom DNS name or ACM certificate.
- The official verifier covers only the partial runtime contract implemented by its bounded checks.
- Full project specification and reviewer evidence remain separate from the automated verifier.
- The infrastructure is intentionally temporary and should be torn down in a separate approved phase after documentation.
- The ECR release tag observed in AWS is `120843f33794` (the first twelve characters of the final commit); image identity is proven by digest.

## 10. Future teardown evidence

AWS resources remain running for documentation and review. Teardown is intentionally not included in this evidence operation. No Terraform destroy, Kubernetes deletion, or state-bucket deletion was performed.
