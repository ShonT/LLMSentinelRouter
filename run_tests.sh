#!/bin/bash
# Test runner script for SentinelRouter (Go implementation)
# Usage: ./run_tests.sh [options]

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}SentinelRouter Test Suite${NC}"
echo ""

# Default: run all tests
if [ $# -eq 0 ]; then
    echo "Running all Go tests..."
    go test ./...
    exit $?
fi

# Parse arguments
case "$1" in
    --unit)
        echo "Running unit tests only..."
        go test ./internal/... ./cmd/...
        ;;
    --integration)
        echo "Running integration/e2e tests..."
        go test ./internal/server
        ;;
    --fast)
        echo "Running quick test suite..."
        go test ./... -count=1
        ;;
    --coverage)
        echo "Running tests with coverage..."
        go test ./... -coverprofile=coverage.out
        go tool cover -func=coverage.out
        ;;
    --help|-h)
        echo "Usage: ./run_tests.sh [option]"
        echo ""
        echo "Options:"
        echo "  (no args)      Run all Go tests"
        echo "  --unit         Run only unit tests"
        echo "  --integration  Run HTTP e2e/integration tests"
        echo "  --fast         Run quick test suite"
        echo "  --coverage     Run tests with coverage report"
        echo "  --help, -h     Show this help message"
        echo ""
        echo "Examples:"
        echo "  ./run_tests.sh              # Run all tests"
        echo "  ./run_tests.sh --unit       # Unit tests only"
        echo "  ./run_tests.sh --fast       # Quick check"
        ;;
    *)
        echo "Unknown option: $1"
        echo "Run './run_tests.sh --help' for usage information"
        exit 1
        ;;
esac
