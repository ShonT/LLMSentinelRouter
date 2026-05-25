package storage

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"time"

	_ "modernc.org/sqlite"
)

type Store struct {
	db *sql.DB
}

type Session struct {
	SessionID         string
	ClientIP          sql.NullString
	Tier              string
	CreatedAt         time.Time
	MaxCostPerSession float64
	CurrentCost       float64
	IsActive          bool
	Version           int
}

type RoutingDecision struct {
	DecisionID       int64
	SessionID        string
	RequestID        string
	Timestamp        time.Time
	ModelUsed        string
	ComplexityScore  float64
	CostIncurred     float64
	CostSource       string
	ComputedCost     sql.NullFloat64
	PromptHash       string
	ImpactScope      sql.NullString
	Reason           sql.NullString
	InputTokens      int
	OutputTokens     int
	TotalTokens      int
	RequestLatencyMS float64
	ModelLatencyMS   float64
	JudgeLatencyMS   sql.NullFloat64
}

type MetricsSummary struct {
	RequestsTotal  int
	SessionsTotal  int
	CostTotal      float64
	EscalationRate float64
	StrongRequests int
	WeakRequests   int
}

func Open(ctx context.Context, databaseURL string) (*Store, error) {
	path, err := sqlitePath(databaseURL)
	if err != nil {
		return nil, err
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return nil, err
	}
	db, err := sql.Open("sqlite", path+"?_pragma=busy_timeout(5000)&_pragma=journal_mode(WAL)")
	if err != nil {
		return nil, err
	}
	db.SetMaxOpenConns(10)
	db.SetMaxIdleConns(5)
	db.SetConnMaxIdleTime(5 * time.Minute)
	if err := db.PingContext(ctx); err != nil {
		_ = db.Close()
		return nil, err
	}
	store := &Store{db: db}
	if err := store.Init(ctx); err != nil {
		_ = db.Close()
		return nil, err
	}
	return store, nil
}

func (s *Store) Close() error {
	return s.db.Close()
}

func (s *Store) Init(ctx context.Context) error {
	statements := []string{
		`CREATE TABLE IF NOT EXISTS sessions (
			session_id TEXT PRIMARY KEY,
			client_ip TEXT,
			tier TEXT NOT NULL DEFAULT 'free',
			created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
			max_cost_per_session REAL NOT NULL DEFAULT 10.0,
			current_cost REAL NOT NULL DEFAULT 0.0,
			is_active INTEGER NOT NULL DEFAULT 1,
			version INTEGER NOT NULL DEFAULT 0
		)`,
		`CREATE TABLE IF NOT EXISTS routing_decisions (
			decision_id INTEGER PRIMARY KEY AUTOINCREMENT,
			session_id TEXT NOT NULL,
			request_id TEXT UNIQUE NOT NULL,
			timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
			model_used TEXT,
			complexity_score REAL,
			cost_incurred REAL,
			cost_source TEXT DEFAULT 'unknown',
			computed_cost REAL,
			prompt_hash TEXT,
			impact_scope TEXT,
			reason TEXT,
			input_tokens INTEGER DEFAULT 0,
			output_tokens INTEGER DEFAULT 0,
			total_tokens INTEGER DEFAULT 0,
			request_latency_ms REAL DEFAULT 0.0,
			model_latency_ms REAL DEFAULT 0.0,
			judge_latency_ms REAL,
			FOREIGN KEY(session_id) REFERENCES sessions(session_id)
		)`,
		`CREATE TABLE IF NOT EXISTS cycle_detection (
			hash_id INTEGER PRIMARY KEY AUTOINCREMENT,
			session_id TEXT NOT NULL,
			prompt_hash TEXT,
			response_hash TEXT,
			timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
			FOREIGN KEY(session_id) REFERENCES sessions(session_id)
		)`,
		`CREATE TABLE IF NOT EXISTS escalation_log (
			log_id INTEGER PRIMARY KEY AUTOINCREMENT,
			session_id TEXT NOT NULL,
			escalation_rate REAL,
			threshold_before REAL,
			threshold_after REAL,
			changed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
			reason TEXT,
			FOREIGN KEY(session_id) REFERENCES sessions(session_id)
		)`,
		`CREATE TABLE IF NOT EXISTS semantic_cache_entries (
			entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
			semantic_hash TEXT,
			context_hash TEXT,
			prompt_preview TEXT,
			response_preview TEXT,
			latency_ms REAL DEFAULT 0.0,
			judge_invoked INTEGER DEFAULT 1,
			judge_latency_ms REAL,
			model_used TEXT,
			complexity_score REAL,
			impact_scope TEXT,
			cost REAL DEFAULT 0.0,
			total_tokens INTEGER DEFAULT 0,
			created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
		)`,
		`CREATE TABLE IF NOT EXISTS semantic_cache_stats (
			semantic_hash TEXT PRIMARY KEY,
			total_calls INTEGER DEFAULT 0,
			weak_calls INTEGER DEFAULT 0,
			strong_calls INTEGER DEFAULT 0,
			judge_invocations INTEGER DEFAULT 0,
			total_latency_ms REAL DEFAULT 0.0,
			total_latency_ms_sq REAL DEFAULT 0.0,
			total_cost REAL DEFAULT 0.0,
			total_tokens INTEGER DEFAULT 0,
			last_model TEXT,
			last_called_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
			first_seen_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
		)`,
		`CREATE TABLE IF NOT EXISTS escalation_traces (
			trace_id INTEGER PRIMARY KEY AUTOINCREMENT,
			session_id TEXT NOT NULL,
			request_id TEXT,
			model_used TEXT,
			complexity_score REAL,
			impact_scope TEXT,
			reason TEXT,
			created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
			FOREIGN KEY(session_id) REFERENCES sessions(session_id)
		)`,
		`CREATE TABLE IF NOT EXISTS app_state (
			key TEXT PRIMARY KEY,
			value TEXT NOT NULL,
			updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
		)`,
		`CREATE INDEX IF NOT EXISTS ix_routing_decisions_session ON routing_decisions(session_id)`,
		`CREATE INDEX IF NOT EXISTS ix_semantic_cache_entries_hash ON semantic_cache_entries(semantic_hash, created_at)`,
	}
	for _, stmt := range statements {
		if _, err := s.db.ExecContext(ctx, stmt); err != nil {
			return err
		}
	}
	return nil
}

