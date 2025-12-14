# Testing

## Overview

SentinelRouter employs a comprehensive testing strategy to ensure reliability, correctness, and maintainability across all four architectural modules. The test suite follows the **Testing Pyramid** model with unit tests forming the foundation, integration tests validating module interactions, and end‑to‑end tests confirming system‑level behavior.

### Testing Philosophy

- **Module‑first testing**: Each architectural module (A‑D) has dedicated unit tests.
- **Real‑world scenarios**: Integration tests simulate production traffic patterns.
- **Cost‑safety**: Tests never call paid APIs unless explicitly configured for integration testing.
- **Fast feedback**: Unit tests run in milliseconds; integration tests under 30 seconds.

## Running Tests

### Prerequisites

Ensure you have the testing dependencies installed:

```bash
pip install pytest pytest-asyncio pytest-cov pytest-mock
```

### Running All Tests

Execute the complete test suite:

```bash
# Run all tests (unit + integration)
pytest

# With verbose output
pytest -v

# With coverage report
pytest --cov=sentinelrouter --cov-report=html
```

### Running Test Categories

#### Unit Tests Only
```bash
pytest tests/unit/ -v
```

#### Integration Tests Only
```bash
pytest tests/integ/ -v
```

#### API Tests Only
```bash
pytest tests/api/ -v
```

#### Script Tests Only
```bash
pytest tests/scripts/ -v
```

### Running Specific Test Files

```bash
# Test budget module (Module A)
pytest tests/unit/test_budget.py -v

# Test judge module (Module B)  
pytest tests/unit/test_judge.py -v

# Test cycle detector (Module D)
pytest tests/unit/test_cycle_detector.py -v
```

### Running with Docker

For consistent testing environments:

```bash
# Build test image
docker build -t sentinelrouter-test -f Dockerfile.test .

# Run tests in container
docker run --rm sentinelrouter-test
```

## Test Organization

The test suite is organized by testing level and architectural module:

```
tests/
├── unit/                          # Unit tests (fast, isolated)
│   ├── test_budget.py            # Module A: Budget kill‑switch
│   ├── test_judge.py             # Module B: Stingy judge
│   ├── test_threshold.py         # Module C: Dynamic thresholding
│   ├── test_cycle_detector.py    # Module D: Cycle detection
│   ├── test_semantic_cache.py    # Semantic caching
│   ├── test_clients.py           # LLM client wrappers
│   ├── test_config_models.py     # Pydantic configuration models
│   ├── test_state_manager.py     # State management
│   └── test_session_defaults.py  # Session defaults
├── integ/                         # Integration tests
│   └── test_backup_weak_models_demo.py  # Backup weak models demo
├── api/                           # API tests
│   └── test_server.py            # FastAPI server endpoints
├── scripts/                       # Script tests
│   ├── test_dashboard.py         # Dashboard functionality
│   ├── test_metrics.py           # Metrics collection
│   └── test_roo_client.py        # Roo client integration
└── conftest.py                    # Shared pytest fixtures
```

## Writing Unit Tests

### Test Structure

Each unit test follows the AAA pattern (Arrange‑Act‑Assert):

```python
def test_function_behavior():
    # Arrange: Set up test data and dependencies
    input_data = "test input"
    expected_output = "expected result"
    
    # Act: Execute the code under test
    actual_output = function_under_test(input_data)
    
    # Assert: Verify the outcome
    assert actual_output == expected_output
```

### Async Test Pattern

For asynchronous functions:

```python
import pytest

@pytest.mark.asyncio
async def test_async_function():
    # Arrange
    mock_client = AsyncMock(return_value="response")
    
    # Act  
    result = await async_function_under_test(mock_client)
    
    # Assert
    assert result == "expected"
```

### Mocking External Dependencies

Use `unittest.mock` to isolate tests from external systems:

```python
from unittest.mock import Mock, patch, AsyncMock

def test_with_mocks():
    # Mock a database session
    mock_db = Mock()
    mock_db.query.return_value.filter_by.return_value.first.return_value = None
    
    # Mock environment variables
    with patch.dict('os.environ', {'API_KEY': 'test_key'}):
        # Test code that reads environment
        result = function_that_uses_env()
        assert result == 'expected'
```

### Database Testing

Use in‑memory SQLite for database tests:

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

