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

kubectl --context "$context" create secret generic feedback-hub-litellm \
  --from-literal=GROQ_API_KEY=smoke-not-a-key \
  --from-literal=LITELLM_MASTER_KEY="sk-smoke-$(openssl rand -hex 16)"

if ! helm upgrade --install feedback-hub-litellm deploy/charts/litellm \
  --kube-context "$context" \
  --wait \
  --timeout 300s; then
  kubectl --context "$context" describe pods --selector app.kubernetes.io/name=feedback-hub-litellm || true
  kubectl --context "$context" logs --selector app.kubernetes.io/name=feedback-hub-litellm --tail=50 || true
  exit 1
fi

proxy_status() {
  local path="$1"
  kubectl --context "$context" exec deploy/feedback-hub-api -- python -c 'import sys,urllib.error,urllib.request
try:
    print(urllib.request.urlopen(sys.argv[1], timeout=5).status)
except urllib.error.HTTPError as error:
    print(error.code)' "http://feedback-hub-litellm:4000${path}"
}

[[ "$(proxy_status /health/readiness)" == "200" ]] || { echo "LiteLLM is not ready."; exit 1; }
[[ "$(proxy_status /v1/models)" == "401" ]] || { echo "LiteLLM accepted a request without the master key."; exit 1; }

kubectl --context "$context" create secret generic feedback-hub-grafana \
  --from-literal=admin-user=admin \
  --from-literal=admin-password="$(openssl rand -hex 16)"

if ! helm upgrade --install feedback-hub-monitoring deploy/charts/monitoring \
  --kube-context "$context" \
  --wait \
  --timeout 300s; then
  kubectl --context "$context" describe pods --selector app.kubernetes.io/part-of=feedback-hub-monitoring || true
  kubectl --context "$context" logs --selector app.kubernetes.io/part-of=feedback-hub-monitoring --tail=50 || true
  exit 1
fi

prometheus() {
  kubectl --context "$context" exec deploy/feedback-hub-prometheus -- wget -qO- "http://127.0.0.1:9090$1"
}

scraped=""
for _ in $(seq 1 24); do
  if prometheus '/api/v1/query?query=up%7Bjob%3D%22feedback-hub-api%22%7D%3D%3D1' | grep -q '"job":"feedback-hub-api"'; then
    scraped="yes"
    break
  fi
  sleep 5
done
[[ -n "$scraped" ]] || { echo "Prometheus did not scrape the API."; exit 1; }

rules="$(prometheus /api/v1/rules)"
[[ "$(grep -o '"health":"ok"' <<<"$rules" | wc -l)" -eq 4 ]] || { echo "Prometheus did not load the alert rules."; exit 1; }

grafana() {
  kubectl --context "$context" exec deploy/feedback-hub-grafana -- sh -c \
    'curl -fsS -u "$GF_SECURITY_ADMIN_USER:$GF_SECURITY_ADMIN_PASSWORD" "http://127.0.0.1:3000$1"' _ "$1"
}

grafana /api/datasources/uid/prometheus/health | grep -q '"status":"OK"' || { echo "Grafana cannot query Prometheus."; exit 1; }
grafana /api/dashboards/uid/feedback-hub-api | grep -q '"title":"API service health"' || { echo "Grafana did not load the dashboard."; exit 1; }
echo "smoke-ok"
