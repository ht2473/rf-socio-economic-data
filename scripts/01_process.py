"""
01_process.py — ETL pipeline for Росстат regional socio-economic dataset.

Reads raw parquet from «Если быть точным» and produces:
  data/processed/regions_full.parquet   — full cleaned dataset  (+value_status)
  data/processed/regions_full.csv.gz    — same, gzip CSV (UTF-8, sep=;)
  data/processed/catalogue.parquet/.csv — indicator reference (1 294 rows)
  data/processed/objects.parquet/.csv   — territory reference  (98 rows)
  data/processed/sections.parquet/.csv  — section reference    (117 rows)
  data/samples/regions_sample_N.parquet/.csv — stratified sample

Usage:
  python scripts/01_process.py                          # defaults
  python scripts/01_process.py --input path/to/raw.parquet
  python scripts/01_process.py --sample-n 5000 --compression zstd
  python scripts/01_process.py --no-csv-gz              # skip heavy gzip step
  python scripts/01_process.py --help

Strategy:
  PyArrow handles the full ~1.3 GB table to avoid Pandas OOM.
  Pandas is used only for small derived subsets (catalogue, objects, sections).
  CSV is written in streaming 200 k-row chunks.

Dependencies: pandas>=2.0  pyarrow>=14.0
"""

from __future__ import annotations

import argparse
import gzip
import logging
import sys
import time
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

# ── Constants ────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent.parent

SENTINEL_NO_DATA = -99_999_999.0   # "Нет информации" in source
SENTINEL_HIDDEN  = -77_777_777.0   # "Скрыто" (suppressed by Rosstat)
CSV_SEP          = ";"             # Rosstat convention; matches source docs
CSV_CHUNK        = 200_000         # rows per chunk for streaming CSV write

# ── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


class _Timer:
    """Minimal context-manager stopwatch."""
    def __init__(self, label: str):
        self.label = label
    def __enter__(self):
        self.t = time.perf_counter()
        return self
    def __exit__(self, *_):
        log.info("%s — %.1fs", self.label, time.perf_counter() - self.t)


# ── CLI ──────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="ETL pipeline: raw Rosstat parquet → processed dataset",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument(
        "--input", "-i",
        type=Path,
        default=ROOT / "data" / "raw" / "data_regions_collection_102_v20260313.parquet",
        metavar="PATH",
        help="Path to raw source parquet file",
    )
    p.add_argument(
        "--processed-dir",
        type=Path,
        default=ROOT / "data" / "processed",
        metavar="DIR",
        help="Output directory for processed files",
    )
    p.add_argument(
        "--samples-dir",
        type=Path,
        default=ROOT / "data" / "samples",
        metavar="DIR",
        help="Output directory for sample files",
    )
    p.add_argument(
        "--sample-n",
        type=int,
        default=1_000,
        metavar="N",
        help="Number of rows in the stratified sample",
    )
    p.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducible sampling",
    )
    p.add_argument(
        "--compression",
        choices=["snappy", "zstd", "lz4", "none"],
        default="zstd",
        help="Parquet compression codec. zstd gives best size/speed trade-off for archival.",
    )
    p.add_argument(
        "--compression-level",
        type=int,
        default=3,
        help="Compression level (zstd only; 1=fast, 22=max). Default 3 is a good balance.",
    )
    p.add_argument(
        "--no-csv-gz",
        action="store_true",
        help="Skip generating regions_full.csv.gz (saves time; parquet is primary format)",
    )
    return p.parse_args()


# ── Core pipeline ────────────────────────────────────────────────────────────

def load_raw(path: Path) -> pa.Table:
    if not path.exists():
        log.error("Raw file not found: %s", path)
        log.error("Download from https://tochno.st/datasets/regions_collection "
                  "and place in data/raw/")
        sys.exit(1)
    log.info("Loading raw parquet: %s", path)
    with _Timer("  read_parquet"):
        table = pq.read_table(path)
    log.info("  %d rows × %d cols  |  %.0f MB in-memory",
             len(table), len(table.schema), table.nbytes / 1024**2)
    return table


def add_value_status(table: pa.Table) -> pa.Table:
    """
    Append 'value_status' column replacing sentinel magic numbers with labels:
      'ok'      — real observation
      'no_data' — absent / erroneous in source (-99999999)
      'hidden'  — suppressed by Rosstat (-77777777)
    """
    log.info("Adding value_status column ...")
    val     = table.column("indicator_value")
    no_data = pc.equal(val, SENTINEL_NO_DATA)
    hidden  = pc.equal(val, SENTINEL_HIDDEN)
    status  = pc.if_else(no_data, "no_data", pc.if_else(hidden, "hidden", "ok"))
    table   = table.append_column("value_status", status)

    counts = table.column("value_status").to_pandas().value_counts()
    log.info("  value_status distribution:\n%s", counts.to_string())
    return table


def save_parquet(table: pa.Table | pd.DataFrame, path: Path,
                 compression: str = "zstd", compression_level: int = 3) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    kwargs: dict = dict(compression=compression)
    if compression == "zstd":
        kwargs["compression_level"] = compression_level
    with _Timer(f"  write {path.name}"):
        if isinstance(table, pd.DataFrame):
            table.to_parquet(path, index=False, **kwargs)
        else:
            pq.write_table(table, path, **kwargs)
    log.info("  saved %s (%.1f MB)", path.name, path.stat().st_size / 1024**2)


def save_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, sep=CSV_SEP, encoding="utf-8")
    log.info("  saved %s (%d rows)", path.name, len(df))


def save_csv_gz(table: pa.Table, path: Path) -> None:
    """Stream-write gzip CSV in chunks to avoid materialising full DataFrame."""
    path.parent.mkdir(parents=True, exist_ok=True)
    n = len(table)
    log.info("Writing gzip CSV (%d-row chunks) ...", CSV_CHUNK)
    with _Timer(f"  write {path.name}"):
        with gzip.open(path, "wt", encoding="utf-8") as fh:
            for start in range(0, n, CSV_CHUNK):
                chunk = table.slice(start, min(CSV_CHUNK, n - start)).to_pandas()
                fh.write(chunk.to_csv(
                    index=False, sep=CSV_SEP,
                    lineterminator="\n", header=(start == 0),
                ))
    log.info("  saved %s (%.1f MB)", path.name, path.stat().st_size / 1024**2)


# ── Reference tables ─────────────────────────────────────────────────────────

def build_catalogue(table: pa.Table) -> pd.DataFrame:
    """
    Indicator reference: one row per indicator_code.
    primary_unit = most frequent non-null unit across all observations.
    """
    log.info("Building indicator catalogue ...")
    df = table.select(
        ["indicator_code", "indicator_name", "section", "indicator_unit"]
    ).to_pandas()

    unit_mode = (
        df[~df["indicator_unit"].isin(["ND", "CD"])]
        .groupby("indicator_code")["indicator_unit"]
        .agg(lambda s: s.mode().iloc[0] if len(s) else pd.NA)
        .rename("primary_unit")
    )
    cat = (
        df[["indicator_code", "indicator_name", "section"]]
        .drop_duplicates("indicator_code")
        .set_index("indicator_code")
        .join(unit_mode)
        .reset_index()
        .sort_values("indicator_code")
    )
    log.info("  %d unique indicators", len(cat))
    return cat


def build_objects(table: pa.Table) -> pd.DataFrame:
    """Territory reference: unique (name, level, oktmo, okato)."""
    log.info("Building territory reference ...")
    objs = (
        table.select(["object_name", "object_level", "object_oktmo", "object_okato"])
        .to_pandas()
        .drop_duplicates()
        .sort_values(["object_level", "object_name"])
        .reset_index(drop=True)
    )
    log.info("  %d unique territories", len(objs))
    return objs


