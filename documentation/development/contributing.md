# Contributing to SentinelRouter

Thank you for your interest in contributing to SentinelRouter! This document provides guidelines and instructions for contributing to the project.

## Development Philosophy

SentinelRouter follows these core principles:

1. **Budget First**: Every feature must consider cost implications and provide mechanisms for budget control.
2. **Defensive Routing**: The system must gracefully handle failures and prevent cascading errors.
3. **Observability**: All routing decisions must be logged, measurable, and auditable.
4. **Simplicity**: Complex logic should be encapsulated behind simple interfaces.

## Getting Started

### Prerequisites

- Python 3.11 or higher
- Git
- Basic understanding of LLM APIs and routing concepts

### Development Environment Setup

1. **Fork and clone the repository**:
   ```bash
   git clone https://github.com/your-username/sentinelrouter.git
   cd sentinelrouter
   ```

2. **Set up virtual environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install development dependencies**:
   ```bash
   pip install -r requirements.txt
   pip install -e .  # Install in development mode
   ```

4. **Configure environment variables**:
   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   ```

5. **Initialize the database**:
   ```bash
   python -c "from sentinelrouter.database import init_db; init_db()"
   ```

6. **Run tests to verify setup**:
   ```bash
   pytest tests/unit/ -v
   ```

## Development Workflow

### 1. Branch Naming

Use descriptive branch names following the pattern:
- `feature/description` for new features
- `fix/description` for bug fixes
- `docs/description` for documentation changes
- `refactor/description` for code refactoring

Examples:
```bash
git checkout -b feature/add-gemini-support
git checkout -b fix/budget-calculation-error
git checkout -b docs/update-api-reference
```

### 2. Code Standards

#### Python Style
- Follow [PEP 8](https://pep8.org/) guidelines
- Use type hints for all function parameters and return values
- Keep functions focused and under 50 lines when possible
- Use descriptive variable and function names

#### Import Organization
```python
# Standard library imports
import os
import sys
from typing import Dict, List, Optional

# Third-party imports
from fastapi import FastAPI
from pydantic import BaseModel

# Local imports
from .budget import Budget
from .clients import BaseLLMClient
```

#### Error Handling
- Use specific exception classes from `sentinelrouter.exceptions`
- Always log errors with appropriate context
- Never swallow exceptions without logging

#### Testing Requirements
- Write tests for new functionality
- Maintain 90%+ test coverage
- Include both unit and integration tests
- Mock external API calls

### 3. Testing

#### Running Tests
```bash
# Run all tests
pytest tests/ -v

# Run unit tests only
pytest tests/unit/ -v

# Run integration tests only
pytest tests/integ/ -v

# Run tests with coverage report
pytest tests/ --cov=sentinelrouter --cov-report=html
```

#### Writing Tests
Example test structure:
```python
import pytest
from unittest.mock import Mock, patch
from sentinelrouter.budget import Budget

class TestBudget:
    """Test suite for Budget class."""
    
    @pytest.fixture
    def budget(self):
        return Budget(max_cost=10.0)
    
    def test_initial_state(self, budget):
        """Test budget initializes with zero cost."""
        assert budget.current_cost == 0.0
        assert budget.max_cost == 10.0
    
    async def test_add_cost(self, budget):
        """Test adding cost increments current cost."""
        await budget.add_cost(2.5)
        assert budget.current_cost == 2.5
```

### 4. Documentation

#### Updating Documentation
- Update relevant documentation when changing functionality
- Ensure all new endpoints are documented in `documentation/api-reference/`
- Keep architecture diagrams current
- Use clear, concise language with examples

#### Building Documentation Locally
The documentation is in Markdown format. To verify links and structure:
```bash
# Check for broken internal links (if you have markdown-link-check installed)
find documentation -name "*.md" -exec markdown-link-check {} \;
```

### 5. Code Review Process

#### Before Submitting a PR
1. **Ensure tests pass**:
   ```bash
   pytest tests/ -xvs
   ```

2. **Check code style**:
   ```bash
   black sentinelrouter/ tests/
   isort sentinelrouter/ tests/
   flake8 sentinelrouter/ tests/
   ```

3. **Update documentation** if needed

4. **Add changelog entry** (if applicable)

#### PR Submission Checklist
- [ ] Tests pass locally
- [ ] Code follows project style guidelines
- [ ] Documentation updated
- [ ] No breaking changes (or documented if intentional)
- [ ] PR description explains changes and motivation

#### Review Process
1. Maintainers will review within 48 hours
2. Address review comments promptly
3. Ensure CI passes before merge
4. Squash commits into logical units before merging

## Areas of Contribution

### High Priority Areas
1. **New LLM Providers**: Add support for additional providers (OpenAI, Cohere, etc.)
2. **Enhanced Monitoring**: Improve dashboard metrics and visualizations
3. **Performance Optimizations**: Reduce latency in routing decisions
4. **Security Improvements**: Audit and enhance security practices

### Good First Issues
Look for issues tagged with:
- `good-first-issue`
- `help-wanted`
- `documentation`

### Feature Requests
Submit feature requests via GitHub Issues with:
- Clear problem statement
- Proposed solution
- Use cases and benefits

## Project Structure

```
sentinelrouter/
├── sentinelrouter/           # Main package
│   ├── schemas/             # Pydantic models for configuration
│   ├── sentinelrouter/      # Core implementation
│   │   ├── budget.py        # Budget kill-switch
│   │   ├── judge.py         # Judge system
│   │   ├── router_logic.py  # Main routing logic
│   │   └── ...              # Other modules
│   └── __init__.py
├── tests/                   # Test suite
│   ├── unit/               # Unit tests
│   ├── integ/              # Integration tests
│   └── scripts/            # Test scripts
├── config/                 # Configuration files
├── documentation/          # Project documentation
└── scripts/                # Utility scripts
```

## Code of Conduct

### Professional Conduct
- Be respectful and inclusive
- Focus on technical merit
- Assume positive intent
- Provide constructive feedback

### Communication
- Use GitHub Issues for bug reports and feature requests
- Use GitHub Discussions for questions and ideas
- Keep conversations professional and on-topic

## Release Process

### Versioning
SentinelRouter follows [Semantic Versioning](https://semver.org/):
- **MAJOR**: Breaking changes
- **MINOR**: New features (backward compatible)
- **PATCH**: Bug fixes

### Release Checklist
1. Update version in `pyproject.toml`
2. Update CHANGELOG.md
3. Run full test suite
4. Build and test Docker image
5. Create GitHub release
6. Update documentation for new version

## Getting Help

### Resources
- [Documentation Index](../index.md) - Main documentation hub
- [API Reference](../api-reference/rest-api.md) - API documentation
- [Architecture Overview](../architecture/overview.md) - System design

### Questions and Support
- Open a [GitHub Discussion](https://github.com/your-org/sentinelrouter/discussions) for questions
- Use [GitHub Issues](https://github.com/your-org/sentinelrouter/issues) for bug reports
- Tag maintainers with `@` mentions for urgent issues

## Acknowledgments

Contributors will be acknowledged in:
- GitHub Contributors page
- Release notes
- Project documentation (for significant contributions)

Thank you for helping make SentinelRouter better!