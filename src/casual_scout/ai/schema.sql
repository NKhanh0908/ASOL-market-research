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
CREATE TABLE IF NOT EXISTS ai_run_evidence_seals (
 run_id TEXT PRIMARY KEY REFERENCES ai_evaluation_runs(id)
);
INSERT OR IGNORE INTO ai_run_evidence_seals(run_id)
 SELECT id FROM ai_evaluation_runs;
CREATE TRIGGER IF NOT EXISTS ai_terminal_immutable
BEFORE UPDATE ON ai_evaluation_runs
WHEN OLD.status IN ('succeeded','partial','failed','blocked')
BEGIN SELECT RAISE(ABORT,'terminal AI run is immutable'); END;
CREATE TRIGGER IF NOT EXISTS ai_run_frozen_fields
BEFORE UPDATE ON ai_evaluation_runs
WHEN OLD.id IS NOT NEW.id OR OLD.request_key IS NOT NEW.request_key
 OR OLD.analysis_date IS NOT NEW.analysis_date OR OLD.markets_json IS NOT NEW.markets_json
 OR OLD.created_at IS NOT NEW.created_at OR OLD.provider_id IS NOT NEW.provider_id
 OR OLD.model_id IS NOT NEW.model_id OR OLD.prompt_version IS NOT NEW.prompt_version
 OR OLD.prompt_hash IS NOT NEW.prompt_hash OR OLD.schema_version IS NOT NEW.schema_version
 OR OLD.input_json IS NOT NEW.input_json OR OLD.input_hash IS NOT NEW.input_hash
 OR OLD.policy_json IS NOT NEW.policy_json OR OLD.rerun_of IS NOT NEW.rerun_of
BEGIN SELECT RAISE(ABORT,'AI run input is immutable'); END;
CREATE TRIGGER IF NOT EXISTS ai_run_valid_transition
BEFORE UPDATE ON ai_evaluation_runs
WHEN NOT ((OLD.status='queued' AND NEW.status IN ('running','failed'))
 OR (OLD.status='running' AND NEW.status IN ('succeeded','partial','failed')))
BEGIN SELECT RAISE(ABORT,'invalid AI run transition'); END;
CREATE TRIGGER IF NOT EXISTS ai_run_no_delete
BEFORE DELETE ON ai_evaluation_runs
BEGIN SELECT RAISE(ABORT,'AI run cannot be deleted'); END;
CREATE TRIGGER IF NOT EXISTS ai_evidence_no_late_insert
BEFORE INSERT ON ai_run_evidence
WHEN EXISTS (SELECT 1 FROM ai_run_evidence_seals WHERE run_id=NEW.run_id)
 OR NOT EXISTS (SELECT 1 FROM ai_evaluation_runs WHERE id=NEW.run_id AND status IN ('queued','blocked'))
BEGIN SELECT RAISE(ABORT,'AI evidence is sealed'); END;
CREATE TRIGGER IF NOT EXISTS ai_evidence_no_update
BEFORE UPDATE ON ai_run_evidence
BEGIN SELECT RAISE(ABORT,'AI evidence is immutable'); END;
CREATE TRIGGER IF NOT EXISTS ai_evidence_no_delete
BEFORE DELETE ON ai_run_evidence
BEGIN SELECT RAISE(ABORT,'AI evidence cannot be deleted'); END;
CREATE TRIGGER IF NOT EXISTS ai_seal_no_update
BEFORE UPDATE ON ai_run_evidence_seals
BEGIN SELECT RAISE(ABORT,'AI evidence seal is immutable'); END;
CREATE TRIGGER IF NOT EXISTS ai_seal_no_delete
BEFORE DELETE ON ai_run_evidence_seals
BEGIN SELECT RAISE(ABORT,'AI evidence seal cannot be deleted'); END;
