# GitHub Actions Workflows

Automated CI/CD pipelines for the Ask Dr. Chaffee project.

## Workflows

### 1. **unit-tests.yml** - Unit Test Runner
**Triggers:** Push/PR to main/develop (Python files only)

**Jobs:**
- `test-windows`: Run unit tests on Windows with coverage
- `test-linux`: Run unit tests on Linux for cross-platform validation

**Features:**
- Coverage reporting to Codecov
- 85% coverage threshold enforcement
- Branch coverage tracking
- Fast feedback (<2 minutes)

**Status Badge:**
```markdown
![Unit Tests](https://github.com/YOUR_ORG/ask-dr-chaffee/actions/workflows/unit-tests.yml/badge.svg)
```

### 2. **code-quality.yml** - Code Quality Checks
**Triggers:** Push/PR to main/develop (Python files)

**Jobs:**
- `lint`: Black formatting + Ruff linting
- `security`: Bandit security scan + dependency vulnerability check
- `type-check`: MyPy type checking (informational)

**Checks:**
- Code formatting (Black)
- Linting rules (Ruff)
- Security vulnerabilities (Bandit)
- Secret detection
- TODO/FIXME tracking

### 3. **pr-checks.yml** - Pull Request Validation
**Triggers:** PR opened/updated

**Jobs:**
- `pr-validation`: PR title format, test coverage check, file size validation
- `test-coverage-diff`: Coverage comparison with base branch

**Features:**
- Conventional commit format enforcement
- Test coverage warnings
- Large file detection
- PR summary generation
- Coverage diff comments

### 4. **nightly-full-tests.yml** - Comprehensive Test Suite
**Triggers:** Daily at 2 AM UTC + manual dispatch

**Jobs:**
- `full-test-suite`: All tests with performance benchmarks
- `dependency-audit`: Security audit of dependencies

**Features:**
- Full test suite execution
- Performance benchmarking
- Coverage HTML reports (30-day retention)
- Dependency vulnerability scanning
- Failure notifications

## Setup Instructions

### 1. Enable GitHub Actions
Actions are automatically enabled for the repository.

### 2. Add Secrets
Go to **Settings → Secrets and variables → Actions** and add:

- `CODECOV_TOKEN`: Get from [codecov.io](https://codecov.io)
  ```
  1. Sign up at codecov.io with GitHub
  2. Add repository
  3. Copy upload token
  4. Add as CODECOV_TOKEN secret
  ```

### 3. Configure Branch Protection
**Settings → Branches → Add rule** for `main`:

- ✅ Require status checks to pass before merging
  - `test-windows`
  - `test-linux`
  - `lint`
  - `security`
- ✅ Require branches to be up to date
- ✅ Require linear history
- ✅ Include administrators

### 4. Enable Codecov Integration
1. Visit [codecov.io/gh/YOUR_ORG/ask-dr-chaffee](https://codecov.io)
2. Enable repository
3. Add `codecov.yml` configuration (optional)

### 5. Add Status Badges to README
```markdown
# Ask Dr. Chaffee

![Unit Tests](https://github.com/YOUR_ORG/ask-dr-chaffee/actions/workflows/unit-tests.yml/badge.svg)
![Code Quality](https://github.com/YOUR_ORG/ask-dr-chaffee/actions/workflows/code-quality.yml/badge.svg)
[![codecov](https://codecov.io/gh/YOUR_ORG/ask-dr-chaffee/branch/main/graph/badge.svg)](https://codecov.io/gh/YOUR_ORG/ask-dr-chaffee)
```

## Workflow Triggers

### Automatic Triggers
- **Push to main/develop**: Runs unit tests + code quality
- **Pull Request**: Runs all checks + coverage diff
- **Daily 2 AM UTC**: Runs full test suite + dependency audit

### Manual Triggers
```bash
# Trigger nightly tests manually
gh workflow run nightly-full-tests.yml

# View workflow runs
gh run list --workflow=unit-tests.yml

# Watch a specific run
gh run watch
```

## Coverage Requirements

- **Minimum**: 85% line + branch coverage
- **Target**: 90% line + branch coverage
- **Enforcement**: CI fails if below 85%

## Performance Benchmarks

Nightly tests track:
- Test execution time (target: <2s for unit tests)
- Slowest tests (top 20)
- Coverage trends
- Dependency vulnerabilities

## Troubleshooting

### Tests Fail in CI but Pass Locally
```bash
# Run tests with same environment as CI
$env:PYTHONPATH = "$PWD;$PWD\backend"
pytest tests/unit/test_ingest_*.py -m unit -v
```

### Coverage Below Threshold
```bash
# Generate coverage report locally
pytest tests/unit/test_ingest_*.py -m unit --cov=backend/scripts/ingest_youtube_enhanced.py --cov-branch --cov-report=html
start htmlcov/index.html
```

### Linting Failures
```bash
# Auto-fix formatting
black backend/scripts/ tests/unit/

# Check linting
ruff check backend/scripts/ tests/unit/

# Auto-fix linting
ruff check --fix backend/scripts/ tests/unit/
```

### Security Scan Failures
```bash
# Run Bandit locally
pip install bandit
bandit -r backend/scripts/

# Check dependencies
pip install safety
safety check
```

## Notifications

### Slack Integration (Optional)
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

### Email Notifications
GitHub sends email notifications automatically for:
- Workflow failures
- First failure after success
- Fixed workflows

Configure in **Settings → Notifications**.

## Maintenance

### Update Dependencies
```bash
# Update test dependencies
pip install --upgrade pytest pytest-cov pytest-mock

# Update requirements.txt
pip freeze > backend/requirements.txt
```

### Add New Workflows
1. Create `.github/workflows/new-workflow.yml`
2. Test locally with [act](https://github.com/nektos/act)
3. Push and verify in Actions tab

### Monitor Costs
- GitHub Actions: 2,000 minutes/month free (public repos unlimited)
- Codecov: Free for open source
- View usage: **Settings → Billing → Actions**

## Best Practices

✅ **Keep workflows fast** (<5 minutes for unit tests)  
✅ **Use caching** for dependencies  
✅ **Fail fast** on critical errors  
✅ **Parallel jobs** for independent tasks  
✅ **Informational checks** don't block PRs  
✅ **Clear error messages** for failures  
✅ **Artifacts** for debugging (coverage reports, logs)  

## Resources

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Codecov Documentation](https://docs.codecov.com)
- [pytest Documentation](https://docs.pytest.org)
- [Ruff Documentation](https://docs.astral.sh/ruff/)
