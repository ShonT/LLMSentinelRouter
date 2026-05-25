package storage

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"math"
)

const budgetEpsilon = 0.0001

func (s *Store) TryReserveBudget(ctx context.Context, sessionID string, estimatedCost float64) (bool, error) {
	result, err := s.db.ExecContext(ctx, `UPDATE sessions
		SET current_cost = current_cost + ?, version = version + 1
		WHERE session_id = ? AND is_active = 1 AND current_cost + ? <= max_cost_per_session`,
		estimatedCost, sessionID, estimatedCost,
	)
	if err != nil {
		return false, err
	}
	rows, err := result.RowsAffected()
	if err != nil {
		return false, err
	}
	return rows == 1, nil
}

func (s *Store) AdjustReservedCost(ctx context.Context, sessionID string, reservedCost, actualCost float64) error {
	diff := actualCost - reservedCost
	if math.Abs(diff) < budgetEpsilon {
		return nil
	}
	if diff < 0 {
		_, err := s.db.ExecContext(ctx, `UPDATE sessions
			SET current_cost = CASE WHEN current_cost + ? < 0 THEN 0 ELSE current_cost + ? END,
			    version = version + 1
			WHERE session_id = ?`, diff, diff, sessionID)
		return err
	}
	result, err := s.db.ExecContext(ctx, `UPDATE sessions
		SET current_cost = current_cost + ?, version = version + 1
		WHERE session_id = ? AND is_active = 1 AND current_cost + ? <= max_cost_per_session`,
		diff, sessionID, diff,
	)
	if err != nil {
		return err
	}
	rows, err := result.RowsAffected()
	if err != nil {
		return err
	}
	if rows != 1 {
		return fmt.Errorf("budget adjustment failed for session %s", sessionID)
	}
	return nil
}

func (s *Store) ReserveBudget(ctx context.Context, sessionID string, estimatedCost float64, maxRetries int) (bool, error) {
	if maxRetries <= 0 {
		maxRetries = 3
	}
	var lastErr error
	for attempt := 0; attempt < maxRetries; attempt++ {
		ok, err := s.TryReserveBudget(ctx, sessionID, estimatedCost)
		if err != nil {
			return false, err
		}
		if ok {
			return true, nil
		}
		session, found, err := s.GetSession(ctx, sessionID)
		if err != nil {
			return false, err
		}
		if !found {
			return false, sql.ErrNoRows
		}
		if !session.IsActive {
			return false, nil
		}
		if session.CurrentCost+estimatedCost > session.MaxCostPerSession {
			return false, nil
		}
		lastErr = errors.New("budget reservation conflict")
	}
	if lastErr != nil {
		return false, lastErr
	}
	return false, nil
}
