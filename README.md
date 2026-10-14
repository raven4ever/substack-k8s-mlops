# substack-k8s-mlops

A local MLOps platform on Kubernetes, installed with GitOps (one Argo CD ApplicationSet, synced in waves), and a model that lives on it: a wine quality regressor that is trained in a pipeline, served, monitored and retrained on its own when its data drifts.

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
| DVC | Data versioning: `data/wine.csv` lives in SeaweedFS, Git keeps the pointer |
| Evidently | Data drift report behind the retraining decision |

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
| `nerdctl` or `docker` | Builds the ML image into the cluster (`ml/build.sh`) | nerdctl 2 (Rancher Desktop) |
| `dvc` with S3 support | Pushes the dataset to SeaweedFS | 3.67 (`uv tool install "dvc[s3]"`) |
| `uv` | Runs the pipeline submitter without a local virtualenv | any |
| `python3`, `curl`, `unzip` | Traffic generator, data download | any |

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

3. Watch the waves roll out (1, then 2, 3 and 4) until all 12 applications are `Synced` and `Healthy`. The first run pulls several GB of images, so give it time.

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

## Train the dragon

1. Build the ML image straight into the cluster (pipeline steps and the drift monitor all use it).

   ```bash
   ./ml/build.sh
   ```

2. Put both data versions into SeaweedFS. Git already points to them: tag `data-v1` is 1,599 red wines, `main` (tag `data-v2`) adds 4,898 white wines.

   ```bash
   ./ml/seed-data.sh
   ```

3. Train the first model on the red wines only.

   ```bash
   uv run --no-project --with kfp==2.17.0 --with kfp-kubernetes==2.17.0 python ml/pipeline.py --data-rev data-v1
   ```

   The run (load-data, validate-data, train, promote) shows up in Kubeflow Pipelines. The model lands in MLflow as version 1 of `wine-quality` with the alias `champion`, and the promote step deploys it with KServe.

4. Ask it something.

   ```bash
   curl -s -H 'Content-Type: application/json' \
     -d '{"instances": [[7.4, 0.7, 0, 1.9, 0.076, 11, 34, 0.9978, 3.51, 0.56, 9.4]]}' \
     http://wine-quality-wine.localhost:8080/v1/models/wine-quality:predict
   ```

5. Keep it busy and watch the "Wine quality model" dashboard in Grafana (requests, errors, latency, predictions per pod).

   ```bash
   python3 ml/traffic.py data/wine.csv
   ```

6. Let it retrain itself. The champion was trained on `data-v1`, but `main` has the white wines. Within 10 minutes the `drift-monitor` CronJob compares both datasets with Evidently, logs the report to the MLflow experiment `wine-quality-monitoring`, and submits a training run on the new data. The new model is promoted only if it beats the champion on the same test split, then KServe rolls to it. To skip the wait:

   ```bash
   kubectl -n wine create job drift-now --from=cronjob/drift-monitor
   ```

New data of your own: change `data/wine.csv`, then `dvc add data/wine.csv && dvc push`, commit the `.dvc` file and push. New ML code: bump `ml/VERSION` and the CronJob image in `apps/wine/manifests/drift-monitor.yaml`, then `./ml/build.sh`.

## Tear down

Remove the platform but keep the cluster:

```bash
kubectl -n argocd delete applicationsets.argoproj.io platform   # apps go in reverse wave order: 4, 3, 2, 1
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
apps/wine/                        The model's tenant: serving account, deploy RBAC, drift CronJob, dashboard
ml/                               Pipeline, drift monitor, traffic generator, image build and data seeding
data/wine.csv.dvc                 DVC pointer to the dataset in SeaweedFS
docs/problems-log.md              Every problem hit so far and the fix that shipped
```

| Wave | Components | Why |
|------|------------|-----|
| 1 | cert-manager, cloudnative-pg, monitoring, kserve-crd | CRDs and operators |
| 2 | traefik, seaweedfs, mlflow-db, kserve | Traefik's ServiceMonitor needs the monitoring CRDs; mlflow-db needs CloudNativePG; kserve needs cert-manager and its CRDs |
| 3 | mlflow, kserve-runtimes, kubeflow | mlflow needs mlflow-db and SeaweedFS; runtimes need the KServe webhook |
| 4 | wine | The tenant: needs the whole platform |

Add a component: create `platform/<name>/config.yaml` (and `values.yaml`, or a `manifests/` folder), then push. Tenants go under `apps/<name>/` the same way.

The InferenceService is the one thing Argo CD does not own: the pipeline's promote step creates and rolls it. Git owns the platform, the model registry owns which model is the champion.

## Fork

Argo CD syncs from this repository. In a fork, point it at yours:

```bash
grep -rl raven4ever/substack-k8s-mlops platform ml | xargs sed -i 's#raven4ever/substack-k8s-mlops#<you>/<repo>#'
```
