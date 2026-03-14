import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "pdfs" / "semantic_rechunk_qwen3.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("semantic_rechunk_qwen3_under_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class _FakeMessage:
    def __init__(self, content, **kwargs):
        self.content = content
        for key, value in kwargs.items():
            setattr(self, key, value)


class _FakeChoice:
    def __init__(self, content, **kwargs):
        self.message = _FakeMessage(content, **kwargs)


class _FakeResponse:
    def __init__(self, content, **kwargs):
        self.choices = [_FakeChoice(content, **kwargs)]


class SemanticRechunkQwenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module()

    def setUp(self):
        self.mod.tokenizer = None

    def test_get_tokenizer_falls_back_without_tokenizers(self):
        with patch.object(self.mod, "Tokenizer", None):
            tok = self.mod.get_tokenizer()
            encoded = tok.encode("alpha beta gamma")

        self.assertTrue(hasattr(tok, "encode"))
        self.assertIsInstance(encoded, list)
        self.assertGreater(len(encoded), 0)

    def test_extract_boundary_index_handles_reasoning_formats(self):
        self.assertEqual(self.mod.extract_boundary_index("<think>reasoning</think>\nAnswer: 4", 8), 4)
        self.assertEqual(self.mod.extract_boundary_index("<think>x</think>{\"index\": 6}", 8), 6)
        self.assertEqual(self.mod.extract_boundary_index("Final answer -> 3", 8), 3)
        self.assertIsNone(self.mod.extract_boundary_index("<think>no final answer", 8))

    def test_get_semantic_block_end_uses_repair_when_primary_unparseable(self):
        responses = [
            _FakeResponse("<think>very long reasoning and no final answer"),
            _FakeResponse("Answer: 2"),
        ]

        def fake_completion(*args, **kwargs):
            return responses.pop(0)

        with patch.object(self.mod, "safe_chat_completion", side_effect=fake_completion), patch.object(
            self.mod.time, "sleep", return_value=None
        ):
            end_idx, raw = self.mod.get_semantic_block_end(
                ["chunk one", "chunk two", "chunk three"], client=object(), model="test", max_tokens=100
            )

        self.assertEqual(end_idx, 2)
        self.assertIn("Answer", raw)

    def test_summarize_text_strips_think_closed_or_unclosed(self):
        responses = [
            _FakeResponse("<think>hidden</think><question>How does TLS handshake establish session keys?</question>"),
            _FakeResponse("<think>still hidden TLS uses key exchange and certificate validation."),
            _FakeResponse("<summary>TLS uses key exchange and certificate validation. It establishes encrypted sessions and verifies peers.</summary>"),
        ]

        def fake_completion(*args, **kwargs):
            return responses.pop(0)

        with patch.object(self.mod, "safe_chat_completion", side_effect=fake_completion), patch.object(
            self.mod.time, "sleep", return_value=None
        ):
            question, summary = self.mod.summarize_text("TLS handshake and certificate validation details.", object(), "test")

        self.assertNotIn("<think>", question.lower())
        self.assertNotIn("<think>", summary.lower())
        self.assertTrue(question)
        self.assertTrue(summary)

    def test_write_second_json_file_keeps_shape(self):
        class FixedNow:
            def strftime(self, _fmt):
                return "20260313153045"

        class FixedDateTime:
            @staticmethod
            def now():
                return FixedNow()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            input_file = tmp / "book_chunks.json"
            output_file = tmp / "semantic blocks@draft.json"
            input_file.write_text(
                json.dumps(
                    [
                        {"source_title": "Book A", "start_page": 10, "end_page": 10},
                        {"source_title": "Book A", "start_page": 11, "end_page": 12},
                        {"source_title": "Book A", "start_page": 13, "end_page": 13},
                        {"source_title": "Book A", "start_page": 14, "end_page": 14},
                    ]
                ),
                encoding="utf-8",
            )
            output_file.write_text(
                json.dumps(
                    [
                        {"question": "Q1?", "summary": "S1", "text": "T1", "start": 1, "end": 2},
                        {"question": "Q2?", "summary": "S2", "text": "T2", "start": 3, "end": 4},
                    ]
                ),
                encoding="utf-8",
            )

            with patch.object(self.mod, "datetime", FixedDateTime):
                self.mod.write_second_json_file(str(input_file), str(output_file))

            expected = tmp / "semantic_blocksdraft_out_20260313153045.json"
            self.assertTrue(expected.exists())
            data = json.loads(expected.read_text(encoding="utf-8"))
            self.assertEqual(len(data), 2)
            self.assertEqual(data[0]["input"], "Q1?")
            self.assertEqual(data[0]["summary"], "S1")
            self.assertEqual(data[0]["output"], "T1")
            self.assertEqual(data[0]["chunk_index"], 1)
            self.assertEqual(data[0]["chunk_count"], 2)
            self.assertEqual(data[0]["chunk_start"], 1)
            self.assertEqual(data[0]["chunk_end"], 2)
            self.assertEqual(data[0]["page_start"], 10)
            self.assertEqual(data[0]["page_end"], 12)
            self.assertEqual(data[0]["source_title"], "Book A")
            self.assertEqual(data[0]["source_file"], "book_chunks.json")
            self.assertEqual(data[0]["prev_chunk_id"], "")
            self.assertTrue(data[0]["chunk_id"])
            self.assertTrue(data[0]["doc_id"])
            self.assertEqual(data[0]["next_chunk_id"], data[1]["chunk_id"])

            self.assertEqual(data[1]["chunk_index"], 2)
            self.assertEqual(data[1]["chunk_count"], 2)
            self.assertEqual(data[1]["chunk_start"], 3)
            self.assertEqual(data[1]["chunk_end"], 4)
            self.assertEqual(data[1]["prev_chunk_id"], data[0]["chunk_id"])
            self.assertEqual(data[1]["next_chunk_id"], "")

    def test_build_adaptive_window_can_expand_for_min_prompt_tokens(self):
        class TinyTokenizer:
            def encode(self, text):
                return [t for t in text.split() if t]

        chunks = [
            "aaa bbb ccc",
            "ddd eee fff",
            "ggg hhh iii",
            "jjj kkk lll",
        ]

        window_chunks, total_tokens, cur_window_size = self.mod.build_adaptive_window(
            chunks=chunks,
            pointer=0,
            adaptive_window_size=2,
            tokenizer=TinyTokenizer(),
            build_boundary_prompt=lambda numbered: " ".join(numbered),
            max_context=200,
            reserved_output_tokens=20,
            min_prompt_tokens=8,
            max_window_size=10,
        )

        self.assertEqual(cur_window_size, 3)
        self.assertEqual(len(window_chunks), 3)
        self.assertGreaterEqual(total_tokens, 8)

    def test_compute_context_targets_front_matter_uses_lower_floor(self):
        chapter = self.mod.compute_context_targets(
            max_context=100000,
            reserved_output_tokens=20000,
            is_front_matter=False,
            has_section_heading=True,
        )
        front = self.mod.compute_context_targets(
            max_context=100000,
            reserved_output_tokens=20000,
            is_front_matter=True,
            has_section_heading=False,
        )
        self.assertGreater(chapter["target_prompt_tokens"], front["target_prompt_tokens"])
        self.assertGreaterEqual(chapter["max_prompt_tokens"], chapter["target_prompt_tokens"])
        self.assertGreaterEqual(front["max_prompt_tokens"], front["target_prompt_tokens"])
        self.assertLessEqual(chapter["min_prompt_tokens"], chapter["target_prompt_tokens"])
        self.assertLessEqual(front["min_prompt_tokens"], front["target_prompt_tokens"])

    def test_is_timeout_like_error(self):
        self.assertTrue(self.mod.is_timeout_like_error("APITimeoutError('Request timed out.')"))
        self.assertTrue(self.mod.is_timeout_like_error("ReadTimeout when posting"))
        self.assertFalse(self.mod.is_timeout_like_error("parse error no integer in output"))

    def test_apply_heading_transition_guard_trims_large_span(self):
        window = [
            "Chapter 1 Intro",
            "content a",
            "content b",
            "Chapter 2 Next",
            "content c",
            "Chapter 3 More",
            "content d",
            "Chapter 4 Last",
            "content e",
        ]
        with patch.object(self.mod, "MAX_HEADING_TRANSITIONS_PER_BLOCK", 2), patch.object(
            self.mod, "MIN_CHUNKS_BEFORE_HEADING_SPLIT", 3
        ):
            guarded = self.mod.apply_heading_transition_guard(window, corrected_end=9)
        self.assertEqual(guarded, 7)

    def test_apply_front_matter_guard_splits_before_first_heading(self):
        window = [
            "Copyright notice",
            "Table of Contents",
            "Preface text",
            "Chapter 1 Getting Started",
            "body",
        ]
        with patch.object(self.mod, "MIN_CHUNKS_BEFORE_HEADING_SPLIT", 2):
            guarded = self.mod.apply_front_matter_guard(window, corrected_end=5, start_is_front_matter=True)
        self.assertEqual(guarded, 3)

    def test_extract_tagged_or_clean_text_prefers_tag(self):
        text = "<think>reason</think><summary>  Uses Nmap for service discovery.  </summary>"
        value = self.mod.extract_tagged_or_clean_text(text, "summary")
        self.assertEqual(value, "Uses Nmap for service discovery.")

    def test_extract_response_text_reads_reasoning_channel(self):
        resp = _FakeResponse("", reasoning_content="<question>What is packet sniffing?</question>")
        raw = self.mod.extract_response_text(resp)
        parsed = self.mod.extract_tagged_or_clean_text(raw, "question")
        self.assertEqual(parsed, "What is packet sniffing?")

    def test_is_reasoning_only_output(self):
        self.assertTrue(self.mod.is_reasoning_only_output("<think>internal chain</think>"))
        self.assertFalse(self.mod.is_reasoning_only_output("<question>What is SQL injection?</question>"))

    def test_resolve_hf_hub_token_prefers_hf_api_token(self):
        original = dict(os.environ)
        try:
            os.environ["HF_API_TOKEN"] = "token_a"
            os.environ["HF_TOKEN"] = "token_b"
            token, source = self.mod.resolve_hf_hub_token()
            self.assertEqual(token, "token_a")
            self.assertEqual(source, "HF_API_TOKEN")
        finally:
            os.environ.clear()
            os.environ.update(original)

    def test_fallback_question_prefers_heading(self):
        text = "Copyright.\nTable of Contents.\nChapter 5 Social Engineering\nThis chapter discusses pretexting."
        question = self.mod.fallback_question(text)
        self.assertIn("Social Engineering", question)

    def test_parse_content_check_answer_defaults_to_yes_when_unclear(self):
        keep, _ = self.mod.parse_content_check_answer("unclear response")
        self.assertTrue(keep)
        keep, _ = self.mod.parse_content_check_answer("no")
        self.assertFalse(keep)
        keep, _ = self.mod.parse_content_check_answer("<think>reason</think> yes")
        self.assertTrue(keep)

    def test_build_ingest_records_filters_blocks_marked_not_book_content(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            input_file = tmp / "book_chunks.json"
            input_file.write_text(
                json.dumps(
                    [
                        {"source_title": "Book A", "start_page": 1, "end_page": 1},
                        {"source_title": "Book A", "start_page": 2, "end_page": 2},
                    ]
                ),
                encoding="utf-8",
            )
            blocks = [
                {"start": 1, "end": 1, "question": "Q1", "summary": "S1", "text": "T1", "is_book_content": True},
                {"start": 2, "end": 2, "question": "Q2", "summary": "S2", "text": "T2", "is_book_content": False},
            ]
            records = self.mod.build_ingest_records(str(input_file), blocks)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["input"], "Q1")

if __name__ == "__main__":
    unittest.main()
