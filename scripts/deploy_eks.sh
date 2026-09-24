#!/usr/bin/env bash
set -euo pipefail

: "${DEPLOY_SHA:?DEPLOY_SHA is required}"
: "${API_IMAGE:?API_IMAGE is required}"
: "${WORKER_IMAGE:?WORKER_IMAGE is required}"
: "${WEB_IMAGE:?WEB_IMAGE is required}"

export AWS_REGION="${AWS_REGION:-ap-southeast-1}"
export KUBECONFIG="/root/.kube/config"

image_re='^[0-9]{12}\.dkr\.ecr\.[a-z0-9-]+\.amazonaws\.com/[a-zA-Z0-9._/-]+@sha256:[0-9a-f]{64}$'
for image in "$API_IMAGE" "$WORKER_IMAGE" "$WEB_IMAGE"; do
  [[ "$image" =~ $image_re ]] || { echo "invalid digest-pinned image: $image" >&2; exit 2; }
done

kubectl cluster-info >/dev/null
kubectl get namespace insighthub >/dev/null
[[ "$(kubectl get pvc insighthub-staging -n insighthub -o jsonpath='{.status.phase}')" == "Bound" ]]
kubectl get secret insighthub-rds-fields -n insighthub >/dev/null
[[ "$(kubectl get job database-init -n insighthub -o jsonpath='{.status.succeeded}')" == "1" ]]
kubectl get deployment api ingestion-worker web -n insighthub >/dev/null
kubectl rollout status deployment/aws-load-balancer-controller -n kube-system --timeout=60s
kubectl get ingress web -n insighthub >/dev/null

rendered_dir="$(mktemp -d)"
api_pf=""
web_pf=""
cleanup() {
  if [[ -n "${web_pf:-}" ]]; then
    kill "$web_pf" 2>/dev/null || true
  fi
  if [[ -n "${api_pf:-}" ]]; then
    kill "$api_pf" 2>/dev/null || true
  fi
  rm -rf "$rendered_dir"
}
trap cleanup EXIT
sed "s|REPLACE_WITH_IMMUTABLE_API_ECR_IMAGE|$API_IMAGE|" deploy/api-deployment.yaml > "$rendered_dir/api.yaml"
sed "s|REPLACE_WITH_IMMUTABLE_WORKER_ECR_IMAGE|$WORKER_IMAGE|" deploy/worker-deployment.yaml > "$rendered_dir/worker.yaml"
sed "s|REPLACE_WITH_IMMUTABLE_WEB_ECR_IMAGE|$WEB_IMAGE|" deploy/web-deployment.yaml > "$rendered_dir/web.yaml"

for manifest in "$rendered_dir"/*.yaml; do
  ! grep -q 'REPLACE_WITH_' "$manifest"
done

rollout_or_report() {
  local deployment="$1"
  if ! kubectl apply -f "$2" || ! kubectl rollout status "deployment/$deployment" -n insighthub --timeout=180s; then
    kubectl get deployment "$deployment" -n insighthub -o wide || true
    kubectl get pods -n insighthub -l "app=$([[ "$deployment" == ingestion-worker ]] && echo ingestion-worker || echo "$deployment")" -o wide || true
    kubectl get events -n insighthub --sort-by=.lastTimestamp | tail -40 || true
    kubectl logs "deployment/$deployment" -n insighthub --tail=100 || true
    return 1
  fi
}

rollout_or_report api "$rendered_dir/api.yaml"
api_pf_log="$rendered_dir/api-port-forward.log"
kubectl -n insighthub port-forward svc/api 18000:8000 >"$api_pf_log" 2>&1 & api_pf=$!
sleep 3
healthz="$(curl -fsS http://127.0.0.1:18000/healthz)"
readyz="$(curl -fsS http://127.0.0.1:18000/readyz)"
kill "$api_pf" 2>/dev/null || true
api_pf=""
grep -q '"status":"ok"' <<<"$healthz"
grep -q '"status":"ready"' <<<"$readyz"
grep -q '"db":true' <<<"$readyz"

rollout_or_report ingestion-worker "$rendered_dir/worker.yaml"
rollout_or_report web "$rendered_dir/web.yaml"

web_pf_log="$rendered_dir/web-port-forward.log"
kubectl -n insighthub port-forward svc/web 18001:3000 >"$web_pf_log" 2>&1 & web_pf=$!
sleep 3
web_root="$(curl -fsS http://127.0.0.1:18001/)"
web_health="$(curl -fsS http://127.0.0.1:18001/api/health)"
web_documents="$(curl -fsS http://127.0.0.1:18001/api/documents)"
kill "$web_pf" 2>/dev/null || true
web_pf=""
[[ -n "$web_root" ]]
grep -q '"status":"ok"' <<<"$web_health"
jq -e . <<<"$web_documents" >/dev/null

ingress_host="$(kubectl get ingress web -n insighthub -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')"
[[ "$ingress_host" =~ ^[a-z0-9][a-z0-9.-]*\.elb\.amazonaws\.com$ ]]
printf 'DEPLOY_SHA=%s\nHEALTHZ=%s\nREADYZ=%s\nWEB_INTERNAL_HEALTH=%s\nWEB_INTERNAL_DOCUMENTS=%s\nINGRESS_HOST=%s\n' \
  "$DEPLOY_SHA" "$healthz" "$readyz" "$web_health" "$web_documents" "$ingress_host"
