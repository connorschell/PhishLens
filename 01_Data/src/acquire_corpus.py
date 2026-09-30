"""WBS 1.1 - corpus acquisition.

Downloads the training corpora into 01_Data/raw/ and writes a manifest recording
exactly which commit of each source was used, so the dataset is reproducible and
citable in the final report.

Sources
-------
spamassassin : SpamAssassin public corpus (ham and spam, full RFC 822 messages).
               Obtained from the stdlib-js mirror because apache.org is not
               reachable from the build network. Same corpus, one message per
               JSON file. Apache License 2.0.
phishing_pot : Real phishing messages collected via honeypots, .eml with intact
               headers. Substituted for the Nazario corpus, whose host
               (monkey.org) is unreachable and whose newest samples are from
               2017. MIT License.

Usage
-----
    python 01_Data/src/acquire_corpus.py            # download anything missing
    python 01_Data/src/acquire_corpus.py --refresh  # re-clone from scratch
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

# Corpus files land here. Override with PHISHLENS_RAW_DIR to keep ~400 MB of
# messages out of a synced folder (OneDrive, Dropbox) without touching the code.
RAW_DIR = Path(os.environ.get("PHISHLENS_RAW_DIR") or Path(__file__).resolve().parents[1] / "raw")

# Shallow clones are cached outside the project so a --refresh of one corpus does
# not re-download the other, and so the repository history never enters the
# project folder - only the message files do.
CACHE_DIR = Path(os.environ.get("PHISHLENS_CACHE_DIR") or Path.home() / ".cache" / "phishlens-corpora")

SOURCES = {
    "spamassassin": {
        "url": "https://github.com/stdlib-js/datasets-spam-assassin.git",
        "description": "SpamAssassin public corpus (easy-ham, hard-ham, spam), JSON per message",
        "licence": "Apache-2.0",
        "role": "ham and non-phishing spam",
        "content_path": "data",
    },
    "phishing_pot": {
        "url": "https://github.com/rf-peixoto/phishing_pot.git",
        "description": "Honeypot-collected phishing messages in .eml with full headers",
        "licence": "MIT",
        "role": "phishing",
        "content_path": "email",
    },
}


def run(cmd: list[str], cwd: Path | None = None) -> str:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=1800)
    if result.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} failed:\n{result.stderr.strip()}")
    return result.stdout.strip()


def fetch(name: str, spec: dict, refresh: bool) -> tuple[Path, str]:
    """Clone (or reuse) the source into the cache and return (cache path, commit)."""
    cached = CACHE_DIR / name
    if cached.exists() and refresh:
        shutil.rmtree(cached)
    if cached.exists():
        print(f"  {name}: using cached clone at {cached}")
    else:
        print(f"  {name}: cloning {spec['url']}")
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        run(["git", "clone", "--depth", "1", "--quiet", spec["url"], str(cached)])
    return cached, run(["git", "rev-parse", "HEAD"], cwd=cached)


def install(name: str, spec: dict, cached: Path) -> tuple[Path, list[Path]]:
    """Archive the message files into 01_Data/raw/<name>.tar.gz.

    The corpora are ~29,000 small files. Writing them loose into the project
    folder takes minutes on a synced drive (OneDrive) and leaves the sync client
    churning for the rest of the semester, so raw/ holds one compressed archive
    per corpus instead. normalize.py reads straight out of the archives.
    """
    content = cached / spec["content_path"]
    files = sorted(p for p in content.rglob("*") if p.is_file() and p.suffix in {".json", ".eml"})
    archive = RAW_DIR / f"{name}.tar.gz"
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    tmp = archive.with_suffix(".tar.gz.partial")
    with tarfile.open(tmp, "w:gz", compresslevel=6) as tar:
        for f in files:
            tar.add(f, arcname=str(f.relative_to(content)))
    if archive.exists():
        archive.unlink()
    tmp.rename(archive)
    return archive, files


def describe(name: str, spec: dict, archive: Path, files: list[Path], content_root: Path,
             commit: str) -> dict:
    by_group: dict[str, int] = {}
    for p in files:
        group = p.parent.name if p.parent != content_root else spec["content_path"]
        by_group[group] = by_group.get(group, 0) + 1
    return {
        "archive": archive.name,
        "archive_bytes": archive.stat().st_size,
        "name": name,
        "url": spec["url"],
        "commit": commit,
        "licence": spec["licence"],
        "role": spec["role"],
        "description": spec["description"],
        "content_path": spec["content_path"],
        "file_count": len(files),
        "files_by_group": dict(sorted(by_group.items())),
        "uncompressed_bytes": sum(p.stat().st_size for p in files),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Download PhishLens training corpora.")
    parser.add_argument("--refresh", action="store_true", help="re-clone even if present")
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Corpus root: {RAW_DIR}")

    manifest = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sources": [],
    }
    for name, spec in SOURCES.items():
        cached, commit = fetch(name, spec, args.refresh)
        archive, files = install(name, spec, cached)
        entry = describe(name, spec, archive, files, cached / spec["content_path"], commit)
        manifest["sources"].append(entry)
        print(
            f"  {name}: {entry['file_count']:,} files -> {archive.name}"
            f" ({entry['archive_bytes'] / 1e6:.0f} MB), commit {commit[:10]}"
        )

    manifest_path = RAW_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Manifest written to {manifest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
