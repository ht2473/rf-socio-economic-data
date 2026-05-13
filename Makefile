# ============================================================================
# Makefile — Rosstat regional dataset pipeline
# ============================================================================
# Usage:
#   make              — show help
#   make all          — full pipeline: process + validate + notebook
#   make processed    — run ETL only
#   make validate     — run quality checks (requires processed data)
#   make sample       — validate using sample only (fast, no full data needed)
#   make clean        — remove all generated files
#   make install      — install Python dependencies
# ============================================================================

PYTHON      ?= python
RAW_DIR     := data/raw
PROCESSED   := data/processed/regions_full.parquet
CATALOGUE   := data/processed/catalogue.parquet
SAMPLE      := data/samples/regions_sample_1000.parquet
PROFILE     := docs/data_profile.md

.DEFAULT_GOAL := help

# ── Help ─────────────────────────────────────────────────────────────────────

.PHONY: help
help:
	@echo ""
	@echo "  Rosstat Regional Dataset — pipeline targets"
	@echo ""
	@echo "  make install      Install Python dependencies"
	@echo "  make all          Full pipeline (process + validate)"
	@echo "  make processed    ETL: raw → data/processed/ + data/samples/"
	@echo "  make validate     Quality checks → docs/data_profile.md"
	@echo "  make sample       Validate sample only (fast, for CI)"
	@echo "  make info         Print dataset file inventory"
	@echo "  make search Q=зарплата   Search indicator catalogue"
	@echo "  make clean        Remove all generated output files"
	@echo ""
	@echo "  Options (override on command line):"
	@echo "    PYTHON=python3   Python interpreter to use"
	@echo "    SAMPLE_N=5000    Sample size"
	@echo "    COMPRESSION=zstd Parquet compression codec"
	@echo ""

# ── Install ───────────────────────────────────────────────────────────────────

.PHONY: install
install:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt

# ── ETL ───────────────────────────────────────────────────────────────────────

SAMPLE_N     ?= 1000
COMPRESSION  ?= zstd

.PHONY: processed
processed: $(PROCESSED)

$(PROCESSED): $(shell find $(RAW_DIR) -name "*.parquet" 2>/dev/null | head -1)
	@echo "▶ Running ETL pipeline ..."
	$(PYTHON) scripts/01_process.py \
		--sample-n $(SAMPLE_N) \
		--compression $(COMPRESSION)
	@echo "✅ ETL complete"

# ── Validate ──────────────────────────────────────────────────────────────────

.PHONY: validate
validate: $(PROCESSED)
	@echo "▶ Running full validation ..."
	$(PYTHON) scripts/02_validate.py
	@echo "✅ Validation complete → $(PROFILE)"

.PHONY: sample
sample:
	@echo "▶ Running sample-only validation (CI mode) ..."
	$(PYTHON) scripts/02_validate.py --sample-only
	@echo "✅ Sample validation complete"

# ── Explore ───────────────────────────────────────────────────────────────────

.PHONY: info
info:
	$(PYTHON) scripts/03_explore.py info

.PHONY: search
search:
	@if [ -z "$(Q)" ]; then \
		echo "Usage: make search Q=зарплата"; \
	else \
		$(PYTHON) scripts/03_explore.py search "$(Q)"; \
	fi

.PHONY: examples
examples: $(PROCESSED)
	$(PYTHON) scripts/03_explore.py examples

# ── Full pipeline ──────────────────────────────────────────────────────────────

.PHONY: all
all: processed validate
	@echo ""
	@echo "✅ Pipeline complete."
	@echo "   Full dataset : $(PROCESSED)"
	@echo "   Profile      : $(PROFILE)"

# ── Clean ─────────────────────────────────────────────────────────────────────

.PHONY: clean
clean:
	@echo "Removing generated files ..."
	rm -f data/processed/regions_full.parquet
	rm -f data/processed/regions_full.csv.gz
	rm -f data/processed/catalogue.parquet
	rm -f data/processed/catalogue.csv
	rm -f data/processed/objects.parquet
	rm -f data/processed/objects.csv
	rm -f data/processed/sections.parquet
	rm -f data/processed/sections.csv
	rm -f data/samples/regions_sample_*.parquet
	rm -f data/samples/regions_sample_*.csv
	rm -f docs/data_profile.md
	@echo "✅ Clean complete"

.PHONY: clean-all
clean-all: clean
	@echo "Also removing notebooks/.ipynb_checkpoints ..."
	rm -rf notebooks/.ipynb_checkpoints
