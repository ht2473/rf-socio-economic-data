# Changelog

All notable changes to this repository are documented here.  
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

## [1.1.0] — 2026-05-14

### Fixed
- `scripts/03_explore.py` — critical index-alignment bug in `example_grp`,
  `example_wages`, `example_population`: boolean masks were built from the
  unfiltered `df` and applied to `_valid(df)`, causing `IndexError` or
  silently wrong results on certain data slices
- `scripts/02_validate.py` — `data_profile.md` reported
  `regions_full.parquet` as source even when run in `--sample-only` mode;
  source field now reflects the actual file used
- `README.md` — corrected `git clone` URL (was `russia-regions-dataset`,
  is `rf-socio-economic-data`)
- `LICENSE` — added author name to copyright line
- `.github/workflows/validate.yml` — added `cache-dependency-path` for
  reliable pip caching; added smoke-test step for `01_process.py --help`

### Changed
- `Makefile` — added `INPUT ?=` variable; `make processed INPUT=path/to/file.parquet`
  now works as documented in CONTRIBUTING
- `requirements.txt` — runtime only (`pandas`, `pyarrow`); Jupyter and dev
  tools moved to new `requirements-dev.txt`
- `CONTRIBUTING.md` — added development setup section with `ruff` instructions

## [1.0.0] — 2026-03-13

### Added
- Initial repository release based on «Если быть точным» dataset v3.0 (13.03.2026)
- `scripts/01_process.py` — ETL pipeline with PyArrow backend, CLI, zstd compression,
  streaming CSV, and generation of `sections.parquet` reference table
- `scripts/02_validate.py` — quality checks with structured pass/warn/fail output,
  `--sample-only` mode for CI, `--fail-on-warn` strict mode
- `scripts/03_explore.py` — CLI with sub-commands: `examples`, `search`, `info`
- `Makefile` — reproducible pipeline (`make all`, `make validate`, `make search Q=...`)
- `.github/workflows/validate.yml` — GitHub Actions CI on push/PR/weekly schedule
- `notebooks/explore.ipynb` — Jupyter notebook with 7 analysis sections (GitHub-renderable)
- `data/processed/sections.parquet/.csv` — section-level coverage reference (117 rows)
- `data/processed/catalogue.parquet/.csv` — indicator reference (1 294 rows)
- `data/processed/objects.parquet/.csv` — territory reference (98 rows)
- `data/samples/regions_sample_1000.*` — 1 000-row stratified sample (parquet + CSV)
- `CONTRIBUTING.md` — update guide for new Rosstat releases
- `CHANGELOG.md` — this file

### Dataset version (upstream)
- Source: Росстат / «Если быть точным» v3.0 (13.03.2026)
- 1 969 010 rows · 1 294 indicators · 87 regions · 2001–2025

---

## Upstream dataset history (from «Если быть точным»)

| Date       | Version | Changes |
|------------|---------|---------|
| 21.08.2023 | 1.0     | Initial release |
| 27.03.2024 | 1.1     | Added 2022 data |
| 07.06.2024 | 2.0     | Added 18 Rosstat collections; added `source` attribute and XLSX format |
| 05.06.2025 | 2.1     | Added 2023 and 2024 data |
| 13.03.2026 | 3.0     | Unified indicator names; replaced source codes with stable external codes; removed partial duplicates; added `version_date`; added 2025 data for 10 collections |
