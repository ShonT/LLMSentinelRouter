package metrics

import (
	"encoding/json"
	"os"
	"path/filepath"
	"sync"
	"time"
)

type Collector struct {
	mu     sync.Mutex
	path   string
	recent []map[string]any
	limit  int
}

func NewCollector(path string) *Collector {
	if path == "" {
		path = "./data/metrics/metrics.jsonl"
	}
	_ = os.MkdirAll(filepath.Dir(path), 0o755)
	return &Collector{path: path, limit: 1000}
}

func (c *Collector) Record(eventType string, data map[string]any) {
	if data == nil {
		data = map[string]any{}
	}
	data["type"] = eventType
	data["timestamp"] = time.Now().UnixNano() / int64(time.Millisecond)
	encoded, _ := json.Marshal(data)
	c.mu.Lock()
	defer c.mu.Unlock()
	c.recent = append(c.recent, data)
	if len(c.recent) > c.limit {
		c.recent = c.recent[len(c.recent)-c.limit:]
	}
	file, err := os.OpenFile(c.path, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o644)
	if err == nil {
		_, _ = file.Write(append(encoded, '\n'))
		_ = file.Close()
	}
}

func (c *Collector) Recent(limit int) []map[string]any {
	c.mu.Lock()
	defer c.mu.Unlock()
	if limit <= 0 || limit > len(c.recent) {
		limit = len(c.recent)
	}
	out := make([]map[string]any, 0, limit)
	for _, item := range c.recent[len(c.recent)-limit:] {
		copyItem := map[string]any{}
		for k, v := range item {
			copyItem[k] = v
		}
		out = append(out, copyItem)
	}
	return out
}

func (c *Collector) Reset() error {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.recent = nil
	return os.Remove(c.path)
}
