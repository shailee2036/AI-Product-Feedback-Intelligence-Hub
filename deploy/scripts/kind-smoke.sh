#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

tag="${IMAGE_TAG:-$(git rev-parse HEAD)}"
if [[ -z "$tag" || "$tag" == "latest" ]]; then
  echo "Set IMAGE_TAG to an immutable commit SHA."
  exit 1
fi

image="feedback-hub-api:${tag}"
cluster="${KIND_CLUSTER_NAME:-feedback-hub-smoke}"
node_image="kindest/node:v1.37.0@sha256:a1ed56cfb0e7b93589bdf97c8cd566405a265939e3620fc4f5de89adff580ae5"
context="kind-${cluster}"

if ! docker image inspect "$image" >/dev/null 2>&1; then
  docker build --tag "$image" apps/api
fi

previous="$(kubectl config current-context 2>/dev/null || true)"

cleanup() {
  kind delete cluster --name "$cluster" >/dev/null 2>&1 || true
  if [[ -n "$previous" ]]; then
    kubectl config use-context "$previous" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

kind create cluster --name "$cluster" --image "$node_image"
kind load docker-image "$image" --name "$cluster"
kubectl --context "$context" create secret generic feedback-hub-api --from-literal=SMOKE=ok

if ! helm upgrade --install feedback-hub-api deploy/charts/api \
  --kube-context "$context" \
  --set "image.repository=feedback-hub-api" \
  --set "image.tag=${tag}" \
  --set image.pullPolicy=IfNotPresent \
  --wait \
  --timeout 180s; then
  kubectl --context "$context" describe pods --selector app.kubernetes.io/name=feedback-hub-api || true
  kubectl --context "$context" logs --selector app.kubernetes.io/name=feedback-hub-api --tail=50 || true
  exit 1
fi

check_health() {
  local path="$1"
  kubectl --context "$context" exec deploy/feedback-hub-api -- python -c 'import json,sys,urllib.request; body=json.load(urllib.request.urlopen(sys.argv[1], timeout=5)); assert body["status"]=="ok", body; print(body["status"])' "http://127.0.0.1:8000${path}"
}

check_health /health/live
check_health /health/ready
echo "smoke-ok"
