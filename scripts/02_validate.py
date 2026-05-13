"""
02_validate.py — Data quality checks and profiling report.

Reads processed data and emits:
  - console summary with pass/warn/fail per check
  - docs/data_profile.md  (Markdown report, GitHub-renderable)

Usage:
  python scripts/02_validate.py                   # full dataset
  python scripts/02_validate.py --sample-only     # use sample (fast, for CI)
  python scripts/02_validate.py --out docs/my_profile.md
  python scripts/02_validate.py --help

Notes on "duplicate primary key" warning:
  The natural key (indicator_code, subsection, object_oktmo, year) is NOT
  guaranteed unique in the source data. The same indicator can appear in
  multiple Rosstat collections for the same region/year, sometimes with
  different values (partial duplicates). The dataset intentionally keeps
  the latest non-missing value per collection per the source documentation
  (section 4, «Полнота данных»). This is expected and NOT a data error.

Dependencies: pandas>=2.0  pyarrow>=14.0
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT          = Path(__file__).resolve().parent.parent
PROCESSED_DIR = ROOT / "data" / "processed"
SAMPLES_DIR   = ROOT / "data" / "samples"
DOCS_DIR      = ROOT / "docs"

EXPECTED_COLUMNS = [
    "section", "indicator_code", "indicator_name", "subsection",
    "object_name", "object_level", "object_oktmo", "object_okato",
    "year", "indicator_value", "indicator_unit",
    "comment", "source", "version_date", "value_status",
]
PRIMARY_KEY = ["indicator_code", "subsection", "object_oktmo", "year"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


# ── CLI ──────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Validate processed dataset and generate data_profile.md",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument(
        "--sample-only",
        action="store_true",
        help="Validate sample file instead of full dataset (fast; use in CI)",
    )
    p.add_argument(
        "--input",
        type=Path,
        default=None,
        metavar="PATH",
        help="Override input parquet path",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=DOCS_DIR / "data_profile.md",
        metavar="PATH",
        help="Path for the generated Markdown report",
    )
    p.add_argument(
        "--fail-on-warn",
        action="store_true",
        help="Exit with code 1 if any warnings are found (strict CI mode)",
    )
    p.add_argument(
        "--ignore-warn",
        nargs="*",
        default=[],
        metavar="CHECK_NAME",
        help="Warn-level check names to exclude when --fail-on-warn is set "
             "(e.g. 'Duplicate primary key'). Useful for known/expected warnings.",
    )
    return p.parse_args()


# ── Checks ───────────────────────────────────────────────────────────────────

class Check:
    """Container for a single quality check result."""
    def __init__(self, name: str, status: str, detail: str):
        assert status in ("ok", "warn", "fail")
        self.name   = name
        self.status = status
        self.detail = detail

    @property
    def icon(self) -> str:
        return {"ok": "✅", "warn": "⚠️", "fail": "❌"}[self.status]

    def __str__(self) -> str:
        return f"{self.icon} {self.name}: {self.detail}"


def check_schema(df: pd.DataFrame) -> Check:
    missing = [c for c in EXPECTED_COLUMNS if c not in df.columns]
    extra   = [c for c in df.columns if c not in EXPECTED_COLUMNS]
    if missing:
        return Check("Schema", "fail",
                     f"Missing columns: {missing}")
    if extra:
        return Check("Schema", "warn",
                     f"Unexpected extra columns: {extra}")
    return Check("Schema", "ok",
                 f"All {len(EXPECTED_COLUMNS)} expected columns present")


def check_row_count(df: pd.DataFrame, sample_mode: bool) -> Check:
    n = len(df)
    if sample_mode:
        return Check("Row count", "ok", f"{n:,} rows (sample mode)")
    if n < 1_900_000:
        return Check("Row count", "warn",
                     f"{n:,} rows — expected ≥ 1,900,000 for full dataset")
    return Check("Row count", "ok", f"{n:,} rows")


def check_value_status(df: pd.DataFrame) -> Check:
    allowed = {"ok", "no_data", "hidden"}
    actual  = set(df["value_status"].unique())
    unknown = actual - allowed
    if unknown:
        return Check("value_status values", "fail",
                     f"Unknown status values: {unknown}")
    ok_pct = (df["value_status"] == "ok").mean()
    if ok_pct < 0.80:
        return Check("value_status coverage", "warn",
                     f"Only {ok_pct:.1%} rows are 'ok' — unusually low")
    return Check("value_status coverage", "ok",
                 f"{ok_pct:.1%} rows have valid values")


def check_year_range(df: pd.DataFrame) -> Check:
    ymin, ymax = int(df["year"].min()), int(df["year"].max())
    if ymin > 2001 or ymax < 2020:
        return Check("Year range", "warn",
                     f"{ymin}–{ymax} — narrower than expected (2001–2025)")
    return Check("Year range", "ok", f"{ymin}–{ymax}")


def check_sentinels(df: pd.DataFrame) -> Check:
    """Verify no raw sentinel values leaked into valid rows."""
    bad = df[
        (df["value_status"] == "ok") &
        (df["indicator_value"].isin([-99_999_999.0, -77_777_777.0]))
    ]
    if len(bad):
        return Check("Sentinel leakage", "fail",
                     f"{len(bad):,} rows marked 'ok' still contain sentinel values")
    return Check("Sentinel leakage", "ok",
                 "No sentinel values in 'ok' rows")


def check_duplicate_pk(df: pd.DataFrame) -> Check:
    """
    Known issue: the same (indicator_code, subsection, object_oktmo, year)
    can appear in multiple Rosstat collections. This is documented in the
    source (section 4 «Полнота данных») and is NOT a data error.
    We report count for transparency, always as 'warn' not 'fail'.
    """
    n_dupes = df.duplicated(subset=PRIMARY_KEY, keep=False).sum()
    if n_dupes == 0:
        return Check("Duplicate primary key", "ok", "No duplicates found")
    pct = n_dupes / len(df)
    return Check(
        "Duplicate primary key", "warn",
        f"{n_dupes:,} rows ({pct:.1%}) share key {PRIMARY_KEY}. "
        "Expected: same indicator can exist in multiple Rosstat collections "
        "for the same region/year. See docs §4 «Полнота данных».",
    )


def check_nulls(df: pd.DataFrame) -> Check:
    """Check for unexpected Python None/NaN (not sentinel-encoded missing)."""
    null_counts = df.isnull().sum()
    problem_cols = null_counts[null_counts > 0]
    # indicator_value and indicator_unit are allowed to have NaN
    # (they use sentinel encoding + ND/CD strings, but parquet may differ)
    unexpected = problem_cols.drop(
        labels=[c for c in ["indicator_value"] if c in problem_cols.index],
        errors="ignore",
    )
    if len(unexpected):
        return Check("Null values", "warn",
                     f"Unexpected nulls in: {unexpected.to_dict()}")
    return Check("Null values", "ok", "No unexpected nulls")


def run_all_checks(df: pd.DataFrame, sample_mode: bool) -> list[Check]:
    checks = [
        check_schema(df),
        check_row_count(df, sample_mode),
        check_value_status(df),
        check_year_range(df),
        check_sentinels(df),
        check_duplicate_pk(df),
        check_nulls(df),
    ]
    for c in checks:
        fn = log.warning if c.status == "warn" else (log.error if c.status == "fail" else log.info)
        fn("  %s", c)
    return checks


# ── Profile ───────────────────────────────────────────────────────────────────

def compute_profile(df: pd.DataFrame) -> dict:
    valid = df[df["value_status"] == "ok"]["indicator_value"]
    return {
        "total_rows":       len(df),
        "total_indicators": df["indicator_code"].nunique(),
        "total_regions":    df[df["object_level"] == "Регион"]["object_name"].nunique(),
        "total_sections":   df["section"].nunique(),
        "year_min":         int(df["year"].min()),
        "year_max":         int(df["year"].max()),
        "source_count":     df["source"].nunique(),
        "rows_ok":          int((df["value_status"] == "ok").sum()),
        "rows_no_data":     int((df["value_status"] == "no_data").sum()),
        "rows_hidden":      int((df["value_status"] == "hidden").sum()),
        "valid_value_min":  float(valid.min()),
        "valid_value_max":  float(valid.max()),
        "valid_value_mean": float(valid.mean()),
    }


def build_section_summary(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df.groupby("section", observed=True)
        .agg(
            rows=("indicator_code", "count"),
            indicators=("indicator_code", "nunique"),
            year_min=("year", "min"),
            year_max=("year", "max"),
            pct_ok=("value_status", lambda s: (s == "ok").mean()),
        )
        .reset_index()
        .assign(years=lambda d: d["year_min"].astype(str) + "–" + d["year_max"].astype(str))
        .assign(pct_ok=lambda d: d["pct_ok"].map("{:.1%}".format))
        .drop(columns=["year_min", "year_max"])
        .sort_values("rows", ascending=False)
        .reset_index(drop=True)
    )


# ── Report ────────────────────────────────────────────────────────────────────

def write_md_report(
    p: dict,
    checks: list[Check],
    section_df: pd.DataFrame,
    out: Path,
    sample_mode: bool,
) -> None:
    mode_note = " *(sample mode)*" if sample_mode else ""
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    source_path = (
        "data/samples/regions_sample_*.parquet"
        if sample_mode
        else "data/processed/regions_full.parquet"
    )

    lines = [
        "# Data Profile Report",
        "",
        f"Generated: {generated}{mode_note}  ",
        f"Source: `{source_path}`",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total rows | {p['total_rows']:,} |",
        f"| Indicators | {p['total_indicators']:,} |",
        f"| Regions | {p['total_regions']:,} |",
        f"| Sections | {p['total_sections']:,} |",
        f"| Year range | {p['year_min']}–{p['year_max']} |",
        f"| Source collections | {p['source_count']:,} |",
        f"| Rows: ok | {p['rows_ok']:,} ({p['rows_ok']/p['total_rows']:.1%}) |",
        f"| Rows: no_data | {p['rows_no_data']:,} ({p['rows_no_data']/p['total_rows']:.1%}) |",
        f"| Rows: hidden | {p['rows_hidden']:,} ({p['rows_hidden']/p['total_rows']:.1%}) |",
        f"| Valid value min | {p['valid_value_min']:,.4f} |",
        f"| Valid value max | {p['valid_value_max']:,.4f} |",
        f"| Valid value mean | {p['valid_value_mean']:,.4f} |",
        "",
        "## Quality Checks",
        "",
        "> **Note on duplicate primary keys:** The same indicator can exist in multiple "
        "Rosstat collections for the same region/year. This is documented in the source "
        "(§4 «Полнота данных») and is **expected behaviour**, not a data error. "
        "The dataset retains the latest non-missing value per observation.",
        "",
    ]
    for c in checks:
        lines.append(f"- {c.icon} **{c.name}:** {c.detail}")

    lines += [
        "",
        "## Coverage by Section (all sections)",
        "",
        "| # | Section | Rows | Indicators | Years | % OK |",
        "|--:|---------|-----:|-----------:|-------|-----:|",
    ]
    for i, row in section_df.iterrows():
        lines.append(
            f"| {i+1} | {row['section']} | {row['rows']:,} | "
            f"{row['indicators']} | {row['years']} | {row['pct_ok']} |"
        )
    lines.append("")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    log.info("Report written → %s", out)


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    args = parse_args()
    t0   = time.perf_counter()

    # Resolve input file
    if args.input:
        src = args.input
    elif args.sample_only:
        # pick the first available sample
        candidates = sorted(SAMPLES_DIR.glob("regions_sample_*.parquet"))
        if not candidates:
            log.error("No sample file found in %s. Run 01_process.py first.", SAMPLES_DIR)
            sys.exit(1)
        src = candidates[0]
        log.info("Sample mode: using %s", src.name)
    else:
        src = PROCESSED_DIR / "regions_full.parquet"

    if not src.exists():
        log.error("File not found: %s", src)
        log.error("Run 'python scripts/01_process.py' first.")
        sys.exit(1)

    log.info("=== Validation start ===")
    log.info("Loading %s ...", src.name)
    df = pd.read_parquet(src)
    log.info("  %d rows × %d cols", *df.shape)

    log.info("Running checks ...")
    checks = run_all_checks(df, sample_mode=args.sample_only)

    log.info("Profiling ...")
    p = compute_profile(df)

    section_df = build_section_summary(df)
    write_md_report(p, checks, section_df, args.out, sample_mode=args.sample_only)

    n_fail = sum(1 for c in checks if c.status == "fail")
    ignored = set(args.ignore_warn or [])
    n_warn = sum(1 for c in checks if c.status == "warn" and c.name not in ignored)
    n_warn_ignored = sum(1 for c in checks if c.status == "warn" and c.name in ignored)
    log.info("=== Done in %.1fs | %d ok  %d warn  %d ignored  %d fail ===",
             time.perf_counter() - t0,
             sum(1 for c in checks if c.status == "ok"),
             n_warn, n_warn_ignored, n_fail)
    if n_warn_ignored:
        log.info("  Ignored warnings (--ignore-warn): %s", ", ".join(sorted(ignored)))

    if n_fail or (args.fail_on_warn and n_warn):
        sys.exit(1)


if __name__ == "__main__":
    main()