def build_sections(table: pa.Table) -> pd.DataFrame:
    """
    Section reference: one row per section with coverage statistics.
    Useful for exploration without loading the full dataset.
    """
    log.info("Building section reference ...")
    df = table.select(
        ["section", "indicator_code", "year", "value_status"]
    ).to_pandas()

    secs = (
        df.groupby("section", observed=True)
        .agg(
            row_count=("indicator_code", "count"),
            indicator_count=("indicator_code", "nunique"),
            year_min=("year", "min"),
            year_max=("year", "max"),
            pct_ok=("value_status", lambda s: round((s == "ok").mean(), 4)),
        )
        .reset_index()
        .sort_values("row_count", ascending=False)
        .reset_index(drop=True)
    )
    log.info("  %d unique sections", len(secs))
    return secs


# ── Sampling ─────────────────────────────────────────────────────────────────

def make_sample(table: pa.Table, n: int, seed: int) -> pd.DataFrame:
    """
    Stratified random sample proportional to (section × object_level).
    Guarantees at least 1 row per stratum; result is exactly n rows.
    """
    log.info("Building %d-row stratified sample (seed=%d) ...", n, seed)
    df     = table.to_pandas()
    strata = df.groupby(["section", "object_level"], observed=True)
    total  = len(df)

    frames = [
        grp.sample(
            min(max(1, round(n * len(grp) / total)), len(grp)),
            random_state=seed,
        )
        for _, grp in strata
    ]
    sample = (
        pd.concat(frames)
        .sample(min(n, sum(len(f) for f in frames)), random_state=seed)
        .reset_index(drop=True)
    )
    log.info("  %d rows across %d strata", len(sample), len(frames))
    return sample


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    args = parse_args()
    t0   = time.perf_counter()

    log.info("=== ETL pipeline start ===")
    log.info("  input:       %s", args.input)
    log.info("  compression: %s (level=%s)", args.compression, args.compression_level)
    log.info("  sample-n:    %d", args.sample_n)

    comp   = args.compression
    clevel = args.compression_level
    pdir   = args.processed_dir
    sdir   = args.samples_dir

    # 1. Load & enrich
    table = load_raw(args.input)
    table = add_value_status(table)

    # 2. Full dataset
    save_parquet(table, pdir / "regions_full.parquet", comp, clevel)
    if not args.no_csv_gz:
        save_csv_gz(table, pdir / "regions_full.csv.gz")
    else:
        log.info("Skipping regions_full.csv.gz (--no-csv-gz)")

    # 3. Reference tables
    for df, stem in [
        (build_catalogue(table), "catalogue"),
        (build_objects(table),   "objects"),
        (build_sections(table),  "sections"),
    ]:
        save_parquet(df, pdir / f"{stem}.parquet", comp, clevel)
        save_csv(df,     pdir / f"{stem}.csv")

    # 4. Sample
    sdir.mkdir(parents=True, exist_ok=True)
    sample_name = f"regions_sample_{args.sample_n}"
    sample = make_sample(table, args.sample_n, args.seed)
    save_parquet(sample, sdir / f"{sample_name}.parquet", comp, clevel)
    save_csv(sample,     sdir / f"{sample_name}.csv")

    # GitHub-preview CSV: all columns, heavy text fields truncated to stay
    # under GitHub's 512 KB CSV render limit so the table is visible in-browser.
    preview = sample.copy()
    preview["indicator_name"] = preview["indicator_name"].str[:60]
    preview["comment"]        = preview["comment"].str[:40]
    preview_path = sdir / f"{sample_name}_preview.csv"
    preview.to_csv(preview_path, index=False, sep=CSV_SEP, encoding="utf-8")
    log.info("  saved %s (%.0f KB, GitHub-renderable)",
             preview_path.name, preview_path.stat().st_size / 1024)

    log.info("=== Done in %.1fs ===", time.perf_counter() - t0)


if __name__ == "__main__":
    main()
