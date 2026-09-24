# Ticket index

Generated from the Riven product backlog (also in ClickUp: Team Space → Riven-Prodcut).
Do not edit by hand; scope changes go through the backlog and are regenerated.

`Repos` shows where each story's tasks live. **This repo: backend.** Open `<story-id>.md` for full details; a task ID like S01.2.3 lives in `S01.2.md`.

## Baseline (MVP scope, described in the product spec)

| ID | Epic | Covers |
| --- | --- | --- |
| B01 | Project Foundation | Requirements, architecture, stack selection, repository, DB design, MVP boundaries (Sprint 1). |
| B02 | Repository & Change Capture | Single-repo integration, commit/PR capture, change metadata, file-change detection, basic change history (Sprint 2). |
| B03 | Sandbox Manager | Isolated container creation, code + test execution, log collection, result handling, teardown (Sprint 3). |
| B04 | Verification Engine | Verification workflow; functional, failure, regression, basic security, spec checks; result classification Passed/Failed/Needs Review; verification report (Sprint 4). |
| B05 | Bug Memory & Regression Lock | Bug DB with ID, description, module, requirement, change, repro, result, fix, regression test, timestamps; regression lock for one module / selected bugs (Sprint 5). |
| B06 | Causal Graph | Graph model with Requirement, Change, Module, Bug, Fix, Verification, Test nodes; relationship creation; basic visualization; 'Why does this exist?' query (Sprint 6). |
| B07 | Agent Workflow & Dashboard | Controlled Code / Verification / Bug-Analysis agent roles; dashboard with change info, verification status, bug info, regression status, graph view (Sprint 7). |
| B08 | Integration & Final Testing | E2E test of the 15-step success scenario, basic performance and security checks, documentation, demo (Sprint 8). |

## Phase 1: Foundation & Infrastructure

Re-platform the MVP into a modular, durable, cloud-ready architecture.

### E01 · Production Architecture & Service Foundation (P0 · XL)

| Story | Title | Pri | Pts | Depends on | Repos |
| --- | --- | --- | --- | --- | --- |
| [S01.1](S01.1.md) | Define service boundaries & internal contracts | P0 | 5 | B01 | backend |
| [S01.2](S01.2.md) | Durable workflow orchestration for the verification pipeline | P0 | 8 | S01.1 | backend |
| [S01.3](S01.3.md) | Domain event backbone with transactional outbox | P0 | 5 | S01.1 | backend |
| [S01.4](S01.4.md) | Production data layer | P0 | 5 | S01.1 | backend |

### E02 · Environments, Developer Experience & IaC (P0 · L)

| Story | Title | Pri | Pts | Depends on | Repos |
| --- | --- | --- | --- | --- | --- |
| [S02.1](S02.1.md) | One-command local development environment | P0 | 3 | S01.1 | backend |
| [S02.2](S02.2.md) | Environment & configuration strategy | P0 | 3 | S02.1 | backend |
| [S02.3](S02.3.md) | Code quality & PR CI baseline | P0 | 3 | S01.1 | backend |
| [S02.4](S02.4.md) | Infrastructure as Code baseline | P0 | 5 | S02.2 | backend |

## Phase 2: Auth & Core Platform

Users, orgs, multi-tenancy, RBAC, public API, audit, notifications, metering.

### E03 · Identity, Authentication & Authorization (P0 · XL)

| Story | Title | Pri | Pts | Depends on | Repos |
| --- | --- | --- | --- | --- | --- |
| [S03.1](S03.1.md) | User sign-up and login | P0 | 5 | S02.2 | backend, frontend |
| [S03.2](S03.2.md) | Organizations & multi-tenant isolation | P0 | 8 | S03.1, S01.4 | backend |
| [S03.3](S03.3.md) | Role-based access control | P0 | 5 | S03.2 | backend, frontend |
| [S03.4](S03.4.md) | Service accounts & API keys for AI agents / CI | P0 | 5 | S03.3 | backend, frontend |
| [S03.5](S03.5.md) | Session security & MFA | P1 | 3 | S03.1 | backend, frontend |

