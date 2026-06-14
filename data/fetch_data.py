"""
ForgeSight — Phase 1 dataset fetcher (idempotent).
====================================================
Downloads the public run-to-failure / fault benchmarks that VALIDATE the ML methods
(the synthetic steel layer validates the SYSTEM — see forgesight-v3-final.md §1.10).

Sources (BUILD_GUIDE.md §2.1):
  - NASA C-MAPSS FD001 (RUL)         : S3 zip
  - AI4I 2020 (failure classifier)   : ucimlrepo id=601
  - UCI Steel Plates Faults (defect) : ucimlrepo id=198
  - CWRU bearing (vibration)         : Kaggle / manual placement
  - NASA IMS bearing (degradation)   : Kaggle / manual placement

Idempotent: existing files are not re-downloaded. Never fails silently — anything that
can't be fetched prints clear manual-placement instructions and is reported at the end.

Run:  python data/fetch_data.py
Gate 1 expectation: C-MAPSS train_FD001 = 20,631 rows · AI4I = 10,000 · Steel Plates = 1,941.
"""

from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

import requests

RAW = Path(__file__).resolve().parent / "raw"

CMAPSS_ZIP_URL = (
    "https://phm-datasets.s3.amazonaws.com/NASA/"
    "6.+Turbofan+Engine+Degradation+Simulation+Data+Set.zip"
)

# Per-dataset status accumulated for the final report.
_report: list[tuple[str, bool, str]] = []


def _ok(name: str, msg: str) -> None:
    _report.append((name, True, msg))
    print(f"  [ok]   {name}: {msg}")


def _missing(name: str, msg: str) -> None:
    _report.append((name, False, msg))
    print(f"  [MISS] {name}: {msg}")


# ----------------------------------------------------------------------------------
# C-MAPSS FD001 (RUL) — S3 zip, nested zips. We only need train/test/RUL FD001 txt.
# ----------------------------------------------------------------------------------

def fetch_cmapss() -> None:
    out = RAW / "cmapss"
    train = out / "train_FD001.txt"
    if train.exists():
        n = sum(1 for _ in train.open())
        _ok("C-MAPSS", f"train_FD001.txt present ({n} rows)")
        return
    print("  downloading C-MAPSS (S3, ~25 MB, may be slow)…")
    try:
        r = requests.get(CMAPSS_ZIP_URL, timeout=120)
        r.raise_for_status()
        _extract_cmapss(r.content, out)
    except Exception as e:  # noqa: BLE001
        _missing(
            "C-MAPSS",
            f"download failed ({e}). Manual: download the NASA Turbofan zip and place "
            f"train_FD001.txt / test_FD001.txt / RUL_FD001.txt in {out}",
        )
        return
    if train.exists():
        n = sum(1 for _ in train.open())
        _ok("C-MAPSS", f"extracted train_FD001.txt ({n} rows; expect 20631)")
    else:
        _missing("C-MAPSS", f"zip fetched but FD001 files not found; inspect {out}")


def _extract_cmapss(content: bytes, out: Path) -> None:
    """The S3 archive nests a 'CMAPSSData.zip' (or similar) holding the txt files."""
    out.mkdir(parents=True, exist_ok=True)
    targets = {"train_FD001.txt", "test_FD001.txt", "RUL_FD001.txt"}

    def _pull(zf: zipfile.ZipFile) -> None:
        for member in zf.namelist():
            base = member.rsplit("/", 1)[-1]
            if base in targets:
                (out / base).write_bytes(zf.read(member))

    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        _pull(zf)
        for member in zf.namelist():
            if member.lower().endswith(".zip"):
                try:
                    with zipfile.ZipFile(io.BytesIO(zf.read(member))) as inner:
                        _pull(inner)
                except zipfile.BadZipFile:
                    continue


# ----------------------------------------------------------------------------------
# UCI datasets via ucimlrepo (AI4I 2020, Steel Plates) — robust, no Kaggle creds needed.
# ----------------------------------------------------------------------------------

def fetch_uci(name: str, uci_id: int, subdir: str, expect_rows: int) -> None:
    out = RAW / subdir
    csv = out / f"{subdir}.csv"
    if csv.exists():
        n = sum(1 for _ in csv.open()) - 1
        _ok(name, f"{csv.name} present ({n} rows)")
        return
    try:
        from ucimlrepo import fetch_ucirepo
    except ImportError:
        _missing(name, "ucimlrepo not installed (`uv add ucimlrepo`). Skipped.")
        return
    try:
        ds = fetch_ucirepo(id=uci_id)
        df = ds.data.original if ds.data.original is not None else ds.data.features
        out.mkdir(parents=True, exist_ok=True)
        df.to_csv(csv, index=False)
        _ok(name, f"wrote {csv.name} ({len(df)} rows; expect {expect_rows})")
    except Exception as e:  # noqa: BLE001
        _missing(name, f"fetch failed ({e}). UCI id={uci_id}; place CSV at {csv}")


# ----------------------------------------------------------------------------------
# Kaggle datasets (CWRU, IMS) — optional; API path or manual placement.
# ----------------------------------------------------------------------------------

def fetch_kaggle(name: str, slug: str, subdir: str) -> None:
    out = RAW / subdir
    if any(out.iterdir()) if out.exists() else False:
        _ok(name, f"{subdir}/ already populated")
        return
    out.mkdir(parents=True, exist_ok=True)
    import os

    if os.getenv("KAGGLE_USERNAME") and os.getenv("KAGGLE_KEY"):
        try:
            import kaggle  # noqa: F401  (auth happens on import)

            kaggle.api.dataset_download_files(slug, path=str(out), unzip=True)
            _ok(name, f"downloaded via Kaggle API → {out}")
            return
        except Exception as e:  # noqa: BLE001
            _missing(name, f"Kaggle API failed ({e}). Manual: kaggle datasets download -d {slug}")
            return
    _missing(
        name,
        f"optional — set KAGGLE_USERNAME/KAGGLE_KEY or place files in {out} "
        f"(kaggle: {slug}). Not required for Gate 1.",
    )


# ----------------------------------------------------------------------------------

def main() -> int:
    # Windows consoles default to cp1252; force utf-8 so status glyphs never crash the run.
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001
        pass
    print("ForgeSight · fetch_data — downloading benchmarks into data/raw/\n")
    fetch_cmapss()
    fetch_uci("AI4I-2020", 601, "ai4i", 10000)
    fetch_uci("Steel-Plates", 198, "steel_plates", 1941)
    fetch_kaggle("CWRU-bearing", "brjapon/cwru-bearing-datasets", "cwru")
    fetch_kaggle("NASA-IMS", "vinayak123tyagi/bearing-dataset", "ims")

    print("\n" + "=" * 60)
    required = {"C-MAPSS", "AI4I-2020", "Steel-Plates"}
    got = {n for n, ok, _ in _report if ok}
    missing_required = required - got
    for name, ok, msg in _report:
        flag = "✓" if ok else "·"
        print(f"  {flag} {name:14s} {msg}")
    print("=" * 60)
    if missing_required:
        print(f"\nGATE 1 (datasets) NOT met — missing required: {sorted(missing_required)}")
        print("CWRU/IMS are optional. Fix the required three and re-run.")
        return 1
    print("\nGATE 1 (downloads): required benchmarks present. "
          "CWRU/IMS optional (feed the bearing narrative only).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
