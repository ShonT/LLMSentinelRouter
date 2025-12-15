# Quick Reference - Testing & Git Hooks

## ⚡ Quick Commands

```bash
# Run all tests (fast)
./run_tests.sh --fast

# Run all tests (verbose)
./run_tests.sh

# Run only unit tests
./run_tests.sh --unit

# View test documentation
cat TESTING.md

# View test summary
cat TEST_SUMMARY.md
```

## 🎯 Test Status

**108 PASSING** | **8 SKIPPED** | **0 FAILING**

All critical functionality tested and working! ✅

## 🔒 Git Pre-Push Hook

**Status**: ✅ Installed and Active

### What it does:
- Runs all 108 tests before push to `main`
- Blocks push if tests fail
- Allows push to feature branches without testing
- Validates requirements.txt exists

### Hook location:
`.git/hooks/pre-push`

### To bypass (not recommended):
```bash
git push --no-verify
```

## 📊 Test Breakdown

| Category | Count | Time | Status |
|----------|-------|------|--------|
| Unit Tests | 88 | 0.5s | ✅ 100% Pass |
| Integration Tests | 20 | 0.5s | ✅ 85% Pass |
| Skipped Tests | 8 | - | ⏭️ Non-Critical |
| **Total** | **116** | **~1s** | **✅ Ready** |

## ✅ Pre-Commit Checklist

Before committing:
- [ ] Run `./run_tests.sh --fast`
- [ ] All tests pass
- [ ] Code formatted
- [ ] No sensitive data in code

Before pushing to main:
- [ ] All commits tested
- [ ] Documentation updated if needed
- [ ] Pre-push hook will run automatically

## 🚨 If Tests Fail

1. Check the error message
2. Run specific test: `python3 -m pytest tests/test_X.py::test_name -v`
3. Fix the issue
4. Re-run tests
5. Commit fix

## 📝 Files Created

- `.git/hooks/pre-push` - Git hook that runs tests
- `run_tests.sh` - Test runner script
- `TESTING.md` - Full testing documentation
- `TEST_SUMMARY.md` - Detailed test status
- `QUICK_REFERENCE.md` - This file

## 🎓 Common Test Commands

```bash
# Run single test file
python3 -m pytest tests/test_budget.py -v

# Run specific test
python3 -m pytest tests/test_budget.py::TestBudgetKillSwitch::test_add_cost -v

# Run tests matching pattern
python3 -m pytest tests/ -k "budget" -v

# Stop on first failure
python3 -m pytest tests/ -x

# Show test durations
python3 -m pytest tests/ --durations=10

# Quiet mode (only failures shown)
python3 -m pytest tests/ -q
```

## 🔧 Troubleshooting

**Tests fail unexpectedly?**
```bash
# Remove test database
rm -f test_sentinelrouter.db

# Clear pytest cache
rm -rf .pytest_cache

# Reinstall dependencies
pip3 install -r requirements.txt
```

**Pre-push hook not running?**
```bash
# Make it executable
chmod +x .git/hooks/pre-push

# Test it manually
.git/hooks/pre-push
```

**Want to skip hook temporarily?**
```bash
git push --no-verify
# Use sparingly! Tests protect code quality
```

## 📞 Support

- Full docs: `TESTING.md`
- Test summary: `TEST_SUMMARY.md`  
- Design doc: `sentinelrouter_design.md`
- Main README: `README.md`

---

**Remember**: The pre-push hook is your friend! It catches issues before they reach main. 🛡️
