import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "pdfs" / "batch_semantic_rechunk.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("batch_semantic_rechunk_under_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


class BatchSemanticRechunkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module()

    def test_compute_coverage_complete_and_incomplete(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            blocks_complete = tmp / "a_20260101010101.json"
            _write_json(blocks_complete, [{"start": 1, "end": 2}, {"start": 3, "end": 5}])
            cov1 = self.mod.compute_coverage(str(blocks_complete), 5)
            self.assertTrue(cov1["is_complete"])
            self.assertEqual(cov1["missing_count"], 0)

            blocks_incomplete = tmp / "b_20260101010101.json"
            _write_json(blocks_incomplete, [{"start": 1, "end": 2}, {"start": 4, "end": 5}])
            cov2 = self.mod.compute_coverage(str(blocks_incomplete), 5)
            self.assertFalse(cov2["is_complete"])
            self.assertEqual(cov2["missing_count"], 1)
            self.assertEqual(cov2["missing_sample"], [3])

    def test_analyze_input_reports_complete_status(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            input_file = tmp / "book_chunks.json"
            _write_json(input_file, [{"output": "a"}, {"output": "b"}, {"output": "c"}])
            output_file = tmp / "book_chunks_20260101010101.json"
            _write_json(output_file, [{"start": 1, "end": 3}])

            cwd = Path.cwd()
            try:
                # analyze_input uses glob in current working directory.
                import os
                os.chdir(tmp)
                result = self.mod.analyze_input("book_chunks.json")
            finally:
                os.chdir(cwd)

            self.assertEqual(result["status"], "complete")
            self.assertEqual(result["coverage"]["missing_count"], 0)

    def test_main_dry_run_writes_status_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            input_file = tmp / "book_chunks.json"
            _write_json(input_file, [{"output": "x"}, {"output": "y"}])

            status_file = tmp / "semantic_batch_status.json"
            argv = [
                "batch_semantic_rechunk.py",
                "--pattern",
                "book_chunks.json",
                "--max-passes",
                "1",
                "--status-file",
                str(status_file),
                "--dry-run",
            ]

            cwd = Path.cwd()
            try:
                import os
                os.chdir(tmp)
                with patch("sys.argv", argv):
                    rc = self.mod.main()
            finally:
                os.chdir(cwd)

            self.assertEqual(rc, 1)
            self.assertTrue(status_file.exists())
            payload = json.loads(status_file.read_text(encoding="utf-8"))
            self.assertIn("passes", payload)
            self.assertEqual(len(payload["passes"]), 1)
            self.assertEqual(payload["passes"][0]["pending_before_count"], 1)

    def test_build_ingest_records_from_work_includes_locator_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            input_file = tmp / "book_chunks.json"
            work_file = tmp / "book_chunks_semantic_work.json"

            _write_json(
                input_file,
                [
                    {"output": "a", "source_title": "Book A", "start_page": 1, "end_page": 1},
                    {"output": "b", "source_title": "Book A", "start_page": 2, "end_page": 3},
                    {"output": "c", "source_title": "Book A", "start_page": 4, "end_page": 4},
                ],
            )
            _write_json(
                work_file,
                [
                    {"start": 1, "end": 2, "question": "Q1", "summary": "S1", "text": "T1"},
                    {"start": 3, "end": 3, "question": "Q2", "summary": "S2", "text": "T2"},
                ],
            )

            records = self.mod.build_ingest_records_from_work(str(input_file), str(work_file))
            self.assertEqual(len(records), 2)
            self.assertEqual(records[0]["chunk_index"], 1)
            self.assertEqual(records[0]["chunk_count"], 2)
            self.assertEqual(records[0]["page_start"], 1)
            self.assertEqual(records[0]["page_end"], 3)
            self.assertEqual(records[0]["source_title"], "Book A")
            self.assertEqual(records[0]["prev_chunk_id"], "")
            self.assertEqual(records[0]["next_chunk_id"], records[1]["chunk_id"])

            self.assertEqual(records[1]["chunk_index"], 2)
            self.assertEqual(records[1]["chunk_start"], 3)
            self.assertEqual(records[1]["chunk_end"], 3)
            self.assertEqual(records[1]["page_start"], 4)
            self.assertEqual(records[1]["page_end"], 4)
            self.assertEqual(records[1]["prev_chunk_id"], records[0]["chunk_id"])
            self.assertEqual(records[1]["next_chunk_id"], "")

    def test_build_ingest_records_from_work_filters_not_book_content(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            input_file = tmp / "book_chunks.json"
            work_file = tmp / "book_chunks_semantic_work.json"

            _write_json(
                input_file,
                [
                    {"output": "a", "source_title": "Book A", "start_page": 1, "end_page": 1},
                    {"output": "b", "source_title": "Book A", "start_page": 2, "end_page": 2},
                ],
            )
            _write_json(
                work_file,
                [
                    {"start": 1, "end": 1, "question": "Q1", "summary": "S1", "text": "T1", "is_book_content": True},
                    {"start": 2, "end": 2, "question": "Q2", "summary": "S2", "text": "T2", "is_book_content": False},
                ],
            )

            records = self.mod.build_ingest_records_from_work(str(input_file), str(work_file))
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["input"], "Q1")

    def test_run_semantic_includes_explicit_output_file(self):
        with patch.object(self.mod.subprocess, "run", return_value=MagicMock(returncode=0)) as run_mock:
            rc = self.mod.run_semantic("script.py", "input.json", output_file="out.json")

        self.assertEqual(rc, 0)
        args = run_mock.call_args[0][0]
        self.assertEqual(args[0], self.mod.sys.executable)
        self.assertEqual(args[1:], ["script.py", "input.json", "out.json", "--single"])


if __name__ == "__main__":
    unittest.main()
