from pathlib import Path
import shutil
import kagglehub

DATASET_SLUG = "rounakbanik/the-movies-dataset"
TARGET_FILES = {
    "movies_metadata.csv",
    "credits.csv",
    "ratings_small.csv",
    "links_small.csv",
}

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"


def download_dataset() -> None:
    """Download The Movies Dataset from Kaggle and copy only selected CSVs to data/raw/."""
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Downloading '{DATASET_SLUG}' from Kaggle...")
    cache_path = Path(kagglehub.dataset_download(DATASET_SLUG))

    copied_files = 0
    for filename in sorted(TARGET_FILES):
        src_file = cache_path / filename
        if not src_file.exists():
            raise FileNotFoundError(f"Expected file not found: {filename}")
        dst_file = RAW_DATA_DIR / filename
        shutil.copy2(src_file, dst_file)
        size_mb = dst_file.stat().st_size / (1024 * 1024)
        print(f" - Saved: {dst_file.name} ({size_mb:.2f} MB)")
        copied_files += 1

    print(f"\nDone. {copied_files} selected files saved to '{RAW_DATA_DIR}'.")


if __name__ == "__main__":
    download_dataset()