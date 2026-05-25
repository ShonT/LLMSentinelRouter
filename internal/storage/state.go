package storage

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"time"
)

func (s *Store) LoadState(ctx context.Context, key string, dest any) (bool, error) {
	row := s.db.QueryRowContext(ctx, `SELECT value FROM app_state WHERE key = ?`, key)
	var raw string
	if err := row.Scan(&raw); err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return false, nil
		}
		return false, err
	}
	if err := json.Unmarshal([]byte(raw), dest); err != nil {
		return false, err
	}
	return true, nil
}

func (s *Store) SaveState(ctx context.Context, key string, value any) error {
	raw, err := json.Marshal(value)
	if err != nil {
		return err
	}
	_, err = s.db.ExecContext(ctx, `INSERT INTO app_state (key, value, updated_at)
		VALUES (?, ?, ?)
		ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at`,
		key, string(raw), time.Now().UTC())
	return err
}