@pytest.fixture
def test_db():
    """Create an in‑memory test database."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    yield db
    db.close()

def test_database_operation(test_db):
    # Use the test database fixture
    obj = Model(name="test")
    test_db.add(obj)
    test_db.commit()
    
    retrieved = test_db.query(Model).filter_by(name="test").first()
    assert retrieved is not None
```

## Writing Integration Tests

Integration tests validate interactions between modules and external services.

### Backup Weak Models Demo

The `test_backup_weak_models_demo.py` demonstrates the failover system:

```python
async def test_backup_weak_models_basic():
    """Test basic failover from primary to backup weak model."""
    # Create registry with primary (failing) and backup (working)
    registry = ModelRegistry()
    
    # Register providers
    registry.register_provider(ModelProvider(
        provider_id="primary",
        tier=ModelTier.WEAK,
        client=MockLLMClient(should_fail=True),
        priority=0
    ))
    registry.register_provider(ModelProvider(
        provider_id="backup",
        tier=ModelTier.WEAK,
        client=MockLLMClient(should_fail=False),
        priority=1
    ))
    
    # Make request - should automatically failover
    response, provider_id = await registry.call_with_failover(
        tier=ModelTier.WEAK,
        messages=[{"role": "user", "content": "test"}],
        max_attempts=2
    )
    
    assert provider_id == "backup"  # Backup was used
    assert "Response from backup" in response.content
```

### Circuit Breaker Testing

Test the circuit breaker pattern for fault tolerance:

```python
async def test_circuit_breaker_opens():
    """Circuit breaker opens after multiple failures."""
    health_tracker = ProviderHealthTracker(
        failure_threshold=3,
        cooldown_seconds=5
    )
    
    # Make repeated failing calls
    for _ in range(3):
        await make_failing_call()
    
    # Circuit should be open
    status = health_tracker.get_status("provider_id")
    assert status['circuit_open'] == True
    assert status['available'] == False
```

## Mocking and Fixtures

### Shared Fixtures (conftest.py)

The `conftest.py` file provides shared fixtures across all tests:

```python
# tests/conftest.py
import pytest
import os

@pytest.fixture(autouse=True)
def mock_environment():
    """Set mock API keys for all tests."""
    os.environ["DEEPSEEK_API_KEY"] = "mock-deepseek-key"
    os.environ["ANTHROPIC_API_KEY"] = "mock-anthropic-key"
    yield
    # Cleanup after test
```

### Custom Fixtures

Create reusable test fixtures:

```python
# tests/unit/conftest.py (if needed)
import pytest
from sentinelrouter.sentinelrouter.budget import BudgetKillSwitch

@pytest.fixture
def budget_manager(test_db):
    """Create a BudgetKillSwitch instance with test database."""
    return BudgetKillSwitch(test_db)

@pytest.fixture
def mock_judge_registry():
    """Create a mock JudgeRegistry."""
    registry = MagicMock()
    registry.judge_with_failover = AsyncMock(
        return_value=(0.5, "MEDIUM", "Test reasoning", "mock-judge")
    )
    return registry
```

## Continuous Integration

SentinelRouter uses GitHub Actions for continuous integration. The workflow runs on every push and pull request.

### CI Pipeline Steps

1. **Install dependencies**: Python 3.10+
2. **Run unit tests**: Fast tests (under 10 seconds)
3. **Run integration tests**: Slower tests (under 30 seconds)
4. **Generate coverage report**: Minimum 80% coverage required
5. **Upload artifacts**: Test reports and coverage

### Viewing CI Results

- GitHub Actions dashboard: `https://github.com/your-org/sentinelrouter/actions`
- Coverage reports: Uploaded as artifacts
- Test results: Available in workflow runs

### Local CI Simulation

Simulate the CI pipeline locally:

```bash
# Install dependencies
pip install -r requirements.txt
pip install -r requirements-test.txt

# Run linters
flake8 sentinelrouter/
mypy sentinelrouter/

# Run tests with coverage
pytest --cov=sentinelrouter --cov-fail-under=80

# Generate HTML report
pytest --cov=sentinelrouter --cov-report=html
```

## Test Coverage

### Coverage Requirements

- **Overall coverage**: ≥ 80% line coverage
- **Critical modules**: ≥ 90% (budget, judge, router logic)
- **New features**: 100% coverage required before merge

### Generating Coverage Reports

```bash
# Generate terminal report
pytest --cov=sentinelrouter --cov-report=term-missing

# Generate HTML report (opens in browser)
pytest --cov=sentinelrouter --cov-report=html
open htmlcov/index.html

# Generate XML for CI tools
pytest --cov=sentinelrouter --cov-report=xml
```

### Coverage Exceptions

Some code paths are excluded from coverage:

```python
# pragma: no cover
def experimental_feature():
    """Experimental code not ready for production."""
    if unreachable_condition:  # pragma: no cover
        handle_edge_case()
```

## Best Practices

### 1. Test Naming
- Use descriptive names: `test_function_behavior_scenario`
- Follow pattern: `test_[unit]_[action]_[expected]`
- Example: `test_budget_check_when_exceeds_limit_returns_false`

### 2. Test Independence
- Each test must run independently
- No test should depend on another test's state
- Use fixtures for shared setup

### 3. Deterministic Tests
- Tests must produce the same result every time
- Avoid randomness in test data
- Mock time‑dependent functions

### 4. Fast Tests
- Unit tests: < 100ms each
- Integration tests: < 2 seconds each
- Use `pytest --durations=10` to identify slow tests

### 5. Meaningful Assertions
- One logical assertion per test
- Include descriptive failure messages
- Use appropriate assertion methods

```python
# Good
assert result == expected, f"Expected {expected}, got {result}"

# Better
pytest.assert(result, expected, "Descriptive message")
```

## Example: Complete Test File

```python
"""
Unit tests for Module A: Budget Kill‑Switch
Tests the budget tracking and enforcement functionality.
"""

import pytest
from unittest.mock import Mock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from sentinelrouter.sentinelrouter.budget import BudgetKillSwitch
from sentinelrouter.sentinelrouter.models import Base, Session as SessionModel


@pytest.fixture
def test_db():
    """Create an in‑memory test database."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    yield db
    db.close()


