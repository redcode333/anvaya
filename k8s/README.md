# Kubernetes deployment

Everything is plain manifests composed with **Kustomize** (`kustomization.yaml` at the repo root, so Grafana reuses
`monitoring/grafana/*` without duplicating the dashboard). Namespace: `anvaya`.

```
k8s/
├── namespace.yaml                 # Pod Security Standard "restricted" enforced
├── secrets.env.example            # copy to secrets.env (gitignored)
├── app/
│   ├── deployment.yaml            # API + UI, non-root, read-only rootfs, startup/liveness/readiness probes
│   ├── service.yaml               # Service :5000 + PVC anvaya-data (SQLite)
│   ├── ingress.yaml               # anvaya.localtest.me, grafana.localtest.me (ingress-nginx)
│   └── networkpolicy.yaml         # default-deny + only ingress-nginx / prometheus / grafana paths
└── monitoring/
    ├── prometheus.yml             # scrape config (bearer token for /metrics)
    ├── prometheus.yaml            # Deployment + Service + PVC
    └── grafana.yaml               # Deployment + Service + PVC, provisioned datasource + dashboard
```

## Deploy

```bash
# 1. Build the image and make it available to the cluster
docker build -t anvaya-ai:latest .
#    Docker Desktop Kubernetes: nothing else to do (shares the local image store)
#    kind:      kind load docker-image anvaya-ai:latest
#    minikube:  minikube image load anvaya-ai:latest
#    registry:  docker tag anvaya-ai:latest <registry>/anvaya-ai:1.0.0 && docker push ...
#               kustomize edit set image anvaya-ai=<registry>/anvaya-ai:1.0.0

# 2. Secrets
cp k8s/secrets.env.example k8s/secrets.env      # set ANVAYA_METRICS_TOKEN and GRAFANA_ADMIN_PASSWORD

# 3. Apply
kubectl apply -k .
kubectl -n anvaya wait --for=condition=Available deploy --all --timeout=240s
```

## Access

With [ingress-nginx](https://kubernetes.github.io/ingress-nginx/deploy/) installed:

* App → http://anvaya.localtest.me
* Grafana → http://grafana.localtest.me (anonymous read-only; admin password from `secrets.env`)

Without an ingress controller:

```bash
kubectl -n anvaya port-forward svc/anvaya 5000:5000
kubectl -n anvaya port-forward svc/grafana 3000:3000
kubectl -n anvaya port-forward svc/prometheus 9090:9090    # Prometheus is never exposed via Ingress
```

## What was verified

Rendered with `kubectl kustomize`, validated with `kubeconform -strict` (21/21 resources valid, Kubernetes 1.30), and
deployed to a single-node **k3s v1.30.5** cluster:

* all three pods `Running`, 0 restarts, under the `restricted` Pod Security Standard;
* TC2 passes against the in-cluster API; `/metrics` returns 401 without the token;
* Prometheus target `anvaya` is `up` (token auth); Grafana serves the 32-panel dashboard from ConfigMaps;
* NetworkPolicy allows Grafana → Prometheus and blocks Grafana → API (k3s enforces policies);
* SQLite data on the PVC survives `kubectl rollout restart`.

Not verified there: the Ingress (k3s ships Traefik, the manifest targets `ingressClassName: nginx`).

## Design decisions & scaling notes

* **`replicas: 1` + `strategy: Recreate`** on purpose. The MVP stores data in SQLite on a `ReadWriteOnce` volume, and the
  case-code rate limiter and Prometheus counters are in-process. Running two pods would split data and metrics. To scale:
  move to PostgreSQL (planned production DB), a shared rate limiter (e.g. Redis), and `prometheus_client` multiprocess
  mode or per-pod scraping via the Prometheus Operator — then raise replicas, switch to `RollingUpdate`, add an HPA and a
  PodDisruptionBudget.
* **Config hashing:** ConfigMaps/Secret come from Kustomize generators, so any change rolls the affected pods automatically.
* **Security:** non-root UIDs, `readOnlyRootFilesystem` (API and Prometheus), all capabilities dropped, `RuntimeDefault`
  seccomp, no service-account token mounted, secrets only via `secretGenerator`.
* **Storage:** PVCs use the cluster's default StorageClass (1 Gi app, 5 Gi Prometheus, 1 Gi Grafana).
* **TLS:** add a `tls:` block and a cert-manager issuer to `k8s/app/ingress.yaml` for public hostnames.

## Remove

```bash
kubectl delete -k .        # deletes the namespace, including PVC data
```
