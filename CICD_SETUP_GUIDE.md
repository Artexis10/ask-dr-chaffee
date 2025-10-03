# CI/CD Setup Guide

Complete guide to setting up the CI/CD pipeline for Ask Dr. Chaffee.

## Overview

The CI/CD pipeline includes:
- ✅ **Automated unit tests** on every push/PR
- ✅ **Code quality checks** (linting, formatting, security)
- ✅ **Coverage tracking** with Codecov
- ✅ **PR validation** with conventional commits
- ✅ **Nightly full test suite** with performance benchmarks
- ✅ **Pre-commit hooks** for local validation

## Quick Setup (5 minutes)

### 1. Enable GitHub Actions
GitHub Actions are automatically enabled for the repository. No action needed.

### 2. Set Up Codecov
```bash
# 1. Visit https://codecov.io and sign in with GitHub
# 2. Add the repository
# 3. Copy the upload token
# 4. Add to GitHub Secrets:
#    Settings → Secrets and variables → Actions → New repository secret
#    Name: CODECOV_TOKEN
#    Value: <paste token>
```

### 3. Install Pre-commit Hooks (Local)
```powershell
# Install pre-commit
pip install pre-commit

# Install hooks
pre-commit install

# Test hooks
pre-commit run --all-files
```

### 4. Configure Branch Protection
**Settings → Branches → Add rule** for `main`:

Required status checks:
- ✅ `test-windows` (Unit Tests)
- ✅ `test-linux` (Unit Tests)
- ✅ `lint` (Code Quality)
- ✅ `security` (Security Scan)
- ✅ `pr-validation` (PR Checks)

Additional settings:
- ✅ Require branches to be up to date before merging
- ✅ Require linear history
- ✅ Include administrators

### 5. Add Status Badges to README
```markdown
# Ask Dr. Chaffee

![Unit Tests](https://github.com/YOUR_ORG/ask-dr-chaffee/actions/workflows/unit-tests.yml/badge.svg)
![Code Quality](https://github.com/YOUR_ORG/ask-dr-chaffee/actions/workflows/code-quality.yml/badge.svg)
[![codecov](https://codecov.io/gh/YOUR_ORG/ask-dr-chaffee/branch/main/graph/badge.svg)](https://codecov.io/gh/YOUR_ORG/ask-dr-chaffee)
![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)
```

## Workflows Explained

### 1. Unit Tests (`unit-tests.yml`)
**Triggers:** Push/PR to main/develop

**What it does:**
- Runs all unit tests on Windows and Linux
- Generates coverage report
- Uploads to Codecov
- Enforces 85% coverage threshold

**Duration:** ~2 minutes

**Failure reasons:**
- Tests fail
- Coverage below 85%
- Import errors

### 2. Code Quality (`code-quality.yml`)
**Triggers:** Push/PR to main/develop

**What it does:**
- Checks code formatting (Black)
- Lints code (Ruff)
- Scans for security issues (Bandit)
- Detects secrets
- Type checking (informational)

**Duration:** ~1 minute

**Failure reasons:**
- Formatting issues
- Linting errors
- Security vulnerabilities
- Secrets detected

### 3. PR Checks (`pr-checks.yml`)
**Triggers:** Pull request opened/updated

**What it does:**
- Validates PR title (conventional commits)
- Checks for test coverage
- Detects large files
- Generates coverage diff
- Comments on PR with coverage changes

**Duration:** ~2 minutes

**Failure reasons:**
- Invalid PR title format
- Coverage decreased significantly

### 4. Nightly Full Tests (`nightly-full-tests.yml`)
**Triggers:** Daily at 2 AM UTC + manual

**What it does:**
- Runs full test suite
- Generates performance benchmarks
- Audits dependencies for vulnerabilities
- Creates coverage HTML report

**Duration:** ~10 minutes

**Failure reasons:**
- Any test failures
- Dependency vulnerabilities

## Local Development Workflow

### Before Committing
```powershell
# 1. Run tests locally
pytest tests/unit/test_ingest_*.py -m unit -v

# 2. Check coverage
pytest tests/unit/test_ingest_*.py -m unit --cov=backend/scripts/ingest_youtube_enhanced.py --cov-branch --cov-report=term-missing

# 3. Format code
black backend/scripts/ tests/unit/

# 4. Lint code
ruff check --fix backend/scripts/ tests/unit/

# 5. Run pre-commit hooks
pre-commit run --all-files
```

### Creating a Pull Request
```bash
# 1. Create feature branch
git checkout -b feat/my-feature

# 2. Make changes and commit
git add .
git commit -m "feat: add new feature"

# 3. Push and create PR
git push origin feat/my-feature
gh pr create --title "feat: add new feature" --body "Description"
```

### PR Title Format
Use [Conventional Commits](https://www.conventionalcommits.org/):

- `feat: add new feature`
- `fix: resolve bug in ingestion`
- `docs: update README`
- `test: add unit tests for config`
- `refactor: simplify cleanup logic`
- `perf: optimize GPU telemetry`
- `chore: update dependencies`

## Monitoring & Maintenance

### View Workflow Runs
```bash
# List recent runs
gh run list

# View specific workflow
gh run list --workflow=unit-tests.yml

# Watch a run in real-time
gh run watch

# View logs
gh run view <run-id> --log
```

### Check Coverage Trends
Visit: `https://codecov.io/gh/YOUR_ORG/ask-dr-chaffee`

**Key metrics:**
- Overall coverage percentage
- Coverage trend (increasing/decreasing)
- Uncovered lines
- Coverage by file

### Monitor Test Performance
Nightly tests track:
- Test execution time
- Slowest tests
- Flaky tests
- Coverage changes

View in: **Actions → Nightly Full Test Suite → Latest run**

### Dependency Security
```bash
# Manual dependency audit
pip install pip-audit
pip-audit

# Check for outdated packages
pip list --outdated

# Update dependencies
pip install --upgrade <package>
```

## Troubleshooting

### Tests Pass Locally but Fail in CI
**Cause:** Environment differences

**Solution:**
```powershell
# Match CI environment
$env:PYTHONPATH = "$PWD;$PWD\backend"
pytest tests/unit/test_ingest_*.py -m unit -v

# Check Python version
python --version  # Should be 3.12

# Clear cache
pytest --cache-clear
```

### Coverage Below Threshold
**Cause:** New code not covered by tests

**Solution:**
```bash
# Generate coverage report
pytest tests/unit/test_ingest_*.py -m unit --cov=backend/scripts/ingest_youtube_enhanced.py --cov-branch --cov-report=html

# Open report
start htmlcov/index.html

# Add tests for uncovered lines
```

### Linting Failures
**Cause:** Code doesn't meet style guidelines

**Solution:**
```bash
# Auto-fix formatting
black backend/scripts/ tests/unit/

# Auto-fix linting
ruff check --fix backend/scripts/ tests/unit/

# Check remaining issues
ruff check backend/scripts/ tests/unit/
```

### Security Scan Failures
**Cause:** Potential security vulnerabilities

**Solution:**
```bash
# Run Bandit locally
pip install bandit
bandit -r backend/scripts/

# Check specific file
bandit backend/scripts/ingest_youtube_enhanced.py

# Suppress false positives (add comment)
# nosec
```

### Pre-commit Hook Failures
**Cause:** Local validation failed

**Solution:**
```bash
# Skip hooks (not recommended)
git commit --no-verify

# Fix issues and retry
pre-commit run --all-files

# Update hooks
pre-commit autoupdate
```

## Advanced Configuration

### Custom Workflow Triggers
Edit `.github/workflows/*.yml`:

```yaml
on:
  push:
    branches: [ main, develop, feature/* ]
    paths:
      - 'backend/**/*.py'
      - 'tests/**/*.py'
  pull_request:
    branches: [ main ]
  workflow_dispatch:  # Manual trigger
```

### Parallel Test Execution
Add to `pytest.ini`:

```ini
[pytest]
addopts = -n auto  # Use all CPU cores
```

Install:
```bash
pip install pytest-xdist
```

### Slack Notifications
Add to workflow:

```yaml
- name: Notify Slack
  if: failure()
  uses: slackapi/slack-github-action@v1
  with:
    webhook-url: ${{ secrets.SLACK_WEBHOOK }}
    payload: |
      {
        "text": "❌ Tests failed on ${{ github.ref }}"
      }
```

### Custom Coverage Thresholds
Edit `codecov.yml`:

```yaml
coverage:
  status:
    project:
      default:
        target: 90%  # Increase threshold
        threshold: 1%  # Stricter tolerance
```

## Cost & Limits

### GitHub Actions
- **Public repos:** Unlimited minutes
- **Private repos:** 2,000 minutes/month free
- **Additional:** $0.008/minute

**Current usage:** ~5 minutes per push (unit tests + quality checks)

### Codecov
- **Open source:** Free unlimited
- **Private repos:** Free for 1 user, paid plans available

### Storage
- **Artifacts:** 500 MB free, 90-day retention
- **Logs:** Unlimited, 90-day retention

## Best Practices

✅ **Keep workflows fast** (<5 minutes for critical path)  
✅ **Use caching** for dependencies  
✅ **Fail fast** on critical errors  
✅ **Parallel jobs** for independent tasks  
✅ **Clear error messages** in failures  
✅ **Artifacts for debugging** (coverage, logs)  
✅ **Informational checks** don't block merges  
✅ **Regular maintenance** (update dependencies, hooks)  

## Next Steps

1. ✅ **Set up Codecov** (5 minutes)
2. ✅ **Configure branch protection** (2 minutes)
3. ✅ **Install pre-commit hooks** (1 minute)
4. ✅ **Add status badges** (1 minute)
5. ✅ **Create first PR** to test pipeline
6. 📊 **Monitor coverage trends** weekly
7. 🔧 **Tune thresholds** based on project needs

## Resources

- [GitHub Actions Docs](https://docs.github.com/en/actions)
- [Codecov Docs](https://docs.codecov.com)
- [Pre-commit Docs](https://pre-commit.com)
- [Conventional Commits](https://www.conventionalcommits.org)
- [pytest Docs](https://docs.pytest.org)

---

**Questions?** Open an issue or check `.github/workflows/README.md`
