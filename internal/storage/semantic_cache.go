package storage

import (
	"context"
	"database/sql"
	"time"
)

type SemanticCacheStats struct {
	SemanticHash     string
	TotalCalls       int
	WeakCalls        int
	StrongCalls      int
	JudgeInvocations int
	TotalLatencyMS   float64
	TotalCost        float64
	TotalTokens      int
	LastModel        sql.NullString
	LastCalledAt     time.Time
	FirstSeenAt      time.Time
}

func (s *Store) LoadSemanticCacheStats(ctx context.Context) (map[string]*SemanticCacheStats, error) {
	rows, err := s.db.QueryContext(ctx, `SELECT semantic_hash, total_calls, weak_calls, strong_calls,
		judge_invocations, total_latency_ms, total_cost, total_tokens, last_model, last_called_at, first_seen_at
		FROM semantic_cache_stats`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := map[string]*SemanticCacheStats{}
	for rows.Next() {
		var st SemanticCacheStats
		if err := rows.Scan(&st.SemanticHash, &st.TotalCalls, &st.WeakCalls, &st.StrongCalls,
			&st.JudgeInvocations, &st.TotalLatencyMS, &st.TotalCost, &st.TotalTokens,
			&st.LastModel, &st.LastCalledAt, &st.FirstSeenAt); err != nil {
			return nil, err
		}
		cp := st
		out[st.SemanticHash] = &cp
	}
	return out, rows.Err()
}

func (s *Store) UpsertSemanticCacheStats(ctx context.Context, st SemanticCacheStats) error {
	_, err := s.db.ExecContext(ctx, `INSERT INTO semantic_cache_stats
		(semantic_hash, total_calls, weak_calls, strong_calls, judge_invocations,
		 total_latency_ms, total_cost, total_tokens, last_model, last_called_at, first_seen_at)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
		ON CONFLICT(semantic_hash) DO UPDATE SET
			total_calls = excluded.total_calls,
			weak_calls = excluded.weak_calls,
			strong_calls = excluded.strong_calls,
			judge_invocations = excluded.judge_invocations,
			total_latency_ms = excluded.total_latency_ms,
			total_cost = excluded.total_cost,
			total_tokens = excluded.total_tokens,
			last_model = excluded.last_model,
			last_called_at = excluded.last_called_at`,
		st.SemanticHash, st.TotalCalls, st.WeakCalls, st.StrongCalls, st.JudgeInvocations,
		st.TotalLatencyMS, st.TotalCost, st.TotalTokens, st.LastModel, st.LastCalledAt, st.FirstSeenAt,
	)
	return err
}

func (s *Store) ClearSemanticCacheStats(ctx context.Context) error {
	if _, err := s.db.ExecContext(ctx, `DELETE FROM semantic_cache_stats`); err != nil {
		return err
	}
	_, err := s.db.ExecContext(ctx, `DELETE FROM semantic_cache_entries`)
	return err
}

func (s *Store) SemanticCacheSummary(ctx context.Context) (hits, misses, clusters int, err error) {
	if err = s.db.QueryRowContext(ctx, `SELECT COUNT(*) FROM semantic_cache_stats`).Scan(&clusters); err != nil {
		return
	}
	if clusters == 0 {
		return 0, 0, 0, nil
	}
	rows, err := s.db.QueryContext(ctx, `SELECT weak_calls, strong_calls FROM semantic_cache_stats`)
	if err != nil {
		return 0, 0, clusters, err
	}
	defer rows.Close()
	for rows.Next() {
		var weak, strong int
		if err := rows.Scan(&weak, &strong); err != nil {
			return 0, 0, clusters, err
		}
		if weak+strong > 0 {
			hits++
		}
	}
	misses = clusters - hits
	if misses < 0 {
		misses = 0
	}
	return hits, misses, clusters, rows.Err()
}
