package provider

// StreamChunk is a normalized token from an upstream provider stream.
type StreamChunk struct {
	Content string
	Done    bool
	Usage   *Usage
}

// StreamHandler receives chunks during streaming; return non-nil error to abort.
type StreamHandler func(chunk StreamChunk) error
