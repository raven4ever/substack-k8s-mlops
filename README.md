# substack-k8s-mlops

A local MLOps platform on Kubernetes, installed with GitOps (one Argo CD ApplicationSet, synced in waves).

| Component | Role |
|-----------|------|
| Traefik | Ingress, every UI at `http://<name>.localhost:8080` |
| cert-manager | Webhook certificates for KServe |
| CloudNativePG | Postgres for MLflow |
| SeaweedFS | S3-compatible storage for MLflow artifacts and DVC data |
| MLflow | Experiment tracking and model registry |
| Kubeflow Pipelines | Training pipelines (v2 only: v1-only components removed) |
| KServe | Model serving (Standard mode, no Knative or Istio) |
| kube-prometheus-stack | Prometheus and Grafana |

## Requirements

- A local Kubernetes cluster with at least 16 GB RAM and 8 CPUs, and a default StorageClass
- `kubectl`, `helm`, `openssl`
- No other ingress controller. On Rancher Desktop: `rdctl set --kubernetes.options.traefik=false`

## Install

```bash
./bootstrap/install.sh
kubectl -n argocd get applications.argoproj.io -w   # waves 1 -> 2 -> 3, until all are Synced / Healthy
```

The script prints the URLs and generated passwords.

> **Local use only.** Argo CD and Grafana have generated admin passwords, but MLflow and Kubeflow Pipelines run without authentication. Do not expose this setup outside your machine.

Traefik is a `LoadBalancer` service on port 8080. Rancher Desktop and Docker Desktop publish it on `localhost` automatically. On kind or minikube, run:

```bash
kubectl -n traefik port-forward svc/traefik 8080:8080
```

## Destroy

Deleting the ApplicationSet removes the apps in reverse wave order (3, 2, 1), but namespaces and CRDs stay by design. For a clean slate, reset the local cluster:

```bash
rdctl reset --k8s     # Rancher Desktop, keeps cached images
kind delete cluster   # kind
minikube delete       # minikube
```

## Fork

Argo CD syncs from this repository. In a fork, replace the repository URL:

```bash
grep -rl raven4ever/substack-k8s-mlops platform | xargs sed -i 's#raven4ever/substack-k8s-mlops#<you>/<repo>#'
```

## Layout

```
bootstrap/                      Argo CD install and generated secrets (the only imperative step)
platform/appset.yaml            ApplicationSet: one Application per component, synced in waves
platform/<component>/config.yaml  Wave, namespace and chart coordinates
platform/<component>/values.yaml  Chart values
platform/<component>/manifests/   Plain manifests for components without a chart (mlflow-db, kubeflow)
docs/                           Problems log
```

| Wave | Components | Why |
|------|------------|-----|
| 1 | traefik, cert-manager, cloudnative-pg, monitoring, kserve-crd | CRDs, operators, ingress |
| 2 | seaweedfs, mlflow-db, kserve | mlflow-db needs CloudNativePG; kserve needs cert-manager and its CRDs |
| 3 | mlflow, kserve-runtimes, kubeflow | mlflow needs mlflow-db and SeaweedFS; runtimes need the KServe webhook |

Add a component: create `platform/<name>/config.yaml` (+ `values.yaml`) and push.
