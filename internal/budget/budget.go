package budget

import (
	"context"
	"fmt"

	"github.com/ShonT/LLMSentinelRouter/internal/storage"
)

type Manager struct {
	store             *storage.Store
	maxCostPerSession float64
}

func NewManager(store *storage.Store, maxCostPerSession float64) *Manager {
	return &Manager{store: store, maxCostPerSession: maxCostPerSession}
}

func (m *Manager) GetOrCreateSession(ctx context.Context, sessionID, clientIP, tier string) (*storage.Session, error) {
	return m.store.GetOrCreateSession(ctx, sessionID, clientIP, tier, m.maxCostPerSession)
}

func (m *Manager) CheckBudget(ctx context.Context, sessionID string, estimatedCost float64) (bool, *storage.Session, error) {
	session, err := m.store.GetOrCreateSession(ctx, sessionID, "", "free", m.maxCostPerSession)
	if err != nil {
		return false, nil, err
	}
	if !session.IsActive {
		return false, session, nil
	}
	return session.CurrentCost+estimatedCost <= session.MaxCostPerSession, session, nil
}

func (m *Manager) RequireBudget(ctx context.Context, sessionID string, estimatedCost float64) (*storage.Session, error) {
	session, err := m.store.GetOrCreateSession(ctx, sessionID, "", "free", m.maxCostPerSession)
	if err != nil {
		return nil, err
	}
	if !session.IsActive {
		return session, fmt.Errorf("budget exceeded for session %s. current cost: %.6f, limit: %.6f", sessionID, session.CurrentCost, session.MaxCostPerSession)
	}
	ok, err := m.store.ReserveBudget(ctx, sessionID, estimatedCost, 3)
	if err != nil {
		return nil, err
	}
	if !ok {
		session, _ = m.store.GetSessionRequired(ctx, sessionID)
		return session, fmt.Errorf("budget exceeded for session %s. current cost: %.6f, limit: %.6f", sessionID, session.CurrentCost, session.MaxCostPerSession)
	}
	return m.store.GetSessionRequired(ctx, sessionID)
}

func (m *Manager) SettleCost(ctx context.Context, sessionID string, reservedCost, actualCost float64) error {
	return m.store.AdjustReservedCost(ctx, sessionID, reservedCost, actualCost)
}

func (m *Manager) AddCost(ctx context.Context, sessionID string, cost float64) error {
	return m.store.AddCost(ctx, sessionID, cost)
}

func (m *Manager) ResetSession(ctx context.Context, sessionID string, maxCost float64) error {
	if maxCost <= 0 {
		maxCost = m.maxCostPerSession
	}
	return m.store.ResetSession(ctx, sessionID, maxCost)
}

func (m *Manager) SetMaxCostPerSession(maxCost float64) {
	if maxCost > 0 {
		m.maxCostPerSession = maxCost
	}
}
