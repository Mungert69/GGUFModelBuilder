import ast
import json
import os
import py_compile
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = REPO_ROOT / "model-converter"
SCRIPTS = sorted(p for p in SCRIPT_DIR.glob("*.py") if p.is_file())
SCRIPT_NAMES = {p.name for p in SCRIPTS}

EXPECTED_SCRIPT_NAMES = {
    "add_metadata_gguf.py",
    "add_models_to_collection.py",
    "add_new_enterprise_models.py",
    "auto_build_new_models.py",
    "build_llama.py",
    "delete_models.py",
    "download_convert.py",
    "fix_missing_models.py",
    "get_gguf_tensor_info.py",
    "make_files.py",
    "mark_old_models_converted.py",
    "model_converter.py",
    "recalc_model_sizes.py",
    "reset_attempts.py",
    "run_all_from_json.py",
    "tensor_list_builder.py",
    "update_gguf.py",
    "update_readme.py",
    "upload-files.py",
    "upload_dir_files.py",
}


def _write_file(path: Path, content: str) -> None:
    path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")


def _build_stub_modules(stub_dir: Path) -> None:
    _write_file(
        stub_dir / "dotenv.py",
        """
        def load_dotenv(*args, **kwargs):
            return True
        """,
    )

    _write_file(
        stub_dir / "tqdm.py",
        """
        class _Bar:
            def update(self, _):
                pass
            def close(self):
                pass

        def tqdm(*args, **kwargs):
            return _Bar()
        """,
    )

    _write_file(
        stub_dir / "numpy.py",
        """
        # Minimal import stub for scripts that only need numpy at import time.
        """,
    )

    _write_file(
        stub_dir / "llama_cpp.py",
        """
        class LlamaGrammar:
            @classmethod
            def from_string(cls, _text):
                return cls()

        class Llama:
            def __init__(self, *args, **kwargs):
                pass

            def __call__(self, *args, **kwargs):
                return {"choices": [{"text": '{"new_model": false}'}]}
        """,
    )

    _write_file(
        stub_dir / "gguf.py",
        """
        class GGUFValueType:
            UINT32 = "UINT32"
            FLOAT32 = "FLOAT32"
            BOOL = "BOOL"
            STRING = "STRING"

        class _General:
            ARCHITECTURE = "general.architecture"
            NAME = "general.name"
            DESCRIPTION = "general.description"

        class _Tokenizer:
            CHAT_TEMPLATE = "tokenizer.chat_template"
            PRE = "tokenizer.ggml.pre"
            LIST = "tokenizer.ggml.tokens"
            BOS_token_id = "tokenizer.ggml.bos_token_id"
            EOS_token_id = "tokenizer.ggml.eos_token_id"

        class Keys:
            General = _General
            Tokenizer = _Tokenizer

        class GGUFReader:
            def __init__(self, *args, **kwargs):
                self.fields = {}
                self.tensors = []

            def get_field(self, _key):
                return None

        class GGUFWriter:
            def __init__(self, *args, **kwargs):
                pass
            def add_key_value(self, *args, **kwargs):
                pass
            def add_chat_template(self, *args, **kwargs):
                pass
            def add_tensor_info(self, *args, **kwargs):
                pass
            def write_header_to_file(self):
                pass
            def write_kv_data_to_file(self):
                pass
            def write_ti_data_to_file(self):
                pass
            def write_tensor_data(self, *_args, **_kwargs):
                pass
            def close(self):
                pass
        """,
    )

    _write_file(
        stub_dir / "redis_utils.py",
        """
        class _Redis:
            def ping(self):
                return True

        class FakeCatalog:
            def __init__(self):
                self.r = _Redis()
                self._data = {
                    "org/good-1B": {"parameters": 1000000000, "has_config": True, "converted": False, "attempts": 1, "is_moe": False},
                    "org/bad-unknown": {"parameters": -1, "has_config": False, "converted": False, "attempts": 2, "is_moe": False},
                }

            def load_catalog(self):
                return dict(self._data)

            def get_model(self, model_id):
                return self._data.get(model_id)

            def add_model(self, model_id, info):
                self._data[model_id] = dict(info)
                return True

            def update_model_field(self, model_id, field, value, condition=None):
                self._data.setdefault(model_id, {})
                self._data[model_id][field] = value
                return True

            def delete_model(self, model_id):
                self._data.pop(model_id, None)
                return True

            def import_models_from_list(self, model_ids, defaults=None):
                defaults = defaults or {}
                added = 0
                updated = 0
                for model_id in model_ids:
                    if model_id in self._data:
                        self._data[model_id].update(defaults)
                        updated += 1
                    else:
                        self._data[model_id] = dict(defaults)
                        added += 1
                return {"added": added, "updated": updated}

        _CATALOG = FakeCatalog()

        def init_redis_catalog(*args, **kwargs):
            return _CATALOG
        """,
    )

    _write_file(
        stub_dir / "model_converter.py",
        """
        from redis_utils import init_redis_catalog

        class ModelConverter:
            def __init__(self):
                self.model_catalog = init_redis_catalog()

            def has_config_json(self, _model_id):
                return True

            def get_file_sizes(self, _model_id):
                return 1024 * 1024

            def estimate_parameters(self, _size):
                return int(1e9)

            def is_moe_model(self, _model_id):
                return False

            def check_moe_from_config(self, _model_id):
                return False

            def convert_model(self, _model_id, _is_moe=False, **kwargs):
                return True

            def load_catalog(self):
                return self.model_catalog.load_catalog()

            def run_conversion_cycle(self, daemon_mode=False):
                return True

            def start_daemon(self):
                return True
        """,
    )

    _write_file(
        stub_dir / "make_files.py",
        """
        import os

        QUANT_CONFIGS = [
            ("q8_0", "Q8_0", None, None),
            ("q4_k_m", "Q4_K_M", None, None),
        ]
        api_token = os.getenv("HF_API_TOKEN", "stub-token")
        base_dir = os.getenv("MODEL_BUILDER_TEST_BASE", "/tmp/model_builder_test")

        def upload_large_file(*args, **kwargs):
            return True

        def split_file_standard(*args, **kwargs):
            return []

        def get_model_size(_base_name):
            return int(1e9)

        def quantize_model(*args, **kwargs):
            return True
        """,
    )

    _write_file(
        stub_dir / "update_readme.py",
        """
        def update_readme(*args, **kwargs):
            return True
        """,
    )

    _write_file(
        stub_dir / "add_metadata_gguf.py",
        """
        def add_metadata(*args, **kwargs):
            return True
        """,
    )

    _write_file(
        stub_dir / "build_llama.py",
        """
        def build_and_copy(*args, **kwargs):
            return True
        """,
    )

    _write_file(
        stub_dir / "tensor_list_builder.py",
        """
        def process_quantization(*args, **kwargs):
            return {}
        """,
    )

    _write_file(
        stub_dir / "huggingface_hub.py",
        """
        import os
        from pathlib import Path
        from types import SimpleNamespace
        from datetime import datetime, timezone

        __version__ = "stub"

        def login(*args, **kwargs):
            return True

        def list_models(author=None, search=None, limit=None):
            if author:
                return [SimpleNamespace(id=f"{author}/demo-1B-GGUF", modelId=f"{author}/demo-1B-GGUF", config={"num_parameters": int(1e9)})]
            if search:
                return [SimpleNamespace(id=f"upstream/{search}", modelId=f"upstream/{search}", config={"num_parameters": int(1e9)})]
            return []

        def list_collections(owner=None):
            return []

        def create_collection(title=None, description=None, private=False, exists_ok=True):
            return SimpleNamespace(slug="stub/collection", title=title, url="https://example.com/collection")

        def add_collection_item(*args, **kwargs):
            return True

        def list_repo_files(repo_id=None):
            return ["README.md", "config.json"]

        def hf_hub_download(repo_id=None, filename=None, token=None, repo_type=None):
            base = Path(os.getenv("MODEL_BUILDER_TEST_BASE", "/tmp/model_builder_test"))
            base.mkdir(parents=True, exist_ok=True)
            p = base / f"downloaded_{filename or 'file'}"
            p.write_text("stub", encoding="utf-8")
            return str(p)

        class HfFileSystem:
            def __init__(self, *args, **kwargs):
                pass

        class HfApi:
            def __init__(self, *args, **kwargs):
                pass

            def list_models(self, author=None, search=None, limit=None):
                return list_models(author=author, search=search, limit=limit)

            def model_info(self, model_id):
                return SimpleNamespace(config={"num_parameters": int(1e9)})

            def create_repo(self, *args, **kwargs):
                return True

            def upload_file(self, *args, **kwargs):
                return True

            def file_exists(self, *args, **kwargs):
                return False

            def get_hf_file_metadata(self, *args, **kwargs):
                return SimpleNamespace(last_commit_date=datetime.now(timezone.utc))
        """,
    )


