# Shared staging storage

The static PV uses the existing Terraform-managed EFS filesystem and access
point. Before applying the storage manifests, replace the two placeholders in
`persistentvolume-efs.yaml` with the Terraform outputs:

- `efs_file_system_id`
- `efs_access_point_id`

The later API and ingestion-worker Deployments must mount the
`insighthub-staging` PVC at `/data/staging`, preserving the existing
`STAGING_DIR=/data/staging` contract. This directory intentionally contains no
application workloads yet.

Before applying runtime manifests, replace the `REPLACE_WITH_*` placeholders
with Terraform outputs and immutable ECR image references. Generate the
database bootstrap ConfigMap directly from the authoritative schema without
committing a second SQL copy:

```text
kubectl -n insighthub create configmap insighthub-db-init \
  --from-file=init.sql=infra/db/init.sql \
  --dry-run=client -o yaml > /tmp/insighthub-db-init.yaml
```

Apply that generated ConfigMap before `database-init-job.yaml`. The RDS
SecretProviderClass synchronizes only the individual DB fields; no complete
DATABASE_URL or password is committed.

## Public web ingress

The AWS Load Balancer Controller uses the pinned chart values in
`aws-load-balancer-controller-values.yaml`. Before installation, replace the
cluster, region, VPC, and ServiceAccount role placeholders with Terraform
outputs. Install the chart version `1.8.3` with `serviceAccount.create=false`,
then apply `web-ingress.yaml`. The Ingress exposes only the `web` ClusterIP
Service using an internet-facing ALB with IP targets and HTTP `/` health checks.

The EKS API is private-only, so Helm and kubectl must run from a network path
that can reach the private cluster endpoint. This demo intentionally omits
ACM, DNS, and HTTPS; HTTP-only exposure is not production guidance.
