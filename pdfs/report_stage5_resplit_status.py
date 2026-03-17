#!/usr/bin/env python3
import argparse
import glob
import json
import os
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple


def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def fmt_bool(value: Any) -> str:
    return "yes" if bool(value) else "no"


def stage5_report(index_dir: str, ingest_pattern: str) -> Dict[str, Any]:
    index_dir = os.path.abspath(index_dir)
    ingest_files = sorted(glob.glob(os.path.join(index_dir, ingest_pattern)))
    status_files = sorted(glob.glob(os.path.join(index_dir, "*.stage5_status.json")))
    work_files = sorted(glob.glob(os.path.join(index_dir, "*.stage5_work.json")))
    resplit_outputs = sorted(glob.glob(os.path.join(index_dir, "*_semantic_ingest_resplit.json")))

    report: Dict[str, Any] = {
        "index_dir": index_dir,
        "ingest_pattern": ingest_pattern,
        "ingest_files_total": len([p for p in ingest_files if os.path.isfile(p)]),
        "status_files_total": len([p for p in status_files if os.path.isfile(p)]),
        "work_files_total": len([p for p in work_files if os.path.isfile(p)]),
        "resplit_outputs_total": len([p for p in resplit_outputs if os.path.isfile(p)]),
        "by_state": {},
        "active": None,
        "errors": [],
        "examples": [],
        "pending_without_status": [],
    }

    by_state = Counter()
    active_candidates: List[Tuple[str, Dict[str, Any]]] = []
    seen_ingest = set()

    for sf in status_files:
        if not os.path.isfile(sf):
            continue
        try:
            payload = load_json(sf)
            if not isinstance(payload, dict):
                raise ValueError("status payload is not an object")
        except Exception as exc:
            report["errors"].append({"status_file": sf, "error": f"parse_error: {exc!r}"})
            by_state["status_parse_error"] += 1
            continue

        ingest_path = str(payload.get("ingest_path") or "")
        output_path = str(payload.get("output_path") or "")
        phase = str(payload.get("phase") or "unknown")
        done = bool(payload.get("done"))
        failed = bool(payload.get("failed"))
        output_exists = bool(output_path and os.path.exists(output_path))
        split_next = int(payload.get("split_next_source_index") or 0)
        regen_next = int(payload.get("regen_next_changed_pos") or 0)
        changed_indices = payload.get("changed_indices") or []
        changed_total = len(changed_indices) if isinstance(changed_indices, list) else 0

        if ingest_path:
            seen_ingest.add(os.path.abspath(ingest_path))

        if done and output_exists:
            state = "done"
        elif done and not output_exists:
            state = "done_output_missing"
        elif failed:
            state = "failed"
        elif phase == "split":
            state = "in_split"
        elif phase == "regen":
            state = "in_regen"
        else:
            state = "unknown"
        by_state[state] += 1

        item = {
            "status_file": sf,
            "ingest_file": ingest_path,
            "output_file": output_path,
            "output_exists": output_exists,
            "phase": phase,
            "done": done,
            "failed": failed,
            "split_next_source_index": split_next,
            "regen_next_changed_pos": regen_next,
            "changed_total": changed_total,
            "oversized_before": payload.get("oversized_before"),
            "oversized_after": payload.get("oversized_after"),
            "rows_after": payload.get("rows_after"),
            "updated_at": payload.get("updated_at"),
            "failed_at": payload.get("failed_at"),
            "last_error": payload.get("last_error"),
        }
        if len(report["examples"]) < 20:
            report["examples"].append(item)

        if not done:
            ts = str(payload.get("updated_at") or payload.get("failed_at") or "")
            active_candidates.append((ts, item))

    for ingest in ingest_files:
        ap = os.path.abspath(ingest)
        if ap not in seen_ingest:
            report["pending_without_status"].append(ingest)

    if len(report["pending_without_status"]) > 20:
        report["pending_without_status"] = report["pending_without_status"][:20]

    if active_candidates:
        active_candidates.sort(key=lambda x: x[0], reverse=True)
        report["active"] = active_candidates[0][1]

    report["by_state"] = dict(by_state)
    return report


def print_report(payload: Dict[str, Any]) -> None:
    print(f"Index Dir: {payload.get('index_dir')}")
    print("")
    print("Stage-5 Resplit:")
    print(f"  Ingest Files Total    : {payload.get('ingest_files_total', 0)}")
    print(f"  Status Files Total    : {payload.get('status_files_total', 0)}")
    print(f"  Work Files Total      : {payload.get('work_files_total', 0)}")
    print(f"  Resplit Outputs Total : {payload.get('resplit_outputs_total', 0)}")
    print(f"  By State              : {payload.get('by_state', {})}")
    print(f"  Errors                : {len(payload.get('errors') or [])}")
    print(f"  Pending w/o Status    : {len(payload.get('pending_without_status') or [])}")

    active = payload.get("active")
    if active:
        print("")
        print("Active File:")
        print(f"  Ingest File           : {active.get('ingest_file')}")
        print(f"  Phase                 : {active.get('phase')}")
        print(f"  Failed                : {fmt_bool(active.get('failed'))}")
        print(f"  Split Next Source Idx : {active.get('split_next_source_index')}")
        print(f"  Regen Next Changed Pos: {active.get('regen_next_changed_pos')}")
        print(f"  Changed Total         : {active.get('changed_total')}")
        print(f"  Updated At            : {active.get('updated_at')}")
        if active.get("last_error"):
            print(f"  Last Error            : {active.get('last_error')}")

    if payload.get("pending_without_status"):
        print("")
        print("Pending Without Status (sample):")
        for path in payload["pending_without_status"][:10]:
            print(f"  - {path}")

    if payload.get("errors"):
        print("")
        print("Status Parse Errors (sample):")
        for item in payload["errors"][:5]:
            print(f"  - {item}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Report stage-5 resplit status.")
    parser.add_argument("--index-dir", default=os.getcwd(), help="Directory containing ingest/status/work files.")
    parser.add_argument("--pattern", default="*_semantic_ingest.json", help="Ingest source pattern to measure pending files.")
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    args = parser.parse_args()

    payload = stage5_report(index_dir=args.index_dir, ingest_pattern=args.pattern)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    print_report(payload)


if __name__ == "__main__":
    main()

