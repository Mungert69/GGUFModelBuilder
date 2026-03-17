#!/usr/bin/env python3
import argparse
import glob
import json
import os
from collections import Counter


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def resolve_index_dir(candidate_dir):
    """
    Resolve an index directory for reporting.
    If candidate_dir does not contain stage1_json_manifest.json, try to auto-discover
    a single child directory that does.
    """
    candidate_dir = os.path.abspath(candidate_dir)
    manifest = os.path.join(candidate_dir, "stage1_json_manifest.json")
    if os.path.exists(manifest):
        return candidate_dir, None

    hits = []
    try:
        for entry in sorted(os.listdir(candidate_dir)):
            sub = os.path.join(candidate_dir, entry)
            if not os.path.isdir(sub):
                continue
            sub_manifest = os.path.join(sub, "stage1_json_manifest.json")
            if os.path.exists(sub_manifest):
                hits.append(sub)
    except Exception:
        pass

    if len(hits) == 1:
        return hits[0], f"Auto-detected index dir: {hits[0]}"
    if len(hits) > 1:
        return candidate_dir, (
            "Multiple index dirs detected. Use --index-dir explicitly.\n"
            + "\n".join(f"  - {p}" for p in hits)
        )
    return candidate_dir, None


def fmt_bool(value):
    return "yes" if value else "no"


def stage1_report(index_dir):
    manifest_path = os.path.join(index_dir, "stage1_json_manifest.json")
    report = {
        "manifest_path": manifest_path,
        "exists": os.path.exists(manifest_path),
        "total": 0,
        "by_status": {},
        "missing_on_disk": 0,
    }
    if not report["exists"]:
        return report

    try:
        payload = load_json(manifest_path)
    except Exception as exc:
        report["error"] = f"parse_error: {exc!r}"
        return report

    files = payload.get("files", [])
    if not isinstance(files, list):
        report["error"] = "invalid_manifest: files is not a list"
        return report

    status_counter = Counter()
    missing_on_disk = 0
    cwd = str(payload.get("cwd") or "").strip()

    for item in files:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "unknown").strip().lower() or "unknown"
        status_counter[status] += 1
        output_json = str(item.get("output_json") or "").strip()
        if output_json:
            if os.path.isabs(output_json):
                candidate = output_json
            elif cwd:
                candidate = os.path.join(cwd, output_json)
            else:
                candidate = os.path.join(index_dir, output_json)
            if not os.path.exists(candidate):
                missing_on_disk += 1

    report["total"] = sum(status_counter.values())
    report["by_status"] = dict(status_counter)
    report["missing_on_disk"] = missing_on_disk
    return report


def stage2_report(index_dir):
    batch_status_path = os.path.join(index_dir, "semantic_batch_status.json")
    inputs_status_path = os.path.join(index_dir, ".semantic_work", "semantic_batch_inputs.json")

    report = {
        "batch_status_path": batch_status_path,
        "batch_status_exists": os.path.exists(batch_status_path),
        "inputs_status_path": inputs_status_path,
        "inputs_status_exists": os.path.exists(inputs_status_path),
    }

    if report["batch_status_exists"]:
        try:
            batch_status = load_json(batch_status_path)
            passes = batch_status.get("passes", [])
            latest = passes[-1] if isinstance(passes, list) and passes else {}
            report["batch_started_at"] = batch_status.get("started_at")
            report["batch_ended_at"] = batch_status.get("ended_at")
            report["passes_count"] = len(passes) if isinstance(passes, list) else 0
            report["latest_pass"] = latest.get("pass")
            report["stage2_message"] = latest.get("message")
            report["stage2_pending_before"] = latest.get("pending_before_count")
            report["stage2_pending_after"] = latest.get("pending_after_count")
        except Exception as exc:
            report["batch_status_error"] = f"parse_error: {exc!r}"

    if report["inputs_status_exists"]:
        try:
            inputs = load_json(inputs_status_path)
            rows = inputs.get("inputs", [])
            status_counter = Counter()
            for row in rows if isinstance(rows, list) else []:
                if not isinstance(row, dict):
                    continue
                status_counter[str(row.get("status") or "unknown")] += 1
            report["inputs_total"] = sum(status_counter.values())
            report["inputs_by_status"] = dict(status_counter)
        except Exception as exc:
            report["inputs_status_error"] = f"parse_error: {exc!r}"

    return report


def is_step_finished(status_file):
    if not os.path.exists(status_file):
        return False
    try:
        payload = load_json(status_file)
    except Exception:
        return False
    return isinstance(payload, dict) and bool(payload.get("finished_at"))


