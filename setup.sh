#!/bin/bash
# Quick setup and verification script for SentinelRouter (Go implementation)

set -euo pipefail

echo "=================================================="
echo "SentinelRouter - Setup & Verification"
echo "=================================================="
echo ""

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "Checking Go toolchain..."
if ! command -v go >/dev/null 2>&1; then
    echo -e "${RED}Go is required but was not found on PATH.${NC}"
    exit 1
fi
go version
echo ""

echo "Checking environment configuration..."
if [ ! -f .env ] && [ -f .env.example ]; then
    echo -e "${YELLOW}No .env file found. Creating from .env.example...${NC}"
    cp .env.example .env
    echo -e "${YELLOW}Edit .env and add provider API keys before live provider calls.${NC}"
fi
echo ""

echo "Downloading dependencies..."
go mod download
echo -e "${GREEN}Dependencies ready.${NC}"
echo ""

echo "Running tests..."
go test ./...
echo ""

echo "Building binary..."
mkdir -p bin
go build -o bin/sentinelrouter ./cmd/sentinelrouter
echo ""

echo -e "${GREEN}=================================================="
echo "Setup Complete"
echo -e "==================================================${NC}"
echo ""
echo "Next steps:"
echo "1. Start the server:"
echo "   ./bin/sentinelrouter"
echo ""
echo "2. Or run without building:"
echo "   go run ./cmd/sentinelrouter"
echo ""
echo "3. Build and run with Docker:"
echo "   docker-compose up --build"
echo ""
