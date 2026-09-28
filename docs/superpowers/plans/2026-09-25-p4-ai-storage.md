# P4.1 AI Evaluation Storage Implementation Plan

**Execution status (2026-09-25):** Tasks 1–3 implemented and independently reviewed inline.
See [verification report](../reviews/p4-storage-verification.md). No commit/push or production
database migration was performed. Subsequent engine/UI/provider plans remain pending.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist reproducible, inspectable AI requests and results without changing existing market data.

**Architecture:** Add an isolated `ai` package and two tables to the existing SQLite database through `Repository.initialize()`. Reuse short SQLite transactions and the existing online backup. Freeze input at creation and all fields when a run becomes terminal.

**Tech Stack:** Python 3.12, sqlite3, dataclasses, JSON, pytest; existing FastAPI integration comes in P4.3.

**Spec:** `docs/superpowers/specs/2026-09-25-p4-ai-storage-contract-design.md`; reconciliation: `2026-09-25-p4-readiness-review.md` in this directory.

## Global Constraints

- “Do not overload the collector `runs` table.”
- “Never hold a SQLite write transaction open during network/model calls.”
- “Terminal runs are immutable; a manual rerun creates a new run linked to the same or new evidence, never overwrites prior results.”
- “Do not automatically expire evaluation history or evidence.”
- “Do not add PostgreSQL, vector search, blob storage, a message broker, or a generalized ORM/migration framework as part of this contract.”
- Cost/usage unknown is nullable, never silently zero. No live provider or budget selection here.
- Existing dirty changes belong to the user. Work inline as authorized; no bulk staging or schema writes against production while developing.

---

## File map and public contract

Create `src/casual_scout/ai/__init__.py`, `contracts.py`, `schema.sql`, `storage.py`.
Modify `storage/repository.py` only to execute the additive AI schema, and `pyproject.toml`
to package `ai/schema.sql`. Create `tests/test_ai_storage.py`, `tests/test_ai_backup.py`,
and `tests/ai_support.py`. Keep backup algorithms in `operations/backup.py` unchanged unless
the P4 round-trip test proves a defect.

`contracts.py` defines these concrete dataclasses; all dictionaries must be JSON-compatible:

```python
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class EvidenceRef:
    evidence_id: str
    analysis_date: str
    country: str
    app_id: str
    snapshot_id: str | None = None
    analytics_id: str | None = None
    metadata_version_id: str | None = None

@dataclass(frozen=True)
class EvaluationRequest:
    request_key: str
    analysis_date: str
    markets: tuple[str, ...]
    provider_id: str | None
    model_id: str | None
    prompt_version: str
    prompt_hash: str
    schema_version: str
    canonical_input: dict[str, Any]
    evidence: tuple[EvidenceRef, ...]
    policy: dict[str, Any]
    rerun_of: str | None = None

@dataclass(frozen=True)
class ProviderReply:
    output: dict[str, Any]
    usage: dict[str, Any] | None = None
    actual_cost_usd: str | None = None
    cost_method: str | None = None
```

`EvaluationStore(repo: Repository)` exposes:

```python
create(request: EvaluationRequest, *, blocked_reason: str | None = None) -> dict
get(run_id: str) -> dict                     # KeyError when absent
list_runs(limit: int = 50) -> list[dict]      # newest first; 1 <= limit <= 100
claim(run_id: str, owner_pid: int, owner_birth: float) -> bool
finish(run_id: str, status: str, *, result: dict | None = None,
       usage: dict | None = None, actual_cost_usd: str | None = None,
       cost_method: str | None = None, error_category: str | None = None,
       safe_error: str | None = None) -> dict
active() -> dict | None
```

`create` returns the existing run for the same request key and same input/policy/scope;
it raises `ValueError` for reuse with different content. Only creation with
`blocked_reason` produces `blocked`; normal creation produces `queued`. `claim` is an
atomic queued→running update. `finish` allows running→succeeded/partial/failed and
queued→failed for dispatch failure; other transitions raise `ValueError`.

## Task 1: Add schema, serialization and packaged migration

**Files:** Create `ai/__init__.py`, `ai/contracts.py`, `ai/schema.sql`,
`tests/ai_support.py`, `tests/test_ai_storage.py`; modify `storage/repository.py`, `pyproject.toml`.

**Interfaces:** Consumes `Repository.initialize()` and `_connect()`; produces dataclasses above,
`canonical_json(value: dict) -> str`, and the two tables.

- [ ] **Step 1: Write migration/serialization regressions.** Define a reusable request fixture
  in `tests/ai_support.py` (no production keys, calls or disk evidence required):

```python
from hashlib import sha256
from casual_scout.ai.contracts import EvaluationRequest

def request(key="request-1"):
    return EvaluationRequest(
        request_key=key, analysis_date="2026-09-25", markets=("vn",),
        provider_id=None, model_id=None, prompt_version="p4-v1",
        prompt_hash=sha256(b"p4-v1").hexdigest(), schema_version="1",
        canonical_input={"messages": [], "manifest": {}}, evidence=(),
        policy={"enabled": False, "max_cost_per_run_usd": None},
    )
```

