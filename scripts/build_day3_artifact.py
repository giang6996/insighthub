"""Build deterministic Day 3 deployment and provenance artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify import fingerprint  # noqa: E402


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def deployment_files() -> list[Path]:
    paths = [
        *sorted((ROOT / "infra").glob("*.tf")),
        *sorted((ROOT / "infra" / "policies").glob("*.json")),
        *sorted((ROOT / "deploy").glob("*.yaml")),
        ROOT / "deploy" / "README.md",
    ]
    return [path for path in paths if path.is_file()]


def build_archive(output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for path in deployment_files():
            relative = path.relative_to(ROOT).as_posix()
            info = zipfile.ZipInfo(relative, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path)
    args = parser.parse_args()

    args.output = (ROOT / args.output).resolve() if not args.output.is_absolute() else args.output.resolve()
    args.manifest = (ROOT / args.manifest).resolve() if not args.manifest.is_absolute() else args.manifest.resolve()
    if args.evidence_dir and not args.evidence_dir.is_absolute():
        args.evidence_dir = (ROOT / args.evidence_dir).resolve()

    build_archive(args.output)
    source_hash = fingerprint(ROOT)
    artifact_hash = sha256(args.output)
    binding = {
        "source_sha256": source_hash,
        "artifact_sha256": artifact_hash,
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(binding, indent=2) + "\n", encoding="utf-8")
    if args.evidence_dir:
        args.evidence_dir.mkdir(parents=True, exist_ok=True)
        evidence = {
            "schema_version": 1,
            "day": 3,
            "mode": "real",
            "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "source_sha256": source_hash,
            "artifacts": {
                "deployment": {
                    "path": args.output.relative_to(ROOT).as_posix(),
                    "sha256": artifact_hash,
                },
                "ci_binding": {
                    "path": args.manifest.relative_to(ROOT).as_posix(),
                    "sha256": sha256(args.manifest),
                },
            },
        }
        (args.evidence_dir / "day3.json").write_text(
            json.dumps(evidence, indent=2) + "\n", encoding="utf-8"
        )
    print(json.dumps({**binding, "artifact": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
