# Problems log

Problems hit while building, deploying, destroying and redeploying the platform, and how each was fixed.
Source material for the articles.

| # | Phase | Problem | Fix |
|---|-------|---------|-----|
| 1 | Cluster | Rancher Desktop default VM (6 GB / 2 CPU) is too small for the stack. | `rdctl set --virtual-machine.memory-in-gb 16 --virtual-machine.number-cpus 8` |
| 2 | Ingress | On Linux, Rancher Desktop cannot forward host ports 80/443 (`net.ipv4.ip_unprivileged_port_start=1024`), so `http://localhost` is unreachable. | Expose Traefik on 8080/8443. No sudo, same URLs on every local cluster. |
| 3 | Ingress | The bundled Traefik exists only on k3s; kind, minikube and Docker Desktop have none. | Disable it (`rdctl set --kubernetes.options.traefik=false`) and install Traefik through Argo CD on every provider. ingress-nginx was retired in March 2026, so Traefik is the default choice. |
| 4 | Storage | MinIO stopped publishing community images in 2025. | SeaweedFS as S3-compatible store (all-in-one mode, one pod). |
| 5 | Database | Bitnami moved free images to `bitnamilegacy` (no updates) in 2025; the MLflow chart's built-in Postgres still uses it. | CloudNativePG operator, one `Cluster` resource for MLflow. |
| 6 | KFP | KFP 2.17 standalone ships its own SeaweedFS and MySQL. | Kept them for pipeline internals; the shared SeaweedFS serves MLflow and DVC only. |
| 7 | KServe | KServe charts are published only as OCI artifacts. | Register `ghcr.io/kserve/charts` in Argo CD with `enableOCI: "true"`. |
| 8 | KServe | `RawDeployment` mode is deprecated and renamed `Standard` (v0.20). | `deploymentMode: Standard`: plain Deployment + Ingress, no Knative or Istio. |
| 9 | KFP | Argo CD timed out generating KFP manifests (`DeadlineExceeded`). A git source on `kubeflow/pipelines` is slow to fetch, and the KFP kustomize bases pull more remote bases (argo-workflows) during the build; `kubectl kustomize` hit its 27s git timeout too. | Vendor the rendered manifests (`platform/manifests/kfp*/upstream.yaml`, regenerate command in the file header). Sync no longer depends on GitHub fetch speed. |
| 10 | MLflow | Deadlock: the CNPG `Cluster` failed because the CNPG webhook had no endpoints yet, while Argo CD kept waiting for the MLflow Deployment to become healthy. MLflow init container waited for secret `mlflow-db-app`, which only exists once the database is created. | `argocd.argoproj.io/sync-wave: "-1"` on the `Cluster` so the database is applied (and retried) before MLflow. Stuck operation ended by setting `status.operationState.phase: Terminating`. |
| 11 | KServe | First sync failed: `no endpoints available for service "kserve-webhook-server-service"` while the controller was still starting. | Resolved by the Application `retry` policy, no change needed. |
| 12 | All | First install is slow: ~40 images pulled in parallel, some took 5–10 minutes (Prometheus 9.5 min). Pods sit in `ContainerCreating` / `PodInitializing` and look broken. | Patience; check `kubectl get events` for `Pulling` before debugging. Recreating the apps (cascade delete, root app recreates them) keeps cached images. |