func (s *Store) GetOrCreateSession(ctx context.Context, sessionID, clientIP, tier string, maxCost float64) (*Session, error) {
	session, found, err := s.GetSession(ctx, sessionID)
	if err != nil {
		return nil, err
	}
	if found {
		return session, nil
	}
	if tier == "" {
		tier = "free"
	}
	now := time.Now().UTC()
	_, err = s.db.ExecContext(ctx, `INSERT INTO sessions
		(session_id, client_ip, tier, created_at, max_cost_per_session, current_cost, is_active, version)
		VALUES (?, ?, ?, ?, ?, 0.0, 1, 0)`,
		sessionID, nullableString(clientIP), tier, now, maxCost,
	)
	if err != nil {
		if strings.Contains(strings.ToLower(err.Error()), "constraint") {
			return s.GetOrCreateSession(ctx, sessionID, clientIP, tier, maxCost)
		}
		return nil, err
	}
	return s.GetSessionRequired(ctx, sessionID)
}

func (s *Store) GetSessionRequired(ctx context.Context, sessionID string) (*Session, error) {
	session, found, err := s.GetSession(ctx, sessionID)
	if err != nil {
		return nil, err
	}
	if !found {
		return nil, sql.ErrNoRows
	}
	return session, nil
}

func (s *Store) GetSession(ctx context.Context, sessionID string) (*Session, bool, error) {
	row := s.db.QueryRowContext(ctx, `SELECT session_id, client_ip, tier, created_at,
		max_cost_per_session, current_cost, is_active, version
		FROM sessions WHERE session_id = ?`, sessionID)
	var session Session
	var active int
	if err := row.Scan(&session.SessionID, &session.ClientIP, &session.Tier, &session.CreatedAt,
		&session.MaxCostPerSession, &session.CurrentCost, &active, &session.Version); err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, false, nil
		}
		return nil, false, err
	}
	session.IsActive = active != 0
	return &session, true, nil
}

func (s *Store) AddCost(ctx context.Context, sessionID string, cost float64) error {
	_, err := s.db.ExecContext(ctx, `UPDATE sessions
		SET current_cost = current_cost + ?, version = version + 1
		WHERE session_id = ?`, cost, sessionID)
	return err
}

func (s *Store) DeactivateSession(ctx context.Context, sessionID string) error {
	_, err := s.db.ExecContext(ctx, `UPDATE sessions SET is_active = 0 WHERE session_id = ?`, sessionID)
	return err
}

func (s *Store) ResetSession(ctx context.Context, sessionID string, maxCost float64) error {
	_, err := s.db.ExecContext(ctx, `UPDATE sessions
		SET current_cost = 0.0, max_cost_per_session = ?, is_active = 1, version = version + 1
		WHERE session_id = ?`, maxCost, sessionID)
	return err
}

