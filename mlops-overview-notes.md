# InsightHub MLOps Overview

## Model Registry

The registry is the system of record for approved model artifacts and their lineage: model version, code/data references, evaluation results, provider or embedding identity, and deployment metadata. InsightHub's observability layer should reference the deployed model identity rather than treating a prompt, dashboard, or application build as the model artifact.

## Approval Gate

Promotion from a candidate model to a deployable version requires reproducible evaluation, safety and quality checks, ownership sign-off, and an explicit version transition. The gate records the candidate, metrics, approvers, and deployment target. A passing Prometheus signal alone is not approval to promote a model.

## Drift Monitoring

Monitor both input/data drift and concept or outcome drift. Data drift concerns changes in the distribution of inputs or retrieved context; concept drift concerns a change in the relationship between inputs and desired outcomes. Telemetry such as latency, errors, token usage, and retrieval quality provides operational context, but does not by itself prove model drift. Drift findings should be linked to the model version and evaluated before promotion or rollback decisions.

## Rollback

Rollback means selecting the last known-good approved model or configuration, restoring the prior deployment, and verifying health and quality signals. It must be reversible, auditable, and separate from incident evidence retention. The rollback owner confirms service recovery; the ML owner investigates model quality and prepares any retraining or replacement candidate.

## DevOps vs ML Engineer ownership boundary

| Area | DevOps owns primary | ML Engineer owns primary |
|---|---|---|
| Registry and deployment plumbing | Registry availability, artifact wiring, rollout and rollback mechanics | Model packaging, lineage, evaluation metadata and version choice |
| Approval gate | CI/CD enforcement, access control and audit trail | Quality, safety, bias and acceptance criteria for the model |
| Drift response | Monitoring pipeline, alert routing, capacity and service recovery | Drift analysis, retraining decision and candidate validation |
| Incident operations | Runtime telemetry, SLOs, rollback execution and communications | Model-behavior diagnosis and remediation proposal |

Neither role silently retrains or promotes a model outside the approval process.