def stage3_report(index_dir):
    work_dir = os.path.join(index_dir, ".semantic_work")
    status_dir = os.path.join(work_dir, ".postprocess_state")
    work_files = sorted(glob.glob(os.path.join(work_dir, "*_semantic_work.json")))

    report = {
        "work_dir": work_dir,
        "status_dir": status_dir,
        "work_files_total": len(work_files),
        "status_dir_exists": os.path.isdir(status_dir),
    }
    if not os.path.isdir(status_dir):
        return report

    complete = 0
    partial = 0
    pending = 0
    active_candidates = []
    steps = ("filter", "questions", "summaries")

    for wf in work_files:
        base = os.path.splitext(os.path.basename(wf))[0]
        flags = []
        for step in steps:
            sf = os.path.join(status_dir, f"{base}.{step}.status.json")
            done = is_step_finished(sf)
            flags.append(done)
            if os.path.exists(sf):
                try:
                    payload = load_json(sf)
                    if isinstance(payload, dict) and not payload.get("finished_at"):
                        active_candidates.append(
                            (
                                payload.get("updated_at") or payload.get("started_at") or "",
                                base,
                                step,
                                sf,
                            )
                        )
                except Exception:
                    pass
        if all(flags):
            complete += 1
        elif any(flags):
            partial += 1
        else:
            pending += 1

    report["complete_files"] = complete
    report["partial_files"] = partial
    report["pending_files"] = pending

    if active_candidates:
        active_candidates.sort(reverse=True)
        ts, base, step, sf = active_candidates[0]
        report["active_file"] = f"{base}.json"
        report["active_step"] = step
        report["active_updated_at"] = ts
        report["active_status_file"] = sf

    return report


def stage4_report(index_dir):
    report = {
        "ingest_files_total": 0,
        "up_to_date_count": 0,
        "stale_or_missing_count": 0,
        "schema_ok_count": 0,
        "schema_fail_count": 0,
        "stale_or_missing_examples": [],
        "schema_fail_examples": [],
    }
    work_dir = os.path.join(index_dir, ".semantic_work")
    work_files = sorted(glob.glob(os.path.join(work_dir, "*_semantic_work.json")))
    if not work_files:
        return report

    required_keys = {
        "input",
        "summary",
        "output",
        "alt_question_1",
        "alt_question_2",
        "alt_question_3",
        "doc_id",
        "chunk_id",
        "chunk_index",
        "chunk_count",
        "chunk_start",
        "chunk_end",
        "semantic_block_index",
        "source_title",
        "source_file",
        "source_chunk_total",
        "page_start",
        "page_end",
        "prev_chunk_id",
        "next_chunk_id",
    }

    for wf in work_files:
        base = os.path.basename(wf).replace("_semantic_work.json", "")
        ingest = os.path.join(index_dir, f"{base}_semantic_ingest.json")
        report["ingest_files_total"] += 1

        if (not os.path.exists(ingest)) or (os.path.getmtime(ingest) < os.path.getmtime(wf)):
            report["stale_or_missing_count"] += 1
            if len(report["stale_or_missing_examples"]) < 10:
                report["stale_or_missing_examples"].append(
                    {
                        "work_file": os.path.basename(wf),
                        "ingest_file": os.path.basename(ingest),
                        "exists": os.path.exists(ingest),
                    }
                )
            continue

        report["up_to_date_count"] += 1
        try:
            payload = load_json(ingest)
        except Exception as exc:
            report["schema_fail_count"] += 1
            if len(report["schema_fail_examples"]) < 10:
                report["schema_fail_examples"].append(
                    {"ingest_file": os.path.basename(ingest), "error": f"parse_error: {exc!r}"}
                )
            continue

        if not isinstance(payload, list):
            report["schema_fail_count"] += 1
            if len(report["schema_fail_examples"]) < 10:
                report["schema_fail_examples"].append(
                    {"ingest_file": os.path.basename(ingest), "error": "not_json_list"}
                )
            continue

        if not payload:
            # empty list is still valid JSON, but mark as fail for pipeline output expectations.
            report["schema_fail_count"] += 1
            if len(report["schema_fail_examples"]) < 10:
                report["schema_fail_examples"].append(
                    {"ingest_file": os.path.basename(ingest), "error": "empty_list"}
                )
            continue

        first = payload[0]
        if not isinstance(first, dict):
            report["schema_fail_count"] += 1
            if len(report["schema_fail_examples"]) < 10:
                report["schema_fail_examples"].append(
                    {"ingest_file": os.path.basename(ingest), "error": "first_item_not_object"}
                )
            continue

        missing = sorted(required_keys - set(first.keys()))
        if missing:
            report["schema_fail_count"] += 1
            if len(report["schema_fail_examples"]) < 10:
                report["schema_fail_examples"].append(
                    {"ingest_file": os.path.basename(ingest), "missing_keys": missing}
                )
            continue

        report["schema_ok_count"] += 1

    return report


