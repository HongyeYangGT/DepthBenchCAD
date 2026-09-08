"""Resolve automatic-judge gray-zone rows with manual review labels."""

from __future__ import annotations

import argparse
from pathlib import Path

from depthbenchcad.io import read_jsonl, write_jsonl


def _key(row: dict) -> tuple[str, str, int, str]:
    return (
        str(row["system_id"]),
        str(row["template_id"]),
        int(row["generation_id"]),
        str(row["state_id"]),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audits", required=True)
    parser.add_argument("--reviews", required=True, help="JSONL rows keyed by system/template/generation/state with boolean failed")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    audits = read_jsonl(args.audits)
    review_rows = read_jsonl(args.reviews)
    reviews: dict[tuple[str, str, int, str], bool] = {}
    for row in review_rows:
        if not isinstance(row.get("failed"), bool):
            raise ValueError("every review row must contain boolean failed")
        key = _key(row)
        if key in reviews:
            raise ValueError(f"duplicate review key: {key}")
        reviews[key] = bool(row["failed"])

    resolved = 0
    unresolved = 0
    for row in audits:
        metadata = dict(row.get("metadata", {}))
        if not metadata.get("review_required"):
            continue
        key = _key(row)
        if key not in reviews:
            unresolved += 1
            continue
        label = reviews[key]
        row["failed"] = label
        row["expert_label"] = label
        row["automatic_label"] = False
        row["failure_stage"] = "manual_review_failure" if label else None
        metadata["review_required"] = False
        metadata["review_resolution"] = "manual"
        row["metadata"] = metadata
        resolved += 1

    if unresolved:
        raise SystemExit(f"{unresolved} gray-zone rows still lack manual review labels; output not written")
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    write_jsonl(output, audits)
    print(f"resolved {resolved} gray-zone rows -> {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
