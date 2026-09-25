# substack-k8s-mlops

A local MLOps platform on Kubernetes, installed with GitOps: one Argo CD ApplicationSet, synced in three waves.

| Component | Role |
|-----------|------|
| Argo CD | GitOps: installs and keeps everything below in sync with this repository |
| Traefik | Ingress, every UI at `http://<name>.localhost:8080` |
| cert-manager | Webhook certificates for KServe |
| CloudNativePG | Postgres for MLflow |
| SeaweedFS | S3-compatible storage for MLflow artifacts and datasets |
| MLflow | Experiment tracking and model registry |
| Kubeflow Pipelines | Training pipelines (v2 only: v1-only components removed) |
| KServe | Model serving (Standard mode, no Knative or Istio) |
| kube-prometheus-stack | Prometheus and Grafana |

> **Local use only.** Argo CD and Grafana have generated admin passwords, but MLflow and Kubeflow Pipelines run without authentication. Do not expose this setup outside your machine.

## Requirements

Tools on your machine:

| Tool | Used for | Tested with |
|------|----------|-------------|
| A local Kubernetes cluster | Runs the platform | Rancher Desktop 1.24 (k3s v1.36) |
| `kubectl` | Bootstrap and inspection | v1.37 |
| `helm` | Installs Argo CD (everything else comes through Argo CD) | v4.2 |
| `openssl` | Generates the secrets | any |
| `git` | Clone (or fork) this repository | any |

The cluster needs:

- at least 16 GB RAM and 8 CPUs
- a default StorageClass (all common local distributions have one)
- no other ingress controller: Traefik is installed by the platform itself

Only Rancher Desktop has been tested end to end. The kind and minikube commands below are the expected equivalents.

## Spin up

1. Create the cluster.

   ```bash
   # Rancher Desktop: resize the VM and disable the bundled Traefik
   rdctl set --virtual-machine.memory-in-gb 16 --virtual-machine.number-cpus 8
   rdctl set --kubernetes.options.traefik=false

   # or kind
   kind create cluster

   # or minikube
   minikube start --memory 16g --cpus 8
   ```

2. Install the platform.

   ```bash
   ./bootstrap/install.sh
   ```

   The script generates the secrets (never stored in Git), installs Argo CD with Helm and applies `platform/appset.yaml`. Argo CD takes over from there.

3. Watch the waves roll out (1, then 2, then 3) until all 11 applications are `Synced` and `Healthy`. The first run pulls several GB of images, so give it time.

   ```bash
   kubectl -n argocd get applications.argoproj.io -L wave -w
   ```

4. Open the UIs. The script prints the URLs and passwords at the end.

   | UI | URL | Login |
   |----|-----|-------|
   | Argo CD | http://argocd.localhost:8080 | `admin` / `kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' \| base64 -d` |
   | Grafana | http://grafana.localhost:8080 | `admin` / `kubectl -n monitoring get secret grafana-admin -o jsonpath='{.data.admin-password}' \| base64 -d` |
   | MLflow | http://mlflow.localhost:8080 | none |
   | Kubeflow Pipelines | http://kfp.localhost:8080 | none |

   Traefik is a `LoadBalancer` service on port 8080. Rancher Desktop and Docker Desktop publish it on `localhost` automatically. On kind or minikube, forward it first:

   ```bash
   kubectl -n traefik port-forward svc/traefik 8080:8080
   ```

## Tear down

Remove the platform but keep the cluster:

```bash
kubectl -n argocd delete applicationsets.argoproj.io platform   # apps go in reverse wave order: 3, 2, 1
helm -n argocd uninstall argocd
```

Namespaces and CRDs stay behind by design (Argo CD never deletes namespaces it created, and CRDs outlive their operators). For a clean slate, reset the cluster instead:

```bash
rdctl reset --k8s     # Rancher Desktop: deletes all workloads, keeps cached images
kind delete cluster   # kind
minikube delete       # minikube
```

To rebuild, run `./bootstrap/install.sh` again. On Rancher Desktop the images are still cached, so the second run is much faster.

## Layout

```
bootstrap/                        Argo CD install and generated secrets (the only imperative step)
platform/appset.yaml              ApplicationSet: one Application per component, synced in waves
platform/<component>/config.yaml  Wave, namespace and chart coordinates
platform/<component>/values.yaml  Chart values
platform/<component>/manifests/   Plain manifests for components without a chart (mlflow-db, kubeflow)
docs/problems-log.md              Every problem hit so far and the fix that shipped
```

| Wave | Components | Why |
|------|------------|-----|
| 1 | traefik, cert-manager, cloudnative-pg, monitoring, kserve-crd | CRDs, operators, ingress |
| 2 | seaweedfs, mlflow-db, kserve | mlflow-db needs CloudNativePG; kserve needs cert-manager and its CRDs |
| 3 | mlflow, kserve-runtimes, kubeflow | mlflow needs mlflow-db and SeaweedFS; runtimes need the KServe webhook |

Add a component: create `platform/<name>/config.yaml` (and `values.yaml`, or a `manifests/` folder), then push.

## Fork

Argo CD syncs from this repository. In a fork, point it at yours:

```bash
grep -rl raven4ever/substack-k8s-mlops platform | xargs sed -i 's#raven4ever/substack-k8s-mlops#<you>/<repo>#'
```
