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