### E04 · Public API & Core Platform Services (P0 · XL)

| Story | Title | Pri | Pts | Depends on | Repos |
| --- | --- | --- | --- | --- | --- |
| [S04.1](S04.1.md) | Versioned public REST API v1 | P0 | 8 | S03.3 | backend |
| [S04.2](S04.2.md) | Outbound webhooks | P1 | 5 | S01.3, S04.1 | backend, frontend |
| [S04.3](S04.3.md) | Python SDK and `riven` CLI | P1 | 5 | S04.1, S03.4 | backend |
| [S04.4](S04.4.md) | Core audit log | P0 | 3 | S03.3 | backend, frontend |
| [S04.5](S04.5.md) | Notification service | P1 | 3 | S01.3 | backend, frontend |
| [S04.6](S04.6.md) | Usage metering & plans | P2 | 5 | S04.1, S01.3 | backend, frontend |

## Phase 3: Core Features — MVP Hardening

Take every MVP module (capture, sandbox, verification, memory, regression, graph, dashboard, agents) to production grade.

### E05 · Change Capture & Understanding 2.0 (P1 · L)

| Story | Title | Pri | Pts | Depends on | Repos |
| --- | --- | --- | --- | --- | --- |
| [S05.1](S05.1.md) | GitHub App-based capture | P0 | 5 | S03.2 | backend |
| [S05.2](S05.2.md) | AST-level change analysis | P1 | 8 | S05.1 | backend |
| [S05.3](S05.3.md) | Change provenance (human vs AI agent) | P1 | 3 | S03.4, S05.1 | backend, frontend |
| [S05.4](S05.4.md) | Requirement ingestion & auto-linking | P1 | 8 | S05.2, S09.1 | backend, frontend |

### E06 · Sandbox Platform 2.0 (P0 · XL · pull-forward)

| Story | Title | Pri | Pts | Depends on | Repos |
| --- | --- | --- | --- | --- | --- |
| [S06.1](S06.1.md) | Reproducible environment builder | P0 | 8 | S01.2 | backend |
| [S06.2](S06.2.md) | Ephemeral service dependencies | P1 | 5 | S06.1 | backend |
| [S06.3](S06.3.md) | Resource limits & network policy | P0 | 5 | S06.1 | backend |
| [S06.4](S06.4.md) | Artifact, log & coverage capture | P1 | 3 | S01.4, S06.1 | backend |
| [S06.5](S06.5.md) | Sandbox lifecycle guarantees | P0 | 3 | S06.1 | backend |

### E07 · Verification Engine 2.0 (P0 · XL · pull-forward)

| Story | Title | Pri | Pts | Depends on | Repos |
| --- | --- | --- | --- | --- | --- |
| [S07.1](S07.1.md) | Pluggable verifier framework | P0 | 8 | S01.2 | backend |
| [S07.2](S07.2.md) | Flaky test detection & quarantine | P0 | 5 | S07.1, S06.4 | backend, frontend |
| [S07.3](S07.3.md) | Verdict policy & severity classification | P0 | 5 | S07.1 | backend, frontend |
| [S07.4](S07.4.md) | Human review workflow for 'Needs Review' | P0 | 5 | S07.3, S03.3, S04.5 | backend, frontend |
| [S07.5](S07.5.md) | Verification report 2.0 | P1 | 3 | S07.3 | backend |
| [S07.6](S07.6.md) | Independence enforcement | P0 | 3 | S03.4, S07.1 | backend |

### E08 · Bug Memory & Regression Lock 2.0 (P0 · XL · pull-forward)

| Story | Title | Pri | Pts | Depends on | Repos |
| --- | --- | --- | --- | --- | --- |
| [S08.1](S08.1.md) | Bug fingerprinting & deduplication | P0 | 8 | S07.3 | backend, frontend |
| [S08.2](S08.2.md) | Bug lifecycle state machine | P0 | 3 | S08.1, S04.4 | backend |
| [S08.3](S08.3.md) | Automated reproduction capture | P1 | 5 | S06.4, S08.2 | backend |
| [S08.4](S08.4.md) | Regression lock for all confirmed bugs | P0 | 8 | S08.3 | backend |
| [S08.5](S08.5.md) | Smart regression selection | P1 | 5 | S08.4, S09.2 | backend |

