# CI/CD Pipeline Quick Reference

## 🚀 What's Implemented

### Automated Workflows
- ✅ **Unit Tests** - Windows + Linux (every push/PR)
- ✅ **Code Quality** - Linting, formatting, security (every push/PR)
- ✅ **PR Validation** - Title format, coverage diff (every PR)
- ✅ **Nightly Tests** - Full suite + benchmarks (daily 2 AM UTC)

### Local Development
- ✅ **Pre-commit Hooks** - Fast tests + secret detection
- ✅ **Coverage Tracking** - 85% minimum threshold
- ✅ **Auto-formatting** - Black + Ruff

## ⚡ Quick Commands

### Run Tests Locally
```powershell
# All unit tests
.\backend\venv\Scripts\python.exe -m pytest tests/unit/test_ingest_*.py -m unit -v

# With coverage
.\backend\venv\Scripts\python.exe -m pytest tests/unit/test_ingest_*.py -m unit --cov=backend/scripts/ingest_youtube_enhanced.py --cov-branch --cov-report=term-missing

# Fast subset (pre-commit)
.\backend\venv\Scripts\python.exe -m pytest tests/unit/test_ingest_subprocess.py tests/unit/test_ingest_config.py -m unit -q
```

### Format & Lint
```powershell
# Auto-format
black backend/scripts/ tests/unit/

# Lint
ruff check --fix backend/scripts/ tests/unit/

# Pre-commit hooks
pre-commit run --all-files
```

### Create PR
```bash
git checkout -b feat/my-feature
git add .
git commit -m "feat: add new feature"
git push origin feat/my-feature
gh pr create --title "feat: add new feature"
```

## 📊 Status Checks

All PRs must pass:
- ✅ `test-windows` - Unit tests on Windows
- ✅ `test-linux` - Unit tests on Linux
- ✅ `lint` - Code formatting & linting
- ✅ `security` - Security scan
- ✅ `pr-validation` - PR format validation

## 📈 Coverage Requirements

- **Minimum:** 85% line + branch coverage
- **Target:** 90% line + branch coverage
- **Current:** ~85-90% for ingest_youtube_enhanced.py

## 🔧 Setup (First Time)

1. **Install pre-commit hooks**
   ```powershell
   pip install pre-commit
   pre-commit install
   ```

2. **Set up Codecov** (maintainers only)
   - Visit https://codecov.io
   - Add repository
   - Add `CODECOV_TOKEN` to GitHub Secrets

3. **Configure branch protection** (maintainers only)
   - Settings → Branches → Add rule for `main`
   - Require status checks

## 📝 PR Title Format

Use [Conventional Commits](https://www.conventionalcommits.org/):

- `feat: add new feature`
- `fix: resolve bug`
- `docs: update documentation`
- `test: add unit tests`
- `refactor: simplify code`
- `perf: optimize performance`
- `chore: update dependencies`

## 🐛 Troubleshooting

### Tests fail in CI but pass locally
```powershell
$env:PYTHONPATH = "$PWD;$PWD\backend"
pytest tests/unit/test_ingest_*.py -m unit -v
```

### Coverage below threshold
```powershell
pytest tests/unit/test_ingest_*.py -m unit --cov=backend/scripts/ingest_youtube_enhanced.py --cov-branch --cov-report=html
start htmlcov/index.html
```

### Linting failures
```powershell
black backend/scripts/ tests/unit/
ruff check --fix backend/scripts/ tests/unit/
```

## 📚 Full Documentation

- **Setup Guide:** `CICD_SETUP_GUIDE.md`
- **Implementation Details:** `CICD_IMPLEMENTATION_SUMMARY.md`
- **Workflow Docs:** `.github/workflows/README.md`
- **Test Guide:** `tests/unit/README.md`

## 🎯 Key Files

```
.github/
├── workflows/
│   ├── unit-tests.yml          # Main test runner
│   ├── code-quality.yml        # Linting & security
│   ├── pr-checks.yml           # PR validation
│   └── nightly-full-tests.yml  # Nightly suite
├── PULL_REQUEST_TEMPLATE.md    # PR template
└── ISSUE_TEMPLATE/             # Issue templates

codecov.yml                      # Coverage config
.pre-commit-config.yaml          # Pre-commit hooks
pytest.ini                       # Pytest config
```

## ✅ Quick Checklist

Before pushing:
- [ ] Tests pass locally
- [ ] Coverage ≥85%
- [ ] Code formatted (Black)
- [ ] No linting errors (Ruff)
- [ ] Pre-commit hooks pass
- [ ] Conventional commit message

## 🚦 Pipeline Status

View workflow runs: **Repository → Actions tab**

- Green ✅ = All checks passed
- Red ❌ = Check failed (click for details)
- Yellow 🟡 = In progress

---

**Questions?** See `CICD_SETUP_GUIDE.md` or open an issue.
