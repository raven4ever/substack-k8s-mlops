# substack-k8s-mlops

A local MLOps platform on Kubernetes, installed with GitOps (Argo CD, app of apps).

| Component | Role |
|-----------|------|
| Traefik | Ingress, every UI at `http://<name>.localhost:8080` |
| cert-manager | Webhook certificates for KServe |
| CloudNativePG | Postgres for MLflow |
| SeaweedFS | S3-compatible storage for MLflow artifacts and DVC data |
| MLflow | Experiment tracking and model registry |
| Kubeflow Pipelines | Training pipelines |
| KServe | Model serving (Standard mode, no Knative or Istio) |
| kube-prometheus-stack | Prometheus and Grafana |

## Requirements

- A local Kubernetes cluster with at least 16 GB RAM and 8 CPUs, and a default StorageClass
- `kubectl`, `helm`, `openssl`
- No other ingress controller. On Rancher Desktop: `rdctl set --kubernetes.options.traefik=false`

## Install

```bash
./bootstrap/install.sh
kubectl -n argocd get applications -w   # wait until all are Synced / Healthy
```

The script prints the URLs and generated passwords.

Traefik is a `LoadBalancer` service on port 8080. Rancher Desktop and Docker Desktop publish it on `localhost` automatically. On kind or minikube, run:

```bash
kubectl -n traefik port-forward svc/traefik 8080:8080
```

## Fork

Argo CD syncs from this repository. In a fork, replace the repository URL:

```bash
grep -rl raven4ever/substack-k8s-mlops platform | xargs sed -i 's#raven4ever/substack-k8s-mlops#<you>/<repo>#'
```

## Layout

```
bootstrap/          Argo CD install and generated secrets (the only imperative step)
platform/root.yaml  Root application
platform/apps/      One Argo CD Application per component
platform/manifests/ Extra manifests (MLflow database, KFP ingress)
docs/               Problems log
```