class TestModelConverterScripts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stub_dir = Path(tempfile.mkdtemp(prefix="model_builder_stubs_"))
        cls.fake_home = Path(tempfile.mkdtemp(prefix="model_builder_home_"))
        cls.fake_base = Path(tempfile.mkdtemp(prefix="model_builder_base_"))
        _build_stub_modules(cls.stub_dir)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.stub_dir, ignore_errors=True)
        shutil.rmtree(cls.fake_home, ignore_errors=True)
        shutil.rmtree(cls.fake_base, ignore_errors=True)

    def _run_script(self, script_name: str, argv=None, run_name="__main__", stdin_text=None, timeout=20):
        script_path = SCRIPT_DIR / script_name
        runner = textwrap.dedent(
            """
            import json
            import runpy
            import sys
            import os
            import importlib

            sys.path.insert(0, os.environ["MODEL_BUILDER_TEST_STUBS"])
            preload = [
                "dotenv",
                "tqdm",
                "numpy",
                "llama_cpp",
                "gguf",
                "redis_utils",
                "model_converter",
                "make_files",
                "huggingface_hub",
                "update_readme",
                "add_metadata_gguf",
                "build_llama",
                "tensor_list_builder",
            ]
            for name in preload:
                sys.modules[name] = importlib.import_module(name)
            script = sys.argv[1]
            argv = json.loads(sys.argv[2])
            run_name = sys.argv[3]
            sys.argv = [script] + argv
            runpy.run_path(script, run_name=run_name)
            """
        )
        env = os.environ.copy()
        env["MODEL_BUILDER_TEST_STUBS"] = str(self.stub_dir)
        env["MODEL_BUILDER_TEST_BASE"] = str(self.fake_base)
        env["HOME"] = str(self.fake_home)
        env.pop("HF_API_TOKEN", None)

        return subprocess.run(
            [sys.executable, "-c", runner, str(script_path), json.dumps(argv or []), run_name],
            cwd=str(REPO_ROOT),
            env=env,
            input=stdin_text,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
        )

    def test_script_inventory_matches_expected(self):
        self.assertEqual(SCRIPT_NAMES, EXPECTED_SCRIPT_NAMES)

    def test_all_scripts_parse_as_python(self):
        for script in SCRIPTS:
            with self.subTest(script=script.name):
                ast.parse(script.read_text(encoding="utf-8"), filename=str(script))

    def test_all_scripts_compile(self):
        for script in SCRIPTS:
            with self.subTest(script=script.name):
                py_compile.compile(str(script), doraise=True)

    def test_all_scripts_execute_with_controlled_expectations(self):
        cases = [
            ("add_metadata_gguf.py", ["--help"], "__main__", 0, "usage"),
            ("add_models_to_collection.py", [], "__main__", 1, "HF_API_TOKEN not set"),
            ("add_new_enterprise_models.py", [], "__main__", 1, "Usage: python add_new_enterprise_models.py"),
            ("auto_build_new_models.py", [], "__main__", 1, "Failed to load grammar"),
            ("build_llama.py", [], "__main__", 1, "llama.cpp directory not found"),
            ("delete_models.py", [], "__main__", 0, "Done."),
            ("download_convert.py", [], "__main__", 1, "Hugging Face API token not found"),
            ("fix_missing_models.py", [], "__main__", 1, "Hugging Face API token not found"),
            ("get_gguf_tensor_info.py", [], "__main__", 2, "usage"),
            ("make_files.py", [], "__main__", 0, "Hugging Face API token not found"),
            ("mark_old_models_converted.py", [], "__main__", 0, "Done."),
            ("model_converter.py", [], "__main__", 2, "usage"),
            ("recalc_model_sizes.py", [], "__main__", 0, "Updated parameters"),
            ("reset_attempts.py", [], "__main__", 0, "All model attempts have been reset to 0."),
            ("run_all_from_json.py", [], "__main__", 1, "Usage: python run_all_from_json.py"),
            ("tensor_list_builder.py", [], "__main__", 2, "usage"),
            ("update_gguf.py", [], "__main__", 0, "usage"),
            ("update_readme.py", [], "__main__", 2, "usage"),
            ("upload-files.py", [], "__main__", 2, "usage"),
            ("upload_dir_files.py", [], "__main__", 2, "usage"),
        ]

        for script_name, argv, run_name, expected_code, expected_text in cases:
            with self.subTest(script=script_name):
                result = self._run_script(script_name, argv=argv, run_name=run_name, stdin_text="\n")
                output = (result.stdout or "") + (result.stderr or "")
                self.assertEqual(
                    result.returncode,
                    expected_code,
                    msg=f"{script_name} returned {result.returncode}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
                )
                self.assertIn(
                    expected_text.lower(),
                    output.lower(),
                    msg=f"{script_name} output did not contain expected text '{expected_text}'.\nOutput:\n{output}",
                )


if __name__ == "__main__":
    unittest.main()