def print_report(index_dir, s1, s2, s3, s4):
    print(f"Index Dir: {index_dir}")
    print("")
    print("Stage 1:")
    print(f"  Manifest Exists: {fmt_bool(s1.get('exists'))}")
    print(f"  Manifest Path  : {s1.get('manifest_path')}")
    if s1.get("error"):
        print(f"  Error          : {s1['error']}")
    else:
        print(f"  Files Total    : {s1.get('total', 0)}")
        print(f"  By Status      : {s1.get('by_status', {})}")
        print(f"  Missing On Disk: {s1.get('missing_on_disk', 0)}")

    print("")
    print("Stage 2:")
    print(f"  Batch Status Exists : {fmt_bool(s2.get('batch_status_exists'))}")
    print(f"  Batch Status Path   : {s2.get('batch_status_path')}")
    if s2.get("batch_status_error"):
        print(f"  Batch Status Error  : {s2['batch_status_error']}")
    else:
        print(f"  Batch Started At    : {s2.get('batch_started_at')}")
        print(f"  Batch Ended At      : {s2.get('batch_ended_at')}")
        print(f"  Passes Count        : {s2.get('passes_count')}")
        print(f"  Latest Pass         : {s2.get('latest_pass')}")
        print(f"  Stage2 Message      : {s2.get('stage2_message')}")
        print(f"  Pending Before      : {s2.get('stage2_pending_before')}")
        print(f"  Pending After       : {s2.get('stage2_pending_after')}")
    print(f"  Inputs Status Exists: {fmt_bool(s2.get('inputs_status_exists'))}")
    print(f"  Inputs Status Path  : {s2.get('inputs_status_path')}")
    if s2.get("inputs_status_error"):
        print(f"  Inputs Status Error : {s2['inputs_status_error']}")
    else:
        print(f"  Inputs Total        : {s2.get('inputs_total')}")
        print(f"  Inputs By Status    : {s2.get('inputs_by_status')}")

    print("")
    print("Stage 3:")
    print(f"  Work Dir Exists   : {fmt_bool(os.path.isdir(s3.get('work_dir', '')))}")
    print(f"  Status Dir Exists : {fmt_bool(s3.get('status_dir_exists'))}")
    print(f"  Work Files Total  : {s3.get('work_files_total', 0)}")
    print(f"  Complete Files    : {s3.get('complete_files', 0)}")
    print(f"  Partial Files     : {s3.get('partial_files', 0)}")
    print(f"  Pending Files     : {s3.get('pending_files', 0)}")
    if s3.get("active_file"):
        print(f"  Active File       : {s3.get('active_file')}")
        print(f"  Active Step       : {s3.get('active_step')}")
        print(f"  Active Updated At : {s3.get('active_updated_at')}")

    print("")
    print("Stage 4:")
    print(f"  Ingest Targets      : {s4.get('ingest_files_total', 0)}")
    print(f"  Up-to-date Ingest   : {s4.get('up_to_date_count', 0)}")
    print(f"  Stale/Missing Ingest: {s4.get('stale_or_missing_count', 0)}")
    print(f"  Schema OK           : {s4.get('schema_ok_count', 0)}")
    print(f"  Schema Fail         : {s4.get('schema_fail_count', 0)}")
    if s4.get("stale_or_missing_examples"):
        print(f"  Stale Examples      : {s4.get('stale_or_missing_examples')[:3]}")
    if s4.get("schema_fail_examples"):
        print(f"  Schema Fail Examples: {s4.get('schema_fail_examples')[:3]}")


def main():
    parser = argparse.ArgumentParser(description="Report Stage-1/2/3 batch status from status files.")
    parser.add_argument(
        "--index-dir",
        default=os.getcwd(),
        help="Index directory containing stage1_json_manifest.json and .semantic_work/",
    )
    parser.add_argument("--json", action="store_true", help="Print report as JSON.")
    args = parser.parse_args()

    index_dir, note = resolve_index_dir(args.index_dir)
    s1 = stage1_report(index_dir)
    s2 = stage2_report(index_dir)
    s3 = stage3_report(index_dir)
    s4 = stage4_report(index_dir)
    payload = {
        "index_dir": index_dir,
        "stage1": s1,
        "stage2": s2,
        "stage3": s3,
        "stage4": s4,
    }

    if args.json:
        if note:
            payload["note"] = note
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if note:
        print(f"Note: {note}")
        print("")
    print_report(index_dir, s1, s2, s3, s4)


if __name__ == "__main__":
    main()