@pytest.fixture
def budget_manager(test_db):
    """Create a BudgetKillSwitch instance with test database."""
    return BudgetKillSwitch(test_db)


class TestBudgetKillSwitch:
    """Tests for Module A - Budget Kill‑Switch."""
    
    def test_get_or_create_session_new(self, budget_manager, test_db):
        """Test creating a new session."""
        session = budget_manager.get_or_create_session("test_session_1")
        
        assert session.session_id == "test_session_1"
        assert session.current_cost == 0.0
        assert session.max_cost_per_session == 10.0
        assert session.is_active is True
        
        # Verify persistence
        db_session = test_db.query(SessionModel).filter_by(
            session_id="test_session_1"
        ).first()
        assert db_session is not None
    
    def test_check_budget_within_limit(self, budget_manager):
        """Test budget check when cost is within limit."""
        budget_manager.get_or_create_session("test_session_2")
        result = budget_manager.check_budget("test_session_2", 5.0)
        assert result is True
    
    def test_check_budget_exceeds_limit(self, budget_manager):
        """Test budget check when cost would exceed limit."""
        session = budget_manager.get_or_create_session("test_session_3")
        session.max_cost_per_session = 10.0
        session.current_cost = 8.0
        
        result = budget_manager.check_budget("test_session_3", 5.0)
        assert result is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

## Troubleshooting Tests

### Common Issues

| Issue | Solution |
|-------|----------|
| `ImportError` | Ensure `PYTHONPATH` includes project root |
| Database lock errors | Use `:memory:` SQLite or separate test database |
| Async test hangs | Use `pytest-asyncio` and proper `await` |
| Mock not being used | Check import path in `patch()` decorator |
| Environment variables not set | Use `conftest.py` or `monkeypatch` |

### Debugging Tests

```bash
# Run single test with debug output
pytest tests/unit/test_budget.py::TestBudgetKillSwitch::test_check_budget_within_limit -vvs

# Drop into PDB on failure
pytest --pdb

# Show log output during tests
pytest --log-cli-level=DEBUG
```

### Test Isolation

If tests are interfering with each other:

1. Check for global state modifications
2. Ensure each test uses unique session IDs
3. Use `pytest --lf` to run only failed tests
4. Run tests in random order: `pytest --random`

## Related Documentation

- [Architecture Overview](../architecture/overview.md) - Understanding the four modules
- [Configuration Guide](../getting-started/configuration.md) - Test‑specific configuration
- [API Reference](../api-reference/rest-api.md) - Testing API endpoints
- [Contributing Guide](contributing.md) - Test requirements for contributions

---

**Next Steps**:
- Learn about [Adding New Models](adding-new-models.md) and their test requirements
- Explore [Troubleshooting](../operations/troubleshooting.md) for production issues
- Review [Backup and Recovery](../operations/backup-and-recovery.md) for data integrity tests