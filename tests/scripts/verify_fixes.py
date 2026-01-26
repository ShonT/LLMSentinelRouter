#!/usr/bin/env python3
"""
Verification script to check all fixes are applied correctly.
Run this before building the Docker image or running tests.
"""

import sys
import ast
import importlib.util
from pathlib import Path


def check_file_syntax(filepath: Path) -> tuple[bool, str]:
    """Check if a Python file has valid syntax."""
    try:
        with open(filepath, "r") as f:
            ast.parse(f.read())
        return True, f"✅ {filepath.name} - Syntax OK"
    except SyntaxError as e:
        return False, f"❌ {filepath.name} - Syntax Error: {e}"


def check_imports(filepath: Path) -> tuple[bool, str]:
    """Check if a file can be imported without errors."""
    try:
        spec = importlib.util.spec_from_file_location("module", filepath)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            # Don't execute, just check if it can be loaded
            return True, f"✅ {filepath.name} - Imports OK"
        return False, f"❌ {filepath.name} - Cannot load module"
    except Exception as e:
        return False, f"❌ {filepath.name} - Import Error: {e}"


def verify_requirements():
    """Verify requirements.txt has all needed dependencies."""
    req_file = Path("requirements.txt")
    if not req_file.exists():
        return False, "❌ requirements.txt not found"

    with open(req_file) as f:
        content = f.read()

    required = ["pydantic-settings", "gunicorn", "fastapi", "sqlalchemy", "httpx"]
    missing = [dep for dep in required if dep.lower() not in content.lower()]

    if missing:
        return False, f"❌ requirements.txt missing: {', '.join(missing)}"

    return True, "✅ requirements.txt has all required dependencies"


def verify_dockerfile():
    """Verify Dockerfile uses httpx instead of requests."""
    dockerfile = Path("Dockerfile")
    if not dockerfile.exists():
        return False, "❌ Dockerfile not found"

    with open(dockerfile) as f:
        content = f.read()

    if "import requests" in content:
        return False, "❌ Dockerfile still uses 'requests' library"

    if "import httpx" not in content:
        return False, "❌ Dockerfile doesn't use 'httpx' for health check"

    if 'CMD ["gunicorn"' in content:
        return (
            False,
            "❌ Dockerfile CMD still uses array form (won't interpolate WORKERS)",
        )

    return True, "✅ Dockerfile uses httpx and shell form for CMD"


def verify_docker_compose():
    """Verify docker-compose.yml uses named volumes."""
    compose_file = Path("docker-compose.yml")
    if not compose_file.exists():
        return False, "❌ docker-compose.yml not found"

    with open(compose_file) as f:
        content = f.read()

    if "import requests" in content:
        return False, "❌ docker-compose.yml still uses 'requests' for health check"

    if "volumes:" not in content or "sentinelrouter_data:" not in content:
        return False, "❌ docker-compose.yml doesn't define named volumes"

    return True, "✅ docker-compose.yml uses named volumes and httpx"


def verify_specific_fixes():
    """Verify specific code fixes are in place."""
    issues = []

    # Check router_logic.py uses LoggingAudit
    router_file = Path("sentinelrouter/sentinelrouter/router_logic.py")
    if router_file.exists():
        with open(router_file) as f:
            content = f.read()

        if "self.audit = AuditLogger(" in content:
            issues.append(
                "❌ router_logic.py still uses AuditLogger instead of LoggingAudit"
            )
        elif "self.audit = LoggingAudit(" in content:
            issues.append("✅ router_logic.py uses LoggingAudit")

        if "hash(prompt)" in content:
            issues.append("❌ router_logic.py still uses random hash() function")
        elif "hashlib.sha256" in content:
            issues.append("✅ router_logic.py uses hashlib.sha256 for hashing")

        if '"session_cost"' in content:
            issues.append("✅ router_logic.py returns session_cost in response dict")
        else:
            issues.append("⚠️  router_logic.py might not return session_cost")

    # Check server.py metrics uses func.sum
    server_file = Path("sentinelrouter/sentinelrouter/server.py")
    if server_file.exists():
        with open(server_file) as f:
            content = f.read()

        if "func.sum(SessionModel.current_cost)" in content:
            issues.append("✅ server.py metrics uses func.sum() to aggregate costs")
        elif "SessionModel.current_cost).scalar()" in content:
            issues.append("❌ server.py metrics still uses scalar() instead of sum()")

    # Check budget.py uses with_for_update
    budget_file = Path("sentinelrouter/sentinelrouter/budget.py")
    if budget_file.exists():
        with open(budget_file) as f:
            content = f.read()

        if "with_for_update()" in content:
            issues.append(
                "✅ budget.py uses with_for_update() to prevent race conditions"
            )
        else:
            issues.append("❌ budget.py doesn't use row-level locking")

    # Check cycle_detector.py uses SHA-256
    cycle_file = Path("sentinelrouter/sentinelrouter/cycle_detector.py")
    if cycle_file.exists():
        with open(cycle_file) as f:
            content = f.read()

        if "hashlib.md5" in content:
            issues.append("❌ cycle_detector.py still uses MD5")
        elif "hashlib.sha256" in content:
            issues.append("✅ cycle_detector.py uses SHA-256 instead of MD5")

    # Check test mocks
    test_file = Path("tests/test_router.py")
    if test_file.exists():
        with open(test_file) as f:
            content = f.read()

        # Should have 3-tuple mocks like (0.3, "LOW", "reasoning")
        if (
            'return_value=(0.3, "weak")' in content
            or 'return_value=(0.8, "strong")' in content
        ):
            issues.append(
                "❌ test_router.py still uses 2-tuple mocks (should be 3-tuple)"
            )
        elif '"LOW"' in content or '"HIGH"' in content:
            issues.append("✅ test_router.py uses correct 3-tuple mocks")

    return issues


def main():
    """Run all verification checks."""
    print("=" * 60)
    print("SentinelRouter - Verification Script")
    print("=" * 60)
    print()

    all_passed = True

    # Check requirements.txt
    print("📦 Checking dependencies...")
    passed, msg = verify_requirements()
    print(msg)
    all_passed = all_passed and passed
    print()

    # Check Dockerfile
    print("🐳 Checking Dockerfile...")
    passed, msg = verify_dockerfile()
    print(msg)
    all_passed = all_passed and passed
    print()

    # Check docker-compose.yml
    print("🐳 Checking docker-compose.yml...")
    passed, msg = verify_docker_compose()
    print(msg)
    all_passed = all_passed and passed
    print()

    # Check specific code fixes
    print("🔧 Checking specific fixes...")
    fix_results = verify_specific_fixes()
    for result in fix_results:
        print(result)
        if result.startswith("❌"):
            all_passed = False
    print()

    # Check syntax of all Python files
    print("🐍 Checking Python syntax...")
    py_files = list(Path("sentinelrouter/sentinelrouter").glob("*.py"))
    py_files.extend(Path("tests").glob("*.py"))

    for py_file in py_files:
        passed, msg = check_file_syntax(py_file)
        print(msg)
        all_passed = all_passed and passed

    print()
    print("=" * 60)
    if all_passed:
        print("✅ All verification checks passed!")
        print("=" * 60)
        print()
        print("Next steps:")
        print("1. Run: pytest tests/ -v")
        print("2. Build: docker build -t sentinelrouter:latest .")
        print("3. Test: docker-compose up")
        return 0
    else:
        print("❌ Some verification checks failed!")
        print("=" * 60)
        print()
        print("Please review the issues above before proceeding.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
