"""
03_explore.py — Quick exploration helpers for the dataset.

Sub-commands:
  examples   — Run 4 built-in analysis examples (GRP, wages, population, sections)
  search     — Search indicator catalogue by keyword
  info       — Print dataset summary statistics

Usage:
  python scripts/03_explore.py examples
  python scripts/03_explore.py search зарплата
  python scripts/03_explore.py search --field section здравоохранение
  python scripts/03_explore.py info
  python scripts/03_explore.py --help

Dependencies: pandas>=2.0  pyarrow>=14.0
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT          = Path(__file__).resolve().parent.parent
PROCESSED_DIR = ROOT / "data" / "processed"
SAMPLES_DIR   = ROOT / "data" / "samples"


# ── Data loading ──────────────────────────────────────────────────────────────

def _load_full_or_sample() -> tuple[pd.DataFrame, bool]:
    """Load full dataset if available, else fall back to sample."""
    full = PROCESSED_DIR / "regions_full.parquet"
    if full.exists():
        return pd.read_parquet(full), False
    candidates = sorted(SAMPLES_DIR.glob("regions_sample_*.parquet"))
    if candidates:
        print(f"[info] Full dataset not found. Using sample: {candidates[0].name}")
        print("[info] Run 'python scripts/01_process.py' to generate full dataset.\n")
        return pd.read_parquet(candidates[0]), True
    print("[error] No data files found. Run 'python scripts/01_process.py' first.")
    sys.exit(1)


def _load_catalogue() -> pd.DataFrame:
    path = PROCESSED_DIR / "catalogue.parquet"
    if not path.exists():
        print("[error] catalogue.parquet not found. Run 'python scripts/01_process.py' first.")
        sys.exit(1)
    return pd.read_parquet(path)


def _load_sections() -> pd.DataFrame:
    path = PROCESSED_DIR / "sections.parquet"
    if not path.exists():
        print("[error] sections.parquet not found. Run 'python scripts/01_process.py' first.")
        sys.exit(1)
    return pd.read_parquet(path)


def _valid(df: pd.DataFrame) -> pd.DataFrame:
    """Filter to rows with valid (non-sentinel) values."""
    return df[df["value_status"] == "ok"]


# ── Sub-command: examples ─────────────────────────────────────────────────────

def _header(title: str) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def example_grp(df: pd.DataFrame) -> None:
    _header("Example 1: Gross Regional Product — top 10 regions (latest year)")
    grp = _valid(df)[
        df["indicator_name"].str.contains("Валовой региональный продукт", na=False) &
        (df["object_level"] == "Регион")
    ]
    if grp.empty:
        print("  No GRP data available in this slice.")
        return
    latest = grp["year"].max()
    top = (
        grp[grp["year"] == latest]
        .drop_duplicates("object_name")
        .nlargest(10, "indicator_value")
        [["object_name", "year", "indicator_value", "indicator_unit"]]
        .reset_index(drop=True)
    )
    top.index += 1
    print(top.to_string())


def example_wages(df: pd.DataFrame) -> None:
    _header("Example 2: Average monthly wage by Federal District (2015→latest)")
    wages = _valid(df)[
        df["indicator_name"].str.contains("Среднемесячная", na=False) &
        df["indicator_name"].str.contains("заработная плата", na=False) &
        (df["object_level"] == "Федеральный округ")
    ]
    if wages.empty:
        print("  No wage data for federal districts in this slice.")
        return
    pivot = (
        wages.groupby(["object_name", "year"])["indicator_value"]
        .mean()
        .unstack("year")
    )
    # show from 2015 onward
    cols = [c for c in pivot.columns if c >= 2015]
    print(pivot[cols].round(0).to_string())


def example_population(df: pd.DataFrame) -> None:
    _header("Example 3: Population of Russian regions, latest available year")
    pop = _valid(df)[
        df["indicator_name"].str.contains("Численность населения", na=False) &
        (df["object_level"] == "Регион")
    ]
    if pop.empty:
        print("  No population data in this slice.")
        return
    latest = pop["year"].max()
    top = (
        pop[pop["year"] == latest]
        .sort_values("indicator_value", ascending=False)
        .drop_duplicates("object_name")
        .head(15)
        [["object_name", "indicator_value", "indicator_unit", "year"]]
        .reset_index(drop=True)
    )
    top.index += 1
    print(top.to_string())


def example_sections(df: pd.DataFrame) -> None:
    _header("Example 4: All sections — row counts")
    counts = _valid(df)["section"].value_counts()
    for sec, n in counts.items():
        print(f"  {n:>10,}  {sec}")


def cmd_examples(args: argparse.Namespace) -> None:
    df, is_sample = _load_full_or_sample()
    if is_sample:
        print("[warn] Results below are from a 1 000-row sample and may be incomplete.\n")
    example_grp(df)
    example_wages(df)
    example_population(df)
    example_sections(df)


# ── Sub-command: search ───────────────────────────────────────────────────────

def cmd_search(args: argparse.Namespace) -> None:
    """
    Search indicator catalogue by keyword (case-insensitive, Russian-friendly).
    Searches indicator_name by default; use --field to search other columns.
    """
    cat   = _load_catalogue()
    field = args.field
    query = args.query

    if field not in cat.columns:
        print(f"[error] Unknown field '{field}'. Available: {cat.columns.tolist()}")
        sys.exit(1)

    mask    = cat[field].str.contains(query, case=False, na=False)
    results = cat[mask].reset_index(drop=True)

    if results.empty:
        print(f"No indicators found matching '{query}' in field '{field}'.")
        return

    print(f"Found {len(results)} indicator(s) matching '{query}' in '{field}':\n")
    pd.set_option("display.max_colwidth", 80)
    pd.set_option("display.width", 160)
    print(results[["indicator_code", "indicator_name", "section", "primary_unit"]].to_string(index=True))
    print(f"\nUse indicator_code to filter the full dataset:")
    codes = results["indicator_code"].head(3).tolist()
    for code in codes:
        print(f"  df[df['indicator_code'] == '{code}']")


# ── Sub-command: info ─────────────────────────────────────────────────────────

def cmd_info(args: argparse.Namespace) -> None:
    """Print high-level summary of all available data files."""
    print("\n=== Dataset file inventory ===\n")

    files = {
        "Full dataset":      PROCESSED_DIR / "regions_full.parquet",
        "Catalogue":         PROCESSED_DIR / "catalogue.parquet",
        "Objects":           PROCESSED_DIR / "objects.parquet",
        "Sections":          PROCESSED_DIR / "sections.parquet",
        "Sample":            next(iter(sorted(SAMPLES_DIR.glob("regions_sample_*.parquet"))), None),
    }
    for label, path in files.items():
        if path is None or not path.exists():
            print(f"  {'[missing]':>10}  {label}")
            continue
        size_mb = path.stat().st_size / 1024**2
        df      = pd.read_parquet(path)
        print(f"  {size_mb:>8.1f} MB  {label:20s}  {len(df):>10,} rows × {len(df.columns)} cols  →  {path.name}")

    # Sections breakdown
    sec_path = PROCESSED_DIR / "sections.parquet"
    if sec_path.exists():
        secs = pd.read_parquet(sec_path)
        print(f"\n=== Sections ({len(secs)} total) ===\n")
        pd.set_option("display.max_colwidth", 60)
        pd.set_option("display.width", 120)
        print(secs[["section", "row_count", "indicator_count", "year_min", "year_max", "pct_ok"]].to_string(index=False))


# ── CLI wiring ────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Explore the Rosstat regional dataset",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    sub = p.add_subparsers(dest="command", required=True)

    # examples
    sub.add_parser("examples", help="Run 4 built-in analysis examples")

    # search
    s = sub.add_parser("search", help="Search indicator catalogue by keyword")
    s.add_argument("query", help="Search term (case-insensitive)")
    s.add_argument(
        "--field", "-f",
        default="indicator_name",
        choices=["indicator_name", "section", "indicator_code", "primary_unit"],
        help="Column to search in",
    )

    # info
    sub.add_parser("info", help="Print dataset summary and file inventory")

    return p


def main() -> None:
    parser  = build_parser()
    args    = parser.parse_args()
    dispatch = {"examples": cmd_examples, "search": cmd_search, "info": cmd_info}
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
