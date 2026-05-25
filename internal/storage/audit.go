package storage

import (
	"context"
	"database/sql"
	"time"
)

type CycleDetectionRecord struct {
	SessionID    string
	PromptHash   string
	ResponseHash string
}

type EscalationLogRecord struct {
	SessionID       string
	EscalationRate  float64
	ThresholdBefore float64
	ThresholdAfter  float64
	Reason          string
}

type EscalationTraceRecord struct {
	SessionID       string
	RequestID       string
	ModelUsed       string
	ComplexityScore float64
	ImpactScope     sql.NullString
	Reason          sql.NullString
}

func (s *Store) InsertCycleDetection(ctx context.Context, record CycleDetectionRecord) error {
	_, err := s.db.ExecContext(ctx, `INSERT INTO cycle_detection
		(session_id, prompt_hash, response_hash, timestamp)
		VALUES (?, ?, ?, ?)`,
		record.SessionID, record.PromptHash, record.ResponseHash, time.Now().UTC())
	return err
}

func (s *Store) InsertEscalationLog(ctx context.Context, record EscalationLogRecord) error {
	_, err := s.db.ExecContext(ctx, `INSERT INTO escalation_log
		(session_id, escalation_rate, threshold_before, threshold_after, changed_at, reason)
		VALUES (?, ?, ?, ?, ?, ?)`,
		record.SessionID, record.EscalationRate, record.ThresholdBefore, record.ThresholdAfter, time.Now().UTC(), record.Reason)
	return err
}

func (s *Store) InsertEscalationTrace(ctx context.Context, record EscalationTraceRecord) error {
	_, err := s.db.ExecContext(ctx, `INSERT INTO escalation_traces
		(session_id, request_id, model_used, complexity_score, impact_scope, reason, created_at)
		VALUES (?, ?, ?, ?, ?, ?, ?)`,
		record.SessionID, record.RequestID, record.ModelUsed, record.ComplexityScore,
		record.ImpactScope, record.Reason, time.Now().UTC())
	return err
}