```python
def test_additive_idempotent_migration(tmp_path):
    from casual_scout.storage import Repository
    repo = Repository(tmp_path)
    repo.initialize()
    with repo._connect() as db:
        before = db.execute("SELECT * FROM markets ORDER BY country").fetchall()
    repo.initialize()
    with repo._connect() as db:
        assert db.execute("SELECT * FROM markets ORDER BY country").fetchall() == before
        names = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"ai_evaluation_runs", "ai_run_evidence"} <= names
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
```

- [ ] **Step 2: Run** `.venv\Scripts\python.exe -m pytest tests/test_ai_storage.py -q`;
  confirm the table assertion fails, not fixture setup.
- [ ] **Step 3: Implement dataclasses and additive SQL.** `canonical_json` is
  `json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)`.
  Persist decimal money as strings; never use binary floats for money. Use this schema:

```sql
CREATE TABLE IF NOT EXISTS ai_evaluation_runs (
 id TEXT PRIMARY KEY, request_key TEXT NOT NULL UNIQUE,
 status TEXT NOT NULL CHECK(status IN ('queued','running','succeeded','partial','failed','blocked')),
 analysis_date TEXT NOT NULL, markets_json TEXT NOT NULL,
 created_at TEXT NOT NULL, started_at TEXT, ended_at TEXT,
 provider_id TEXT, model_id TEXT, prompt_version TEXT NOT NULL,
 prompt_hash TEXT NOT NULL, schema_version TEXT NOT NULL,
 input_json TEXT NOT NULL, input_hash TEXT NOT NULL, policy_json TEXT NOT NULL,
 result_json TEXT, usage_json TEXT, actual_cost_usd TEXT, cost_method TEXT,
 error_category TEXT, safe_error TEXT, owner_pid INTEGER, owner_birth REAL,
 rerun_of TEXT REFERENCES ai_evaluation_runs(id)
);
CREATE UNIQUE INDEX IF NOT EXISTS ai_one_active
 ON ai_evaluation_runs((1)) WHERE status IN ('queued','running');
CREATE INDEX IF NOT EXISTS ai_history ON ai_evaluation_runs(created_at DESC, id DESC);
CREATE TABLE IF NOT EXISTS ai_run_evidence (
 run_id TEXT NOT NULL REFERENCES ai_evaluation_runs(id),
 evidence_id TEXT NOT NULL, analysis_date TEXT NOT NULL,
 country TEXT NOT NULL, app_id TEXT NOT NULL,
 snapshot_id TEXT REFERENCES snapshots(id), analytics_id TEXT,
 metadata_version_id TEXT REFERENCES metadata_versions(id),
 PRIMARY KEY(run_id,evidence_id)
);
```

  Execute this schema after existing initialization SQL. Include `ai/schema.sql` in
  `[tool.setuptools.package-data].casual_scout`; verify it is found using
  `Path(__file__).parents[1] / 'ai' / 'schema.sql'`. No application startup is needed to test.
- [ ] **Step 4: Re-run migration test** and add `canonical_json({'b':2,'a':1}) == '{"a":1,"b":2}'`;
  require `ValueError` for NaN. Verify populated snapshot and analytics fixtures survive initialize twice.
- [ ] **Step 5: Review and checkpoint only task files.** Run `git diff --check`;
  stage only reviewed hunks and use commit message `feat: add isolated AI evaluation schema`
  if committing is authorized. Do not include existing unrelated changes.

## Task 2: Implement immutable lifecycle and safe persistence

**Files:** Modify `ai/contracts.py`, `ai/schema.sql`; create `ai/storage.py`; extend `tests/test_ai_storage.py`.

**Interfaces:** Consumes `EvaluationRequest`, `EvidenceRef`, `canonical_json`; produces all
`EvaluationStore` methods listed above and exceptions `EvaluationBusy(RuntimeError)`.

- [ ] **Step 1: Write lifecycle/immutability tests.**

```python
import pytest
from ai_support import request
from casual_scout.ai.storage import EvaluationStore
from casual_scout.storage import Repository

def test_result_and_unknown_cost_are_preserved(tmp_path):
    repo = Repository(tmp_path); repo.initialize()
    store = EvaluationStore(repo)
    run = store.create(request())
    assert store.create(request())["id"] == run["id"]
    assert store.claim(run["id"], 1234, 1.0)
    assert not store.claim(run["id"], 1234, 1.0)
    stored = store.finish(run["id"], "succeeded", result={"recommendations": []})
    assert stored["actual_cost_usd"] is None
    assert stored["usage"] is None
    with pytest.raises(ValueError):
        store.finish(run["id"], "failed", error_category="timeout")
```

  Add cases: blocked creation with no provider; active-run conflict; changed input under
  same key; canonical input unchanged after mutating the caller's dictionary; linked evidence
  surviving analytics recalculation; negative/nonfinite cost rejected; SQL mutation rejected.
