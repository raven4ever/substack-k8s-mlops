#!/usr/bin/env bash
# One-time bootstrap: secrets + Argo CD + platform ApplicationSet. Everything else is synced from Git.
set -euo pipefail
cd "$(dirname "$0")"

ARGOCD_CHART_VERSION=10.9.2
S3_CONSUMERS="mlflow" # namespaces that get the s3-credentials secret

kubectl get nodes >/dev/null # fail fast when no cluster is reachable

ensure_ns() { kubectl create namespace "$1" --dry-run=client -o yaml | kubectl apply -f - >/dev/null; }

# Secrets never live in Git. Generated once, kept on re-runs.
# ponytail: plain Secrets from a script; use Sealed Secrets or External Secrets on a shared cluster.
ensure_ns seaweedfs
if ! kubectl -n seaweedfs get secret seaweedfs-s3-config >/dev/null 2>&1; then
  key=$(openssl rand -hex 10)
  secret=$(openssl rand -hex 20)
  kubectl -n seaweedfs create secret generic seaweedfs-s3-config \
    --from-literal=AWS_ACCESS_KEY_ID="$key" \
    --from-literal=AWS_SECRET_ACCESS_KEY="$secret" \
    --from-literal=seaweedfs_s3_config="{\"identities\":[{\"name\":\"admin\",\"credentials\":[{\"accessKey\":\"$key\",\"secretKey\":\"$secret\"}],\"actions\":[\"Admin\",\"Read\",\"Write\",\"List\",\"Tagging\"]}]}"
fi
get_s3() { kubectl -n seaweedfs get secret seaweedfs-s3-config -o jsonpath="{.data.$1}" | base64 -d; }
for ns in $S3_CONSUMERS; do
  ensure_ns "$ns"
  kubectl -n "$ns" create secret generic s3-credentials \
    --from-literal=AWS_ACCESS_KEY_ID="$(get_s3 AWS_ACCESS_KEY_ID)" \
    --from-literal=AWS_SECRET_ACCESS_KEY="$(get_s3 AWS_SECRET_ACCESS_KEY)" \
    --dry-run=client -o yaml | kubectl apply -f - >/dev/null
done

ensure_ns monitoring
if ! kubectl -n monitoring get secret grafana-admin >/dev/null 2>&1; then
  kubectl -n monitoring create secret generic grafana-admin \
    --from-literal=admin-user=admin --from-literal=admin-password="$(openssl rand -hex 12)"
fi

helm upgrade --install argocd argo-cd --repo https://argoproj.github.io/argo-helm \
  --version "$ARGOCD_CHART_VERSION" -n argocd --create-namespace -f argocd-values.yaml --wait >/dev/null
kubectl apply -f ../platform/appset.yaml

secret() { kubectl -n "$1" get secret "$2" -o jsonpath="{.data.$3}" | base64 -d; }
cat <<EOF

Argo CD is syncing the platform. Watch it: kubectl -n argocd get applications.argoproj.io -w
  Argo CD   http://argocd.localhost:8080   admin / $(secret argocd argocd-initial-admin-secret password)
  Grafana   http://grafana.localhost:8080  admin / $(secret monitoring grafana-admin admin-password)
  MLflow    http://mlflow.localhost:8080
  KFP       http://kfp.localhost:8080
EOF