### E09 · Causal Graph 2.0 (P1 · L)

| Story | Title | Pri | Pts | Depends on | Repos |
| --- | --- | --- | --- | --- | --- |
| [S09.1](S09.1.md) | Graph schema v2 & versioning | P1 | 5 | S01.4 | backend |
| [S09.2](S09.2.md) | Automated relationship extraction | P1 | 5 | S09.1, S05.2, S06.4 | backend |
| [S09.3](S09.3.md) | Temporal (point-in-time) queries | P2 | 5 | S09.1 | backend |
| [S09.4](S09.4.md) | Interactive graph explorer | P1 | 5 | S09.2, S10.1 | backend, frontend |

### E10 · Developer Dashboard & UX Polish (P1 · L)

| Story | Title | Pri | Pts | Depends on | Repos |
| --- | --- | --- | --- | --- | --- |
| [S10.1](S10.1.md) | Design system & accessibility | P1 | 5 | S02.3 | frontend |
| [S10.2](S10.2.md) | Repository overview & health | P1 | 3 | S10.1, S08.4 | backend, frontend |
| [S10.3](S10.3.md) | Live change detail page | P1 | 5 | S10.1, S07.5 | backend, frontend |
| [S10.4](S10.4.md) | Bug memory explorer | P1 | 3 | S08.2, S10.1 | backend, frontend |
| [S10.5](S10.5.md) | Onboarding & connect-repo wizard | P1 | 3 | S05.1, S06.1 | backend, frontend |

### E11 · Agent Orchestration 2.0 (P1 · L)

| Story | Title | Pri | Pts | Depends on | Repos |
| --- | --- | --- | --- | --- | --- |
| [S11.1](S11.1.md) | Agent role framework & meeting protocol | P1 | 5 | S07.6 | backend, frontend |
| [S11.2](S11.2.md) | Memory-aware Bug Analysis Agent | P1 | 5 | S08.1, S09.2 | backend |
| [S11.3](S11.3.md) | LLM guardrails & cost control | P0 | 3 | S04.6 | backend |
| [S11.4](S11.4.md) | Riven MCP server for external coding agents | P1 | 5 | S04.1, S03.4 | backend |

## Phase 4: Advanced Features

AI verification intelligence, gated auto-fix, multi-agent coordination.

### E12 · AI-Powered Verification Intelligence (P1 · XL)

| Story | Title | Pri | Pts | Depends on | Repos |
| --- | --- | --- | --- | --- | --- |
| [S12.1](S12.1.md) | Specification-to-test generation | P1 | 8 | S05.4, S07.1 | backend |
| [S12.2](S12.2.md) | Change risk scoring | P1 | 5 | S09.2, S14.2 | backend |
| [S12.3](S12.3.md) | Automated root-cause bisection | P2 | 5 | S08.3 | backend, frontend |
| [S12.4](S12.4.md) | Natural-language memory query ('Why' 2.0) | P1 | 5 | S09.2, S11.3 | backend, frontend |
| [S12.5](S12.5.md) | Property-based & fuzz verifier | P2 | 5 | S07.1 | backend |

### E13 · Safe Auto-Fix (Suggest-Only → Gated) (P2 · L)

| Story | Title | Pri | Pts | Depends on | Repos |
| --- | --- | --- | --- | --- | --- |
| [S13.1](S13.1.md) | Fix suggestion generation | P2 | 5 | S11.2 | backend |
| [S13.2](S13.2.md) | Independent verification of Riven fixes | P2 | 3 | S13.1, S07.6 | backend |
| [S13.3](S13.3.md) | Autonomy policy controls | P2 | 3 | S13.1, S03.3 | backend, frontend |

### E14 · Multi-Agent Coordination & Conflict Detection (P2 · L)

