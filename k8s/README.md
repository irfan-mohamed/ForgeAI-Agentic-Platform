# ForgeAI — Kubernetes Deployment Guide

## Directory layout

```
k8s/
├── namespace.yaml        Kubernetes namespace (forgeai)
├── secrets.yaml          Secret template — fill in REPLACE_ME before applying
├── postgres.yaml         PostgreSQL Deployment + PVC + Service
├── redis.yaml            Redis Deployment + Service (rate limiting)
├── qdrant.yaml           Qdrant Deployment + PVC + Service (vector search)
├── kafka.yaml            Zookeeper + Kafka Deployments + Services
├── api.yaml              API service (2 replicas) + Service
├── repository.yaml       Repository service (2 replicas) + Service
├── worker.yaml           Worker Deployment (Kafka consumer, no Service)
├── ai.yaml               AI service (2 replicas) + Service
├── ingress.yaml          Nginx Ingress with SSE-compatible settings
└── kustomization.yaml    Kustomize listing for `kubectl apply -k`
```

## Pre-requisites

| Tool | Version |
|------|---------|
| kubectl | ≥ 1.27 |
| Kubernetes cluster | EKS / GKE / AKS / kind |
| nginx ingress controller | any recent |
| (Optional) cert-manager | for automatic TLS |

## Quick start

### 1 — Fill in secrets
Edit `k8s/secrets.yaml` and replace every `REPLACE_ME` with your real values, **or** use `kubectl create secret` (recommended — keeps secrets out of files):

```bash
kubectl create namespace forgeai

kubectl create secret generic forgeai-secrets -n forgeai \
  --from-literal=POSTGRES_USER=forgeai \
  --from-literal=POSTGRES_PASSWORD=<strong-password> \
  --from-literal=SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))") \
  --from-literal=GROQ_API_KEY=<your-groq-api-key> \
  --from-literal=GITHUB_TOKEN=<your-github-pat> \
  --from-literal=GITHUB_APP_ID=<id> \
  --from-literal=GITHUB_WEBHOOK_SECRET=<secret>
```

### 2 — Build and push images
```bash
# From repo root — replace <registry> with your Docker registry
docker build -t <registry>/forgeai/api:latest        Services/api
docker build -t <registry>/forgeai/repository:latest Services/repository
docker build -t <registry>/forgeai/worker:latest     Services/worker
docker build -t <registry>/forgeai/ai:latest         Services/ai

docker push <registry>/forgeai/api:latest
docker push <registry>/forgeai/repository:latest
docker push <registry>/forgeai/worker:latest
docker push <registry>/forgeai/ai:latest
```

Update the `image:` field in each YAML to point at your registry.

### 3 — Apply all resources
```bash
kubectl apply -k k8s/
```

Or individually in dependency order:
```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/secrets.yaml   # skip if used kubectl create secret above
kubectl apply -f k8s/postgres.yaml
kubectl apply -f k8s/redis.yaml
kubectl apply -f k8s/qdrant.yaml
kubectl apply -f k8s/kafka.yaml
kubectl apply -f k8s/api.yaml
kubectl apply -f k8s/repository.yaml
kubectl apply -f k8s/worker.yaml
kubectl apply -f k8s/ai.yaml
kubectl apply -f k8s/ingress.yaml
```

### 4 — Verify
```bash
kubectl get pods -n forgeai
kubectl logs -n forgeai deploy/api
kubectl logs -n forgeai deploy/ai
```

## Ingress

Edit `k8s/ingress.yaml` and change `forge.ai.example.com` to your domain.
Uncomment the TLS block and the cert-manager annotation after installing cert-manager.

## Scaling

```bash
# Scale AI service to 4 replicas during high load
kubectl scale deploy/ai -n forgeai --replicas=4

# Scale worker for more indexing throughput
kubectl scale deploy/worker -n forgeai --replicas=3
```

## Notes

- **Alembic runs automatically** on startup (see `entrypoint.sh` in each service).
- **Worker** has no Service — it only consumes from Kafka.
- **Rate limiting** is Redis-backed; works across all AI service replicas.
- For production, replace the single-node Kafka with a managed service (AWS MSK, Confluent Cloud).
