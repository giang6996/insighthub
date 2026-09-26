# InsightHub: Windows From-Scratch Redeploy

This runbook covers local Docker/Minikube and the AWS/EKS infrastructure baseline. It assumes Docker Engine is active, the AWS CLI profile is test, and the default region is ap-southeast-1.

## 0. Verify identity and safety

~~~powershell
Set-Location D:\AWS\VTI\AI\insighthub
$env:AWS_PROFILE = 'test'
$env:AWS_REGION = 'ap-southeast-1'
$env:AWS_DEFAULT_REGION = $env:AWS_REGION
aws sts get-caller-identity --profile test --region ap-southeast-1
aws configure list --profile test
~~~

Stop if the returned account is not the intended sandbox account.

Before every local Kubernetes operation:

~~~powershell
$kubectl = (Get-Command kubectl -ErrorAction Stop).Source
$ctx = & $kubectl config current-context
if ($ctx -ne 'minikube') { throw "Refusing operation: expected minikube, got $ctx" }
~~~

## 1. Check Windows tools

~~~powershell
docker version
docker compose version
git --version
aws --version
terraform version
kubectl version --client
helm version
node --version
npm --version
py --list
~~~

Optional installation:

~~~powershell
winget install --id Amazon.AWSCLI --exact
winget install --id Hashicorp.Terraform --exact
winget install --id Kubernetes.kubectl --exact
winget install --id Helm.Helm --exact
winget install --id OpenJS.NodeJS --exact
~~~

The verifier requires Python 3.11 or newer.

## 2. Clean local Docker state

Preserve named volumes:

~~~powershell
docker compose down --remove-orphans
~~~

For a genuinely empty local database and Redis state, only after confirming local data may be discarded:

~~~powershell
docker compose down --volumes --remove-orphans
~~~

Do not use docker system prune or docker volume prune.

## 3. Configure local Day 5 variables

Use placeholders for local-only values. Never commit the kubeconfig or secrets.

~~~powershell
$env:INSIGHTHUB_MCP_KUBECONFIG = 'C:\Users\<user>\.kube\insighthub-mcp.kubeconfig'
$env:POSTGRES_EXPORTER_PASSWORD = '<local-only-password>'
$env:CHATOPS_REPLY_PATH = '/tmp/chatops-replies.jsonl'
$env:CHATOPS_AUDIT_PATH = '/tmp/chatops-audit.jsonl'
$env:CHATOPS_REPLY_FAIL_ONCE_PATH = ''
$env:PROMETHEUS_MCP_CLIENT_SCRIPT = ''
if (-not (Test-Path -LiteralPath $env:INSIGHTHUB_MCP_KUBECONFIG)) { throw 'MCP kubeconfig not found' }
~~~

## 4. Prepare Minikube MCP

~~~powershell
minikube status
minikube start --driver=docker
kubectl config use-context minikube
kubectl cluster-info
kubectl get nodes
~~~

Create the restricted read-only MCP identity:

~~~powershell
& .\k8s\mcp-setup-kubeconfig.ps1
if ((kubectl config current-context) -ne 'minikube') { throw 'Expected minikube' }
kubectl auth can-i get pods --namespace insighthub
kubectl auth can-i create pods --namespace insighthub
~~~

Expected authorization is read allowed and pod creation denied.

## 5. Build and start the local runtime

~~~powershell
docker compose config --quiet
docker compose up --build -d --wait
docker compose ps
Invoke-WebRequest -UseBasicParsing http://localhost:8000/healthz
Invoke-WebRequest -UseBasicParsing http://localhost:8000/readyz
Invoke-WebRequest -UseBasicParsing http://localhost:18080/healthz
Invoke-WebRequest -UseBasicParsing http://localhost:9090/-/ready
docker compose logs --no-color --tail=200 api chatops-bot chatops-worker redis postgres prometheus
~~~

The ChatOps bot is published on host port 18080 and listens on container port 8080.

## 6. Verify MCP clients

~~~powershell
docker compose exec -T chatops-worker node /opt/mcp-client/client.mjs
docker compose exec -T chatops-worker node /opt/mcp-client/prometheus.mjs
docker compose exec -T chatops-worker sh -c 'command -v kubectl || true'
node --check chatops-bot/mcp-client/client.mjs
node --check chatops-bot/mcp-client/prometheus.mjs
~~~

The worker must not contain a kubectl binary or use a shell fallback.

## 7. Run tests and quality checks

~~~powershell
py -3.11 -m pytest chatops-bot/tests -q
py -3.11 -m pytest tests/milestones/day5/test_day5.py -q
py -3.11 -m compileall -q chatops-bot/app tests/milestones/day5
git diff --check
Select-String -Path chatops-bot/requirements.txt -Pattern '^(arq|redis|fastapi|uvicorn)([<=>]|\s)'
~~~

Regenerate dependencies after editing requirements.in:

~~~powershell
$env:UV_CACHE_DIR = 'D:\AWS\VTI\AI\insighthub\.uv-cache'
uv pip compile chatops-bot/requirements.in --python-version 3.12 --universal --generate-hashes --no-emit-index-url --output-file chatops-bot/requirements.txt
~~~

## 8. Run the diagnostic Day 5 verifier

~~~powershell
py -3.11 scripts/verify.py day5 --evidence-dir evidence --bot-url http://localhost:18080 --json
~~~

This is not final evidence freezing and does not replace Slack review, screenshots, or screencast.

## 9. Validate controlled failure paths

Prometheus degradation:

~~~powershell
$env:PROMETHEUS_MCP_CLIENT_SCRIPT = '/missing'
docker compose up -d --force-recreate chatops-worker
# Send one valid locally signed health event to http://localhost:18080/slack/events.
$env:PROMETHEUS_MCP_CLIENT_SCRIPT = ''
docker compose up -d --force-recreate chatops-worker
~~~

Transient reply failure:

~~~powershell
$env:CHATOPS_REPLY_FAIL_ONCE_PATH = '/tmp/chatops-reply-fail-once.marker'
docker compose up -d --force-recreate chatops-worker
# Send one valid locally signed health event.
$env:CHATOPS_REPLY_FAIL_ONCE_PATH = ''
docker compose up -d --force-recreate chatops-worker
~~~

Permanent reply failure:

~~~powershell
$env:CHATOPS_REPLY_PATH = '/proc/1'
$env:CHATOPS_AUDIT_PATH = '/tmp/chatops-reply-failure-audit.jsonl'
docker compose up -d --force-recreate chatops-worker
# Send one valid locally signed health event and inspect the audit JSONL.
$env:CHATOPS_REPLY_PATH = '/tmp/chatops-replies.jsonl'
$env:CHATOPS_AUDIT_PATH = '/tmp/chatops-audit.jsonl'
docker compose up -d --force-recreate chatops-worker
~~~

Expected result: SLACK_REPLY_UNAVAILABLE is audited, no infinite retry loop occurs, and the worker remains running.

## 10. Recreate the AWS/EKS Terraform baseline

This section creates billable resources including networking, NAT, EKS, RDS, ElastiCache, EFS, KMS, ECR, IAM/OIDC, and a deployment runner. The repository contains an empty S3 backend block, so use the approved state bucket and key only.

~~~powershell
$env:AWS_PROFILE = 'test'
$env:AWS_REGION = 'ap-southeast-1'
aws sts get-caller-identity --profile test --region ap-southeast-1
Get-Content infra/backend.tf
terraform -chdir=infra init -input=false -backend-config='bucket=<approved-state-bucket>' -backend-config='key=insighthub/day3/terraform.tfstate' -backend-config='region=ap-southeast-1' -backend-config='use_lockfile=true'
terraform -chdir=infra fmt -check -recursive
terraform -chdir=infra validate -no-color
terraform -chdir=infra plan -input=false -out=day3.tfplan -var='aws_region=ap-southeast-1' -var='project_name=insighthub' -var='environment=day3' -var='github_repository=<owner/repository>'
terraform -chdir=infra show -no-color day3.tfplan
terraform -chdir=infra apply -input=false day3.tfplan
terraform -chdir=infra output
~~~

Review the plan and account before apply. Never invent backend details.

## 11. Reach private EKS correctly

The EKS API is private-only. Use these commands only from a network path that can reach the endpoint:

~~~powershell
$cluster = terraform -chdir=infra output -raw eks_cluster_name
aws eks update-kubeconfig --name $cluster --region $env:AWS_REGION --profile $env:AWS_PROFILE
kubectl config current-context
kubectl cluster-info
~~~

If the Windows host cannot reach the private endpoint, do not weaken endpoint security. Use the configured private deployment runner/SSM path or the repository deployment workflow:

~~~powershell
gh workflow run deploy.yml --repo <owner/repository> --ref main -f operation=preflight
gh run list --repo <owner/repository> --workflow deploy.yml --limit 5
gh workflow run deploy.yml --repo <owner/repository> --ref main -f operation=deploy
gh run watch --repo <owner/repository> <run-id>
~~~

The workflow builds immutable Linux/amd64 images, pushes ECR digests, and runs scripts/deploy_eks.sh on the private runner. Do not use :latest.

## 12. AWS/EKS post-deployment checks

Run only with the EKS context:

~~~powershell
kubectl get nodes
kubectl get namespace insighthub
kubectl get pods -n insighthub -o wide
kubectl get pvc -n insighthub
kubectl get ingress web -n insighthub
kubectl rollout status deployment/api -n insighthub --timeout=180s
kubectl rollout status deployment/ingestion-worker -n insighthub --timeout=180s
kubectl rollout status deployment/web -n insighthub --timeout=180s
kubectl get events -n insighthub --sort-by=.lastTimestamp
~~~

Return to Minikube before Day 5 validation:

~~~powershell
kubectl config use-context minikube
if ((kubectl config current-context) -ne 'minikube') { throw 'Day 5 requires minikube' }
~~~

## 13. Full AWS teardown after the lab

First remove Kubernetes resources that can create AWS load balancers. Then inspect the destroy plan:

~~~powershell
terraform -chdir=infra plan -destroy -input=false -out=teardown.tfplan
terraform -chdir=infra show -no-color teardown.tfplan
~~~

Only after confirming account, region, workspace, and plan:

~~~powershell
terraform -chdir=infra apply -input=false teardown.tfplan
terraform -chdir=infra state list
aws eks list-clusters --region $env:AWS_REGION --profile $env:AWS_PROFILE
~~~

Do not run account-wide deletion commands, ambiguous name-based deletion scripts, or terraform destroy -auto-approve without a reviewed plan.

## 14. Final cleanup and secret scan

~~~powershell
docker compose down --remove-orphans
docker compose ps
$logs = docker compose logs --no-color chatops-bot chatops-worker
if ($logs -match 'xoxb-|AWS_SECRET_ACCESS_KEY|certificate-authority-data|raw_body|postgres_password') { throw 'Sensitive pattern found in logs' }
Write-Output 'secret-scan=clean'
~~~

Never commit .env files, kubeconfigs, Terraform state or plan files, AWS credentials, Slack tokens, signing secrets, or raw Slack request bodies.

