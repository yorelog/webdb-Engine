# webdb-Engine

**Web-as-Database Intelligent Automation Engine**

> Treat every website as a queryable, operable database.  
> Automatically understand page structure, plan actions, execute them safely, learn from failures, and sync extracted data to local storage — all in a closed-loop system.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Architecture](#2-architecture)
3. [Module Reference](#3-module-reference)
4. [Data Models](#4-data-models)
5. [Getting Started](#5-getting-started)
6. [Configuration](#6-configuration)
7. [Security & Compliance](#7-security--compliance)
8. [Training Pipeline](#8-training-pipeline)
9. [MVP Roadmap](#9-mvp-roadmap)
10. [Evaluation Metrics](#10-evaluation-metrics)

---

## 1. System Overview

### Problem Statement

Modern organisations need to extract, monitor, and operate on data that lives inside web applications: internal portals, SaaS dashboards, e-commerce back-offices, regulatory filing systems.  Doing this manually is slow and brittle; existing scraping tools are fragile and require per-site maintenance.

**webdb-Engine** solves this by treating each website as a *learnable data source*:

| Concept | Traditional View | webdb-Engine View |
|---|---|---|
| Web page | HTML document | Queryable data view |
| DOM element | Visual node | Field / Action / Status signal |
| User interaction | Random click | Transactional action step |
| Failure | Exception | Training sample |
| Human correction | Hotfix | Continuous learning signal |

### Supported Tasks

| Task | Supported |
|---|---|
| Login & session management | ✅ |
| List / table data extraction | ✅ |
| Paginated data collection | ✅ |
| Form fill and submission | ✅ |
| File download | ✅ |
| Search and filter | ✅ |
| Incremental sync to local DB | ✅ |
| Human annotation feedback | ✅ |
| Training data export (SFT/DPO/RLHF) | ✅ |
| Payments / fund transfers | ❌ (out of scope) |
| CAPTCHA solving | ❌ (out of scope) |
| OAuth / MFA flows | ⚠️ (manual assist required) |

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    webdb-Engine                         │
│                                                         │
│  ┌──────────────┐     ┌──────────────────────────────┐  │
│  │  Collection  │────▶│   Page Knowledge Base (DB)   │  │
│  │    Layer     │     │  Sites / Pages / Elements /  │  │
│  └──────────────┘     │  Trajectories / Credentials  │  │
│         │             └──────────────────────────────┘  │
│         ▼                          │                    │
│  ┌──────────────┐                  ▼                    │
│  │    Page      │     ┌──────────────────────────────┐  │
│  │Understanding │────▶│     Action Planning Layer    │  │
│  │    Layer     │     │  (Rule-based + LLM-optional) │  │
│  └──────────────┘     └──────────────────────────────┘  │
│                                    │                    │
│                                    ▼                    │
│  ┌──────────────┐     ┌──────────────────────────────┐  │
│  │  Annotation  │◀────│      Executor Layer          │  │
│  │  & Feedback  │     │  (Playwright + retry/rollback│  │
│  │    Layer     │     │   + sandbox + screenshot)    │  │
│  └──────────────┘     └──────────────────────────────┘  │
│         │                          │                    │
│         ▼                          ▼                    │
│  ┌──────────────┐     ┌──────────────────────────────┐  │
│  │  Training &  │     │     Local Sync Layer         │  │
│  │  Continuous  │     │  SQLite / PostgreSQL /       │  │
│  │  Learning    │     │  CSV / Parquet               │  │
│  └──────────────┘     └──────────────────────────────┘  │
│                                                         │
│  ┌──────────────────────────────────────────────────┐   │
│  │           Security & Audit Layer                 │   │
│  │  Credential Vault · PII Redaction · Audit Log    │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

### Layer Summary

| Layer | Module | Input | Output |
|---|---|---|---|
| **Collection** | `webdb.collector` | URL + credentials | `CollectedPage` (HTML, AX tree, HAR, screenshots) |
| **Knowledge Base** | `webdb.database` | Collected artefacts | Persisted Site/Page/Element/Trajectory records |
| **Understanding** | `webdb.understanding` | HTML + DOM | `ClassificationResult`, `RecognisedElement[]` |
| **Planning** | `webdb.planner` | Classification + Elements | `ActionPlan` |
| **Execution** | `webdb.executor` | ActionPlan + URL | `ExecutionResult` with per-step outcomes |
| **Annotation** | `webdb.annotation` | Failed steps / trajectories | `AnnotationTask` queue → `TrainingRecord` |
| **Training** | `webdb.training` | `TrainingRecord` DB rows | JSONL files (SFT / DPO / reward) |
| **Sync** | `webdb.sync` | Extracted rows + `SyncTask` | Rows written to local storage |
| **Security** | `webdb.security` | Plaintext secrets / raw HTML | Encrypted secrets, redacted HTML, audit events |

---

## 3. Module Reference

### `webdb.collector.page_collector`

```python
from webdb.collector.page_collector import PageCollector

async with PageCollector() as collector:
    page = await collector.collect("https://example.com")

print(page.html)              # Full HTML source
print(page.accessibility_tree)  # AX tree dict
print(page.bounding_boxes)    # List of element bounding boxes
print(page.content_hash)      # SHA-256 of HTML
```

Collects: HTML, rendered DOM (post-JS), title, Playwright accessibility tree, network HAR (request log), element bounding boxes, full-page screenshot.

---

### `webdb.understanding.dom_parser`

```python
from webdb.understanding.dom_parser import DOMParser

parser = DOMParser(html)
elements = parser.get_interactive_elements()
forms = parser.get_forms()
links = parser.get_links()
```

---

### `webdb.understanding.page_classifier`

```python
from webdb.understanding.page_classifier import PageClassifier

result = PageClassifier(html, title="Login", url="/login").classify()
print(result.page_type)    # PageType.LOGIN
print(result.confidence)   # 0.75
print(result.signals)      # {"has_password_field": True, ...}
```

Rule-based classifier; replace or augment with an ML model for higher accuracy.

---

### `webdb.planner.action_planner`

```python
from webdb.planner.action_planner import ActionPlanner

planner = ActionPlanner(page_type_result, recognised_elements)

plan = planner.plan_login("user@example.com", "password")
plan = planner.plan_extract()
plan = planner.plan_paginate_and_extract(max_pages=10)
plan = planner.plan_search("keyword")
plan = planner.plan_download()
```

---

### `webdb.executor.browser_executor`

```python
from webdb.executor.browser_executor import BrowserExecutor

async with BrowserExecutor() as executor:
    result = await executor.execute(plan, url="https://example.com")

print(result.overall_status)  # ActionStatus.SUCCESS
print(result.success_rate)    # 1.0
for step in result.steps:
    print(step.status, step.duration_ms, step.error_message)
```

Features: configurable retry (default 3), fallback selectors, before/after DOM hash comparison, screenshot capture per step.

---

### `webdb.sync.sync_manager` + `webdb.sync.storage_adapters`

```python
from webdb.sync.sync_manager import SyncManager

manager = SyncManager()
task_id = manager.register_task(
    site_id="...",
    source_url="https://example.com/data",
    target_type="sqlite",   # or "csv" or "parquet"
    target_path="local.db",
    field_mapping={"Name": "name", "Date": "date"},
)
report = manager.run_task(task_id, rows=[{"Name": "Alice", "Date": "2024-01-01"}])
print(report.rows_written)
```

---

### `webdb.annotation.annotation_manager`

```python
from webdb.annotation.annotation_manager import AnnotationManager, AnnotationResult

mgr = AnnotationManager()
task_id = mgr.queue_failure(trajectory_id="...", priority=9)
pending = mgr.get_pending()

result = AnnotationResult(
    annotation_task_id=task_id,
    annotation_type="trajectory_failure",
    annotator_id="human-1",
    corrected_steps=[{"action_type": "click", "selector": "#real-btn"}],
)
mgr.submit(result)
```

---

### `webdb.security`

```python
from webdb.security.credential_manager import CredentialManager
from webdb.security.audit_logger import AuditLogger
from webdb.security.pii_handler import PIIHandler

# Credentials
cred_mgr = CredentialManager()
cred_mgr.store(site_id="...", username="admin", secret="p@ss")
secret = cred_mgr.retrieve(site_id="...", username="admin")

# Audit
audit = AuditLogger()
audit.log(actor="system", action="sync.run", outcome="success", detail={"rows": 42})

# PII redaction
pii = PIIHandler()
clean_html = pii.redact_text(raw_html)
clean_row = pii.redact_dict(data_row)
```

---

## 4. Data Models

All entities are stored in the Page Knowledge Base (SQLAlchemy ORM, default SQLite).

### Entity Relationship

```
Site (1) ──▶ (N) Page (1) ──▶ (N) Element
                  │
                  └──▶ (N) Trajectory (1) ──▶ (N) ActionStep
                  │
                  └──▶ (N) AnnotationTask ──▶ TrainingRecord
                  
Site (1) ──▶ (N) Credential
Site (1) ──▶ (N) SyncTask

AuditLog  (standalone append-only)
```

### Key Tables

| Table | Purpose |
|---|---|
| `sites` | One row per website origin |
| `pages` | Collected page snapshots (versioned) |
| `elements` | Semantic elements extracted from pages |
| `trajectories` | Task execution plans and their outcomes |
| `action_steps` | Individual steps within a trajectory |
| `credentials` | Fernet-encrypted site credentials |
| `sync_tasks` | Scheduled/ongoing data sync jobs |
| `annotation_tasks` | Human labelling queue |
| `training_records` | SFT / DPO / reward training examples |
| `audit_logs` | Immutable operation audit trail |

### Training Record Schema

```json
{
  "id": "uuid",
  "type": "sft | preference | reward | failure",
  "split": "train | val",
  "input": { "...": "..." },
  "output": { "...": "..." },
  "reward": null
}
```

---

## 5. Getting Started

### Installation

```bash
pip install -e ".[dev]"
```

### Initialise the database

```bash
webdb init-db
```

### Collect a page

```bash
webdb collect --url https://example.com
```

### Export training data

```bash
webdb export-training --output-dir ./data/training
```

### Run tests

```bash
pytest tests/ -q
```

---

## 6. Configuration

All settings are read from environment variables (prefix `WEBDB_`) or a `.env` file.

| Variable | Default | Description |
|---|---|---|
| `WEBDB_DB_URL` | `sqlite:///webdb.db` | SQLAlchemy DB URL |
| `WEBDB_BROWSER_TYPE` | `chromium` | Playwright browser |
| `WEBDB_BROWSER_HEADLESS` | `true` | Headless mode |
| `WEBDB_BROWSER_TIMEOUT_MS` | `30000` | Action timeout |
| `WEBDB_BROWSER_SANDBOX` | `true` | Extra sandbox args |
| `WEBDB_EXECUTOR_MAX_RETRIES` | `3` | Retries per step |
| `WEBDB_EXECUTOR_RETRY_DELAY_S` | `1.5` | Delay between retries |
| `WEBDB_CREDENTIAL_ENCRYPTION_KEY` | *(required in prod)* | Fernet key |
| `WEBDB_AUDIT_LOG_PATH` | `logs/audit.jsonl` | Audit log path |
| `WEBDB_PII_REDACT_ENABLED` | `true` | Auto-redact PII |
| `WEBDB_SYNC_BATCH_SIZE` | `500` | Sync batch size |
| `WEBDB_SYNC_DEFAULT_TARGET` | `sqlite` | Default sync backend |
| `WEBDB_TRAINING_DATA_DIR` | `data/training` | Training JSONL output |
| `WEBDB_LOG_LEVEL` | `INFO` | Log verbosity |

Generate a Fernet key:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

---

## 7. Security & Compliance

### Credential Storage
- Credentials are encrypted with **Fernet** symmetric encryption before database storage.
- The encryption key must be provided via `WEBDB_CREDENTIAL_ENCRYPTION_KEY`.
- Never commit credentials or keys to source control.

### PII Handling
- `PIIHandler` detects and redacts: email addresses, phone numbers, ID card numbers, credit card numbers, IPv4 addresses.
- Redaction is applied before persisting collected HTML/DOM data when `WEBDB_PII_REDACT_ENABLED=true`.

### Audit Trail
- Every privileged operation (credential store/delete, sync run, annotation submit) writes an immutable entry to the `audit.jsonl` file and optionally to the `audit_logs` database table.
- Audit entries include: timestamp, actor, action, outcome, resource type/ID, IP address.

### Operations Requiring Human Approval
The following operations must be confirmed by a human operator before execution:
- Any action on a payment, transfer, or financial form.
- Bulk delete or overwrite of synced data.
- Credential rotation.
- Deployment of a newly trained model version.

### Browser Sandboxing
- The Playwright browser is launched with `--no-sandbox --disable-dev-shm-usage` when `WEBDB_BROWSER_SANDBOX=true`.
- For production, consider running the browser inside a container with `seccomp` profiles and restricted network egress.

---

## 8. Training Pipeline

### Data Types

| Type | Description | Use For |
|---|---|---|
| `sft` | Input → correct output pairs | Supervised fine-tuning |
| `preference` | Chosen / rejected trajectory pairs | DPO / RLHF |
| `reward` | Input → scalar reward | Reward model training |
| `failure` | Failed trajectory + correction | Negative sampling |

### Workflow

```
1. Executor fails a step
        ↓
2. AnnotationManager.queue_failure() → AnnotationTask
        ↓
3. Human annotator reviews in UI
        ↓
4. AnnotationManager.submit() → TrainingRecord
        ↓
5. TrainingDataPipeline.export() → JSONL files
        ↓
6. External training job (SFT / DPO / PPO)
        ↓
7. Updated model deployed back to planner
```

### Export

```python
from webdb.training.data_pipeline import TrainingDataPipeline
from webdb.database.models import TrainingDataType

pipeline = TrainingDataPipeline()
counts = pipeline.export(data_type=TrainingDataType.SFT)
# → {"data/training/sft_train.jsonl": 1240, "data/training/sft_val.jsonl": 138}
```

---

## 9. MVP Roadmap

### Phase 1 — MVP (current)

| Component | Implementation |
|---|---|
| Page collection | Playwright (rule-based) |
| Page classification | Rule-based heuristics |
| Element recognition | Rule-based heuristics |
| Action planning | Rule-based templates |
| Executor | Playwright + retry |
| Sync | SQLite / CSV / Parquet |
| Security | Fernet encryption + JSONL audit |
| Annotation | DB queue + manual UI needed |
| Training export | JSONL export |

### Phase 2 — Enhanced

- Replace rule-based classifier and planner with fine-tuned LLM (using SFT data from Phase 1).
- Add PostgreSQL and Parquet sync targets.
- Build a minimal annotation web UI (nanochat integration).
- Implement reward model training from preference data.
- Add site version-change detection (content hash diff).

### Phase 3 — Production

- Full RLHF / DPO training loop with PPO.
- Continuous model evaluation and A/B testing.
- Multi-tenant access control and RBAC.
- Integration with autoresearch or similar training pipeline orchestration.
- Kubernetes-based browser sandbox fleet.
- Vector database integration for semantic page matching.

---

## 10. Evaluation Metrics

### System-Level

| Metric | Definition |
|---|---|
| **Task success rate** | % of ActionPlans that complete with `overall_status=SUCCESS` |
| **Step success rate** | % of individual ActionSteps that succeed |
| **Data completeness** | Rows extracted / expected rows |
| **Sync fidelity** | Hash match between source and synced data |

### Model-Level (future)

| Metric | Definition |
|---|---|
| **Page type accuracy** | Classifier accuracy vs human labels |
| **Element role F1** | Per-role F1 score vs human annotations |
| **Planner task success** | End-to-end task completion on held-out sites |
| **Reward model correlation** | Spearman ρ between model score and human preference |

### Offline vs Online

- **Offline**: Replay recorded trajectories against saved HTML snapshots.
- **Online**: Shadow-mode execution against live sites; compare with human baseline.