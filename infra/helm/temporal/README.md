# Temporal Cluster Helm Deployment (Staging)

This directory defines the Helm deployment specification for the Temporal cluster in staging (ticket S01.2.1).

## Architecture

- **Temporal Server (v1.24.2):** Scaled frontend, history, and matching services.
- **Persistence:** Dedicated Postgres databases (`riven_temporal_staging` and `riven_temporal_visibility_staging`).
- **Temporal Web UI (v2.26.2):** Ingress-exposed dashboard at `https://temporal.staging.riven.internal`.
- **Admin Tools:** Diagnostic pod with `tctl` and `temporal` CLI.

## Deployment

```bash
helm repo add temporal https://go.temporal.io/helm-charts
helm repo update
helm dependency build infra/helm/temporal
helm upgrade --install temporal infra/helm/temporal \
  -n temporal --create-namespace \
  -f infra/helm/temporal/values.yaml \
  -f infra/helm/temporal/values-staging.yaml
```
