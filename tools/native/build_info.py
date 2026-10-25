"""Write release metadata shared by the native installers for this checkout."""
import json
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[2]
DIST = ROOT / "dist"
MARKETING_VERSION = "0.8.0"


def main():
    commit = subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
    ).strip()
    if not re.fullmatch(r"[0-9a-fA-F]{40}", commit):
        raise RuntimeError("git rev-parse HEAD did not return a full commit SHA.")
    timestamp = int(subprocess.check_output(
        ["git", "-C", str(ROOT), "show", "-s", "--format=%ct", "HEAD"], text=True
    ).strip())
    minute = timestamp // 60
    bundle_version = f"{minute // 10000}.{minute // 100 % 100}.{minute % 100}"
    metadata = {
        "commit_sha": commit.lower(),
        "commit_timestamp": timestamp,
        "marketing_version": MARKETING_VERSION,
        "bundle_version": bundle_version,
    }
    DIST.mkdir(exist_ok=True)
    (DIST / "native-build-info.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"Wrote dist/native-build-info.json for {commit} ({bundle_version}).")


if __name__ == "__main__":
    main()
