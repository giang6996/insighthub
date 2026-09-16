$ErrorActionPreference = "Stop"

$ContextName = "insighthub-mcp"
$ClusterName = "minikube-mcp"

$KubeconfigPath = Join-Path $HOME ".kube\insighthub-mcp.kubeconfig"

$NamespaceFilePath = Join-Path $PSScriptRoot "namespace.yaml"
$ServiceAccountFilePath = Join-Path $PSScriptRoot "serviceaccount.yaml"
$RbacPath = Join-Path $PSScriptRoot "mcp-readonly-rbac.yaml"

# Cluster check: default to minikube

$currentContext = kubectl config current-context

if ($currentContext -ne "minikube") {
    throw "Safety check failed: current kubectl context is '$currentContext', expected 'minikube'."
}

Write-Host "Current context verified: minikube"

# 1. Apply namespace and service account config

kubectl apply -f $NamespaceFilePath
kubectl apply -f $ServiceAccountFilePath

$Namespace = kubectl get -f $NamespaceFilePath`
    -o jsonpath='{.metadata.name}'

$ServiceAccount = kubectl get -f $ServiceAccountFilePath `
    -o jsonpath='{.metadata.name}'

# 2. Apply MCP RBAC configuration

kubectl apply -f $RbacPath

# 3. Generate short-lived ServiceAccount token

$token = kubectl create token $ServiceAccount `
    -n $Namespace `
    --duration=8h

if (-not $token) {
    throw "Failed to generate ServiceAccount token."
}

# 4. Read current Minikube API endpoint

$server = kubectl config view `
    --minify `
    -o jsonpath='{.clusters[0].cluster.server}'

$caPath = Join-Path $HOME ".minikube\ca.crt"

# 5. Rebuild dedicated MCP kubeconfig

if (Test-Path $KubeconfigPath) {
    Remove-Item $KubeconfigPath
}

kubectl config `
    --kubeconfig="$KubeconfigPath" `
    set-cluster $ClusterName `
    --server="$server" `
    --certificate-authority="$caPath" `
    --embed-certs=true

kubectl config `
    --kubeconfig="$KubeconfigPath" `
    set-credentials $ServiceAccount `
    --token="$token"

kubectl config `
    --kubeconfig="$KubeconfigPath" `
    set-context $ContextName `
    --cluster=$ClusterName `
    --user=$ServiceAccount `
    --namespace=$Namespace

kubectl config `
    --kubeconfig="$KubeconfigPath" `
    use-context $ContextName

# 6. Verify the generated identity

Write-Host ""
Write-Host "Testing MCP ServiceAccount permissions..."

kubectl `
    --kubeconfig="$KubeconfigPath" `
    auth can-i get pods

kubectl `
    --kubeconfig="$KubeconfigPath" `
    auth can-i delete pods

Write-Host ""
Write-Host "MCP kubeconfig created:"
Write-Host $KubeconfigPath