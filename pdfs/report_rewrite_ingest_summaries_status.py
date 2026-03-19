#!/usr/bin/env python3
import argparse
import glob
import json
import os
from collections import Counter
from typing import Any, Dict, List, Tuple


def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def fmt_bool(value: Any) -> str:
    return "yes" if bool(value) else "no"


def _records_state_counts(records: Dict[str, Any]) -> Dict[str, int]:
    c = Counter()
    if not isinstance(records, dict):
        return {}
    for rec in records.values():
        if isinstance(rec, dict):
            c[str(rec.get("state") or "unknown")] += 1
        else:
            c["unknown"] += 1
    return dict(c)


def rewrite_report(index_dir: str, ingest_pattern: str, status_file: str) -> Dict[str, Any]:
    index_dir = os.path.abspath(index_dir)
    ingest_files = sorted(glob.glob(os.path.join(index_dir, ingest_pattern)))
    ingest_files = [p for p in ingest_files if os.path.isfile(p)]

    if status_file.strip():
        status_path = os.path.abspath(status_file)
    else:
        status_path = os.path.join(index_dir, ".rewrite_ingest_summaries_status.json")

    report: Dict[str, Any] = {
        "index_dir": index_dir,
        "ingest_pattern": ingest_pattern,
        "status_file": status_path,
        "ingest_files_total": len(ingest_files),
        "status_exists": os.path.exists(status_path),
        "tracked_files_total": 0,
        "by_state": {},
        "active": None,
        "errors": [],
        "examples": [],
        "pending_without_status": [],
        "totals": {
            "rows_done": 0,
            "rows_rewritten": 0,
            "rows_skipped": 0,
            "rows_failed": 0,
        },
    }

    if not os.path.exists(status_path):
        report["pending_without_status"] = ingest_files[:20]
        report["by_state"] = {"pending_no_status": len(ingest_files)}
        return report

    try:
        payload = load_json(status_path)
        if not isinstance(payload, dict):
            raise ValueError("status payload is not an object")
    except Exception as exc:
        report["errors"].append({"status_file": status_path, "error": f"parse_error: {exc!r}"})
        report["by_state"] = {"status_parse_error": 1}
        report["pending_without_status"] = ingest_files[:20]
        return report

    files_state = payload.get("files")
    if not isinstance(files_state, dict):
        files_state = {}

    report["tracked_files_total"] = len(files_state)
    by_state = Counter()
    seen_ingest = set()
    active_candidates: List[Tuple[str, Dict[str, Any]]] = []

    for ingest_path, state in files_state.items():
        ap = os.path.abspath(str(ingest_path))
        seen_ingest.add(ap)

        if not isinstance(state, dict):
            by_state["bad_state"] += 1
            continue

        done_indices = state.get("done_indices") or []
        records = state.get("records") or {}
        stats = state.get("stats") or {}

        rows_done = len(done_indices) if isinstance(done_indices, list) else 0
        rows_rewritten = int(stats.get("rewritten") or 0)
        rows_skipped = int(stats.get("skipped") or 0)
        rows_failed = int(stats.get("failed") or 0)

        report["totals"]["rows_done"] += rows_done
        report["totals"]["rows_rewritten"] += rows_rewritten
        report["totals"]["rows_skipped"] += rows_skipped
        report["totals"]["rows_failed"] += rows_failed

        row_total = 0
        payload_sig = state.get("payload_signature")
        if isinstance(payload_sig, dict):
            row_total = int(payload_sig.get("rows") or 0)

        if row_total > 0 and rows_done >= row_total and rows_failed == 0:
            run_state = "done"
        elif rows_done == 0 and rows_failed == 0:
            run_state = "not_started"
        elif rows_failed > 0:
            run_state = "in_progress_with_failures"
        else:
            run_state = "in_progress"
        by_state[run_state] += 1

        item = {
            "ingest_file": ap,
            "updated_at": state.get("updated_at"),
            "summary_token_cap": state.get("summary_token_cap"),
            "rows_total": row_total,
            "rows_done": rows_done,
            "rows_remaining": max(0, row_total - rows_done) if row_total > 0 else None,
            "stats": {
                "rewritten": rows_rewritten,
                "skipped": rows_skipped,
                "failed": rows_failed,
            },
            "record_states": _records_state_counts(records),
            "run_state": run_state,
        }
        if len(report["examples"]) < 20:
            report["examples"].append(item)

        if run_state != "done":
            ts = str(state.get("updated_at") or "")
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
    report["started_at"] = payload.get("started_at")
    report["updated_at"] = payload.get("updated_at")
    report["version"] = payload.get("version")
    return report


def print_report(payload: Dict[str, Any]) -> None:
    print(f"Index Dir: {payload.get('index_dir')}")
    print("")
    print("Rewrite Ingest Summaries:")
    print(f"  Ingest Files Total     : {payload.get('ingest_files_total', 0)}")
    print(f"  Status File            : {payload.get('status_file')}")
    print(f"  Status Exists          : {fmt_bool(payload.get('status_exists'))}")
    print(f"  Tracked Files Total    : {payload.get('tracked_files_total', 0)}")
    print(f"  By State               : {payload.get('by_state', {})}")
    print(f"  Totals                 : {payload.get('totals', {})}")
    print(f"  Errors                 : {len(payload.get('errors') or [])}")
    print(f"  Pending w/o Status     : {len(payload.get('pending_without_status') or [])}")

    active = payload.get("active")
    if active:
        print("")
        print("Active File:")
        print(f"  Ingest File            : {active.get('ingest_file')}")
        print(f"  Run State              : {active.get('run_state')}")
        print(f"  Rows Done/Total        : {active.get('rows_done')}/{active.get('rows_total')}")
        print(f"  Rows Remaining         : {active.get('rows_remaining')}")
        st = active.get("stats") or {}
        print(f"  Rewritten/Skipped/Failed: {st.get('rewritten', 0)}/{st.get('skipped', 0)}/{st.get('failed', 0)}")
        print(f"  Updated At             : {active.get('updated_at')}")

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
    parser = argparse.ArgumentParser(description="Report rewrite-ingest-summaries status.")
    parser.add_argument("--index-dir", default=os.getcwd(), help="Directory containing ingest files.")
    parser.add_argument("--pattern", default="*_semantic_ingest.json", help="Ingest source pattern.")
    parser.add_argument("--status-file", default="", help="Path to .rewrite_ingest_summaries_status.json")
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    args = parser.parse_args()

    payload = rewrite_report(index_dir=args.index_dir, ingest_pattern=args.pattern, status_file=args.status_file)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    print_report(payload)


if __name__ == "__main__":
    main()