| Story | Title | Pri | Pts | Depends on | Repos |
| --- | --- | --- | --- | --- | --- |
| [S14.1](S14.1.md) | Concurrent change conflict detection | P2 | 5 | S05.2, S05.1 | backend |
| [S14.2](S14.2.md) | Agent & producer quality scorecards | P2 | 3 | S05.3, S08.2 | backend, frontend |
| [S14.3](S14.3.md) | Duplicate work detection | P3 | 3 | S14.1 | backend |

## Phase 5: Integrations

SCM/CI merge gates, issue trackers, chat, production feeds.

### E15 · Source Control & CI Integrations (P0 · L)

| Story | Title | Pri | Pts | Depends on | Repos |
| --- | --- | --- | --- | --- | --- |
| [S15.1](S15.1.md) | GitHub Checks & PR comments (merge gate) | P0 | 5 | S05.1, S07.5 | backend |
| [S15.2](S15.2.md) | GitLab & Bitbucket support | P2 | 8 | S15.1 | backend |
| [S15.3](S15.3.md) | CI system integrations | P1 | 3 | S04.3 | backend |

### E16 · Work Management & Communication Integrations (P2 · M)

| Story | Title | Pri | Pts | Depends on | Repos |
| --- | --- | --- | --- | --- | --- |
| [S16.1](S16.1.md) | Issue tracker integrations (Jira, Linear, ClickUp) | P2 | 8 | S08.2, S05.4 | backend |
| [S16.2](S16.2.md) | Slack & Microsoft Teams | P2 | 5 | S04.5 | backend |

### E17 · Production Verification Feeds (P2 · L)

| Story | Title | Pri | Pts | Depends on | Repos |
| --- | --- | --- | --- | --- | --- |
| [S17.1](S17.1.md) | Error-tracking ingestion (Sentry, Datadog) | P2 | 5 | S08.1, S16.1 | backend |
| [S17.2](S17.2.md) | Production recurrence & drift detection | P2 | 5 | S17.1 | backend |
| [S17.3](S17.3.md) | Incident memory | P3 | 3 | S09.1 | backend |

## Phase 6: Performance & Scalability

Multi-repo/multi-team, autoscaling sandbox fleet, test-impact analysis, SLO-backed performance.

### E18 · Multi-Repository & Multi-Team Scale (P1 · L)

| Story | Title | Pri | Pts | Depends on | Repos |
| --- | --- | --- | --- | --- | --- |
| [S18.1](S18.1.md) | Multi-repository support | P1 | 5 | S05.1 | backend |
| [S18.2](S18.2.md) | Teams & ownership | P1 | 3 | S18.1, S07.4 | backend |
| [S18.3](S18.3.md) | Cross-repo knowledge search | P2 | 3 | S10.4, S18.1 | backend, frontend |

### E19 · Performance & Throughput (P1 · XL)

| Story | Title | Pri | Pts | Depends on | Repos |
| --- | --- | --- | --- | --- | --- |
| [S19.1](S19.1.md) | Autoscaled Kubernetes sandbox fleet | P1 | 8 | S06.5, S02.4 | backend |
| [S19.2](S19.2.md) | Test impact analysis | P1 | 5 | S09.2, S12.2 | backend |
| [S19.3](S19.3.md) | Build & dependency caching | P1 | 3 | S06.1 | backend |
| [S19.4](S19.4.md) | Database & graph performance | P1 | 5 | S01.4 | backend |
| [S19.5](S19.5.md) | Load testing & performance SLOs | P1 | 3 | S19.1, S19.4 | backend |

## Phase 7: Security & Compliance

Sandbox isolation, secrets, encryption, SSO/SCIM, attestation, SOC 2 readiness.

### E20 · Platform Security & Compliance (P0 · XL · pull-forward)

| Story | Title | Pri | Pts | Depends on | Repos |
| --- | --- | --- | --- | --- | --- |
| [S20.1](S20.1.md) | Sandbox isolation hardening | P0 | 8 | S06.3, S19.1 | backend |
| [S20.2](S20.2.md) | Customer secrets & log redaction | P0 | 5 | S02.2, S11.3 | backend |
| [S20.3](S20.3.md) | Encryption & data protection | P0 | 3 | S02.4 | backend |
| [S20.4](S20.4.md) | Enterprise SSO & SCIM | P1 | 5 | S03.1 | backend |
| [S20.5](S20.5.md) | Verification attestation & tamper-evident audit | P1 | 5 | S07.6, S04.4 | backend |
| [S20.6](S20.6.md) | Security verifier 2.0 (SAST, SCA, secrets) | P1 | 5 | S07.1 | backend |
| [S20.7](S20.7.md) | Compliance & privacy readiness | P1 | 5 | S20.3, S04.4 | backend |
| [S20.8](S20.8.md) | Application security program | P0 | 5 | S04.1 | backend |

## Phase 8: Testing & QA

Quality engineering for Riven itself: test pyramid, E2E, benchmark corpus, LLM evals, chaos.

### E21 · Quality Engineering for Riven (P0 · L)

| Story | Title | Pri | Pts | Depends on | Repos |
| --- | --- | --- | --- | --- | --- |
| [S21.1](S21.1.md) | Test strategy & coverage gates | P0 | 3 | S02.3 | backend |
| [S21.2](S21.2.md) | Automated golden-path E2E | P0 | 5 | S02.4, S10.5 | backend, frontend |
| [S21.3](S21.3.md) | Benchmark bug corpus & detection metrics | P1 | 5 | S08.1 | backend |
| [S21.4](S21.4.md) | LLM evaluation harness | P1 | 3 | S11.3 | backend |
| [S21.5](S21.5.md) | Chaos & failure testing | P2 | 3 | S01.2, S19.1 | backend |

## Phase 9: Deployment & DevOps

CI/CD, GitOps, safe migrations, backup/DR, feature flags, self-hosted edition.

### E22 · CI/CD, Release Engineering & Reliability (P0 · L · pull-forward)

| Story | Title | Pri | Pts | Depends on | Repos |
| --- | --- | --- | --- | --- | --- |
| [S22.1](S22.1.md) | Container build & supply chain | P0 | 3 | S02.3 | backend |
| [S22.2](S22.2.md) | GitOps deployments with progressive delivery | P0 | 5 | S22.1, S02.4 | backend |
| [S22.3](S22.3.md) | Safe database migrations | P0 | 3 | S01.4, S22.2 | backend |
| [S22.4](S22.4.md) | Backup & disaster recovery | P0 | 3 | S02.4 | backend |
| [S22.5](S22.5.md) | Feature flags | P1 | 2 | S22.2 | backend |
| [S22.6](S22.6.md) | Self-hosted / VPC enterprise edition | P3 | 8 | S22.2, S20.1 | backend |

## Phase 10: Monitoring & Analytics

Platform observability, SLO alerting, cost tracking, customer-facing insights.

### E23 · Platform Observability & Operations (P0 · L · pull-forward)

| Story | Title | Pri | Pts | Depends on | Repos |
| --- | --- | --- | --- | --- | --- |
| [S23.1](S23.1.md) | Tracing, metrics & logging | P0 | 5 | S01.2 | backend |
| [S23.2](S23.2.md) | SLOs, alerting & on-call | P0 | 3 | S23.1 | backend |
| [S23.3](S23.3.md) | Error tracking for Riven | P1 | 2 | S22.2 | backend, frontend |
| [S23.4](S23.4.md) | Cost monitoring per tenant | P1 | 3 | S11.3, S19.1 | backend |

### E24 · Product & Engineering Analytics (P2 · L)

| Story | Title | Pri | Pts | Depends on | Repos |
| --- | --- | --- | --- | --- | --- |
| [S24.1](S24.1.md) | Product analytics | P2 | 2 | S10.5 | backend, frontend |
| [S24.2](S24.2.md) | Customer engineering insights dashboard | P2 | 5 | S08.5, S14.2, S18.2 | backend, frontend |
| [S24.3](S24.3.md) | Scheduled reports & exports | P3 | 2 | S24.2, S04.5 | backend |
| [S24.4](S24.4.md) | Fleet risk overview | P3 | 5 | S12.2, S17.2, S18.1 | backend, frontend |
