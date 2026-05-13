# Contributing Guide

## How to update when a new Rosstat release appears

«Если быть точным» typically publishes updates once or twice a year.
When a new parquet appears at https://tochno.st/datasets/regions_collection,
follow these steps:

### 1. Download the new raw file

```bash
# Example — replace filename with the actual new version
wget -P data/raw/ https://tochno.st/.../<new_file>.parquet
```

### 2. Run the pipeline against the new file

```bash
make processed INPUT=data/raw/<new_file>.parquet
# or with explicit path via script directly:
python scripts/01_process.py --input data/raw/<new_file>.parquet
```

### 3. Validate

```bash
make validate
```

Review `docs/data_profile.md`. Check:
- Row count increased (or is explained if not)
- Year range extended
- No new `fail` checks appeared

### 4. Update CHANGELOG.md

Add an entry under `[Unreleased]`:

```markdown
## [Unreleased]

### Changed
- Updated to upstream dataset vX.Y (YYYY-MM-DD)
- Row count: 1,969,010 → X,XXX,XXX
- Year range extended to 202X
```

### 5. Commit

```bash
git add data/processed/ data/samples/ docs/data_profile.md CHANGELOG.md
git commit -m "data: update to upstream v3.1 (YYYY-MM-DD)"
git push
```

> **Note:** `data/raw/` and `data/processed/regions_full.parquet` are in `.gitignore`
> and are NOT committed. Only lightweight reference files and samples go to git.

---

## Repository conventions

- **Branch names:** `feat/...`, `fix/...`, `data/...`
- **Commit messages:** follow [Conventional Commits](https://www.conventionalcommits.org/)
- **Python style:** PEP 8; type hints on all public functions; checked with `ruff`
- **Scripts:** always runnable from the repo root; support `--help`

## Development setup

```bash
pip install -r requirements-dev.txt   # includes jupyter + ruff
ruff check scripts/                   # lint
ruff check --fix scripts/             # auto-fix
```

## Reporting issues

If you find a data quality issue, please open a GitHub Issue with:
1. The indicator code(s) affected
2. The region and year
3. What value you see vs. what you expect
4. The Rosstat source (if known)

Data issues that originate from Rosstat itself should also be reported upstream
at https://tochno.st/datasets/regions_collection.