func (s *Store) InsertRoutingDecision(ctx context.Context, d RoutingDecision) error {
	_, err := s.db.ExecContext(ctx, `INSERT INTO routing_decisions
		(session_id, request_id, timestamp, model_used, complexity_score, cost_incurred, cost_source,
		 computed_cost, prompt_hash, impact_scope, reason, input_tokens, output_tokens, total_tokens,
		 request_latency_ms, model_latency_ms, judge_latency_ms)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
		d.SessionID, d.RequestID, d.Timestamp, d.ModelUsed, d.ComplexityScore, d.CostIncurred,
		d.CostSource, d.ComputedCost, d.PromptHash, d.ImpactScope, d.Reason, d.InputTokens,
		d.OutputTokens, d.TotalTokens, d.RequestLatencyMS, d.ModelLatencyMS, d.JudgeLatencyMS,
	)
	return err
}

func (s *Store) RoutingDecisionsBySession(ctx context.Context, sessionID string) ([]RoutingDecision, error) {
	rows, err := s.db.QueryContext(ctx, `SELECT decision_id, session_id, request_id, timestamp,
		model_used, complexity_score, cost_incurred, cost_source, computed_cost, prompt_hash,
		impact_scope, reason, input_tokens, output_tokens, total_tokens, request_latency_ms,
		model_latency_ms, judge_latency_ms
		FROM routing_decisions WHERE session_id = ? ORDER BY timestamp`, sessionID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []RoutingDecision
	for rows.Next() {
		var d RoutingDecision
		if err := rows.Scan(&d.DecisionID, &d.SessionID, &d.RequestID, &d.Timestamp,
			&d.ModelUsed, &d.ComplexityScore, &d.CostIncurred, &d.CostSource, &d.ComputedCost,
			&d.PromptHash, &d.ImpactScope, &d.Reason, &d.InputTokens, &d.OutputTokens,
			&d.TotalTokens, &d.RequestLatencyMS, &d.ModelLatencyMS, &d.JudgeLatencyMS); err != nil {
			return nil, err
		}
		out = append(out, d)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	return out, nil
}

func (s *Store) RecentRoutingDecisions(ctx context.Context, limit int) ([]RoutingDecision, error) {
	if limit <= 0 {
		limit = 50
	}
	rows, err := s.db.QueryContext(ctx, `SELECT decision_id, session_id, request_id, timestamp,
		model_used, complexity_score, cost_incurred, cost_source, computed_cost, prompt_hash,
		impact_scope, reason, input_tokens, output_tokens, total_tokens, request_latency_ms,
		model_latency_ms, judge_latency_ms
		FROM routing_decisions ORDER BY timestamp DESC LIMIT ?`, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []RoutingDecision
	for rows.Next() {
		var d RoutingDecision
		if err := rows.Scan(&d.DecisionID, &d.SessionID, &d.RequestID, &d.Timestamp,
			&d.ModelUsed, &d.ComplexityScore, &d.CostIncurred, &d.CostSource, &d.ComputedCost,
			&d.PromptHash, &d.ImpactScope, &d.Reason, &d.InputTokens, &d.OutputTokens,
			&d.TotalTokens, &d.RequestLatencyMS, &d.ModelLatencyMS, &d.JudgeLatencyMS); err != nil {
			return nil, err
		}
		out = append(out, d)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	return out, nil
}

func (s *Store) ClearRoutingDecisions(ctx context.Context) error {
	_, err := s.db.ExecContext(ctx, `DELETE FROM routing_decisions`)
	return err
}

func (s *Store) MetricsSummary(ctx context.Context, strongModels map[string]bool) (MetricsSummary, error) {
	var summary MetricsSummary
	if err := s.db.QueryRowContext(ctx, `SELECT COUNT(*) FROM sessions`).Scan(&summary.SessionsTotal); err != nil {
		return summary, err
	}
	if err := s.db.QueryRowContext(ctx, `SELECT COUNT(*) FROM routing_decisions`).Scan(&summary.RequestsTotal); err != nil {
		return summary, err
	}
	if err := s.db.QueryRowContext(ctx, `SELECT COALESCE(SUM(current_cost), 0) FROM sessions`).Scan(&summary.CostTotal); err != nil {
		return summary, err
	}
	rows, err := s.db.QueryContext(ctx, `SELECT model_used FROM routing_decisions`)
	if err != nil {
		return summary, err
	}
	defer rows.Close()
	for rows.Next() {
		var model string
		if err := rows.Scan(&model); err != nil {
			return summary, err
		}
		if strongModels[model] {
			summary.StrongRequests++
		} else {
			summary.WeakRequests++
		}
	}
	if err := rows.Err(); err != nil {
		return summary, err
	}
	if summary.RequestsTotal > 0 {
		summary.EscalationRate = float64(summary.StrongRequests) / float64(summary.RequestsTotal)
	}
	return summary, nil
}

func DataDir(databaseURL string) string {
	path, err := sqlitePath(databaseURL)
	if err != nil || path == "" {
		return "./data"
	}
	dir := filepath.Dir(path)
	if dir == "" || dir == "." {
		return "./data"
	}
	return dir
}

func sqlitePath(databaseURL string) (string, error) {
	if databaseURL == "" {
		return "./data/sentinelrouter.db", nil
	}
	if strings.HasPrefix(databaseURL, "sqlite:///") {
		return strings.TrimPrefix(databaseURL, "sqlite:///"), nil
	}
	if strings.HasPrefix(databaseURL, "sqlite://") {
		parsed, err := url.Parse(databaseURL)
		if err != nil {
			return "", err
		}
		if parsed.Path != "" {
			return parsed.Path, nil
		}
		return parsed.Host, nil
	}
	if strings.HasPrefix(databaseURL, "file:") || strings.HasSuffix(databaseURL, ".db") {
		return strings.TrimPrefix(databaseURL, "file:"), nil
	}
	return "", fmt.Errorf("unsupported database url %q", databaseURL)
}

func nullableString(value string) sql.NullString {
	return sql.NullString{String: value, Valid: value != ""}
}
