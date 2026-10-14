#!/usr/bin/env bash
# Build the ML image straight into the local cluster's image store. No registry involved.
set -euo pipefail
cd "$(dirname "$0")"
IMAGE="wine-ml:$(cat VERSION)"

nerdctl --namespace k8s.io build -t "$IMAGE" .   # Rancher Desktop (containerd)
# docker build -t "$IMAGE" .                     # Docker Desktop, Rancher Desktop (moby)
# docker build -t "$IMAGE" . && kind load docker-image "$IMAGE"   # kind
# minikube image build -t "$IMAGE" .             # minikube
