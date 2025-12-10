#!/bin/bash
# Test runner script for SentinelRouter
# Usage: ./run_tests.sh [options]

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}🧪 SentinelRouter Test Suite${NC}"
echo ""

# Default: run all tests
if [ $# -eq 0 ]; then
    echo "Running all tests..."
    python3 -m pytest tests/ -v
    exit $?
fi

# Parse arguments
case "$1" in
    --unit)
        echo "Running unit tests only..."
        python3 -m pytest tests/test_budget.py tests/test_judge.py tests/test_threshold.py tests/test_cycle_detector.py tests/test_clients.py -v
        ;;
    --integration)
        echo "Running integration tests..."
        python3 -m pytest tests/test_integration.py tests/test_router.py tests/test_server.py -v
        ;;
    --fast)
        echo "Running quick test suite (no output)..."
        python3 -m pytest tests/ -q --tb=no
        ;;
    --coverage)
        echo "Running tests with coverage..."
        python3 -m pytest tests/ --cov=sentinelrouter --cov-report=html --cov-report=term
        ;;
    --help|-h)
        echo "Usage: ./run_tests.sh [option]"
        echo ""
        echo "Options:"
        echo "  (no args)      Run all tests with verbose output"
        echo "  --unit         Run only unit tests"
        echo "  --integration  Run only integration tests"
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
