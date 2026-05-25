package semantic

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"math/bits"
	"regexp"
	"strings"
)

var tokenRE = regexp.MustCompile(`[A-Za-z0-9_]+`)

func SimHash(text string) uint64 {
	tokens := tokenRE.FindAllString(strings.ToLower(text), -1)
	var vector [64]int
	for _, token := range tokens {
		sum := sha256.Sum256([]byte(token))
		value := uint64(0)
		for i := 0; i < 8; i++ {
			value = (value << 8) | uint64(sum[i])
		}
		for bit := 0; bit < 64; bit++ {
			if value&(uint64(1)<<bit) != 0 {
				vector[bit]++
			} else {
				vector[bit]--
			}
		}
	}
	var out uint64
	for bit := 0; bit < 64; bit++ {
		if vector[bit] > 0 {
			out |= uint64(1) << bit
		}
	}
	return out
}

func HammingDistance(a, b uint64) int {
	return bits.OnesCount64(a ^ b)
}

func HashPayload(prompt string, context any) string {
	payload := map[string]any{"prompt": strings.TrimSpace(prompt)}
	if context != nil {
		payload["context"] = context
	}
	data, err := json.Marshal(payload)
	if err != nil {
		data = []byte(prompt)
	}
	sum := sha256.Sum256(data)
	return hex.EncodeToString(sum[:])
}