- [ ] **Step 2: Run** `python -m pytest tests/test_ai_storage.py -q` and capture red assertions.
- [ ] **Step 3: Implement short transactions and invariants.** Use `repo._write_connection()`;
  insert run and all evidence in the same transaction. At queued creation also persist
  `owner_pid=os.getpid()` and `owner_birth=psutil.Process().create_time()` so a crash before
  worker dispatch remains recoverable; blocked rows need no owner. Catch the `ai_one_active` conflict as
  `EvaluationBusy`; never swallow unrelated `IntegrityError`. Compute `input_hash` from UTF-8
  canonical input. Decode JSON fields once in `get/list_runs`, exposing `input`, `result`,
  `usage`, `markets`, `policy`, `evidence`; retain scalar timestamps/status/cost fields.
  No network code belongs in this file. USD costs are populated only from a reported USD
  amount or an explicit verified conversion method; otherwise keep them null. Lifecycle claims use:

```sql
UPDATE ai_evaluation_runs SET status='running', started_at=?, owner_pid=?, owner_birth=?
WHERE id=? AND status='queued';
```

  Require `rowcount == 1` for finish transitions. Add SQLite triggers rejecting UPDATE/DELETE
  on terminal runs, DELETE on any run/evidence, updates to input/scope/provider/prompt/policy
  on any run, and evidence UPDATE at all times or INSERT after queued creation. For example:

```sql
CREATE TRIGGER IF NOT EXISTS ai_terminal_immutable
BEFORE UPDATE ON ai_evaluation_runs
WHEN OLD.status IN ('succeeded','partial','failed','blocked')
BEGIN SELECT RAISE(ABORT,'terminal AI run is immutable'); END;
```

  The input trigger compares `OLD.column IS NOT NEW.column` for each frozen field listed
  above; `started_at`, owner fields, status and result fields alone are mutable during execution.
  Reject sensitive dictionary keys recursively (`authorization`, `api_key`, `access_token`,
  `password`, `client_secret`) before persisting. Store only whitelisted provider usage/cost;
  do not persist raw request headers, raw HTTP exceptions or raw provider response envelopes.
  Error text comes from engine-owned fixed messages, not `str(exception)`.
- [ ] **Step 4: Run storage tests**, including direct SQL trigger tests, and existing
  `tests/test_storage.py tests/test_android_batches.py` to verify independent writes still work.
- [ ] **Step 5: Review/checkpoint:** `git diff --check`; commit reviewed hunks as
  `feat: persist immutable AI evaluation lifecycle` when authorized.

## Task 3: Verify backup/restore and ship storage independently

**Files:** Create `tests/test_ai_backup.py`; update this plan's execution checklist only when done.

**Interfaces:** Consumes `create_backup(repo, destination)` and `restore_backup(manifest_path, target_data_dir)`
from `operations/backup.py`, and the storage API; produces a restore regression.

- [ ] **Step 1: Add a self-contained round-trip test.**

```python
from ai_support import request
from casual_scout.ai.storage import EvaluationStore
from casual_scout.operations.backup import create_backup, restore_backup
from casual_scout.storage import Repository

def test_ai_history_backup_round_trip(tmp_path):
    repo = Repository(tmp_path / "data"); repo.initialize()
    store = EvaluationStore(repo)
    run = store.create(request(), blocked_reason="provider_not_configured")
    manifest = create_backup(repo, tmp_path / "backup")
    restored = restore_backup(manifest, tmp_path / "restored")
    assert EvaluationStore(restored).get(run["id"]) == store.get(run["id"])
```

  Add a second case with an actual snapshot and `EvidenceRef` using the existing
  `repo_with_snapshot` setup in `tests/test_backup.py`: use its real raw fixture, not fake
  raw paths from synthetic analysis fixtures; preserve snapshot/metadata foreign keys and hashes.
- [ ] **Step 2: Run** `python -m pytest tests/test_ai_backup.py tests/test_backup.py -q`.
  The existing SQLite online backup may already pass: this is acceptable verification,
  not a reason to invent new backup infrastructure.
- [ ] **Step 3: Verify packaged schema and full regression.** Run
  `python -m pytest -q` and `ruff check src/casual_scout/ai tests/test_ai_storage.py tests/test_ai_backup.py tests/ai_support.py`.
  If Windows temp-directory permissions fail, use a unique ignored `--basetemp .venv/pytest-p41-<run>`
  and `-p no:cacheprovider`; never delete a broad data directory to fix tests.
- [ ] **Step 4: Review/checkpoint:** commit only the regression as
  `test: preserve AI evidence through backup and restore` when authorized. Report P4.1 ready
  for P4.2 without enabling AI or applying a migration to the user's production data manually.

## Self-review / coverage

Storage acceptance 1 → Task 1; 2–5 → Task 2; 6 → Task 3. All later plans use the same
dataclasses and store signatures. No analytics schema redesign, new database, network
provider, secret persistence, automatic pruning or external queue is introduced.
