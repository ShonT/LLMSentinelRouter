package config

import (
	"crypto/sha256"
	"os"
	"sync"
	"time"
)

type Manager struct {
	settings Settings
	mu       sync.RWMutex
	config   *SentinelConfig
	source   string
	digest   [32]byte
}

func NewManager(settings Settings) (*Manager, error) {
	m := &Manager{settings: settings}
	if err := m.ForceReload(); err != nil {
		return nil, err
	}
	return m, nil
}

func (m *Manager) Current() *SentinelConfig {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return m.config
}

func (m *Manager) Source() string {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return m.source
}

func (m *Manager) ForceReload() error {
	cfg, source, err := LoadRuntimeConfig(m.settings)
	if err != nil {
		return err
	}
	digest := m.currentDigest()
	m.mu.Lock()
	defer m.mu.Unlock()
	m.config = cfg
	m.source = source
	m.digest = digest
	return nil
}

func (m *Manager) ReloadIfChanged() (bool, error) {
	digest := m.currentDigest()
	m.mu.RLock()
	same := digest == m.digest
	m.mu.RUnlock()
	if same {
		return false, nil
	}
	if err := m.ForceReload(); err != nil {
		return false, err
	}
	return true, nil
}

func (m *Manager) Watch(stop <-chan struct{}, interval time.Duration) {
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		select {
		case <-stop:
			return
		case <-ticker.C:
			_, _ = m.ReloadIfChanged()
		}
	}
}

func (m *Manager) currentDigest() [32]byte {
	path := m.settings.SentinelConfigPath
	if _, err := os.Stat(path); err != nil {
		path = m.settings.ModelsConfigPath
	}
	data, err := os.ReadFile(path)
	if err != nil {
		return [32]byte{}
	}
	return sha256.Sum256(data)
}
