"""Check library selection without importing the network-connected pipeline."""
import ast
import os
from pathlib import Path
import shutil
import sys
import unittest
from unittest.mock import patch


class LlamaRuntimeTests(unittest.TestCase):
    def setUp(self):
        source = Path(__file__).resolve().parents[1] / 'make_files.py'
        tree = ast.parse(source.read_text())
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                        and n.name == 'llama_cpp_env')
        namespace = dict(os=os, sys=sys, Path=Path, shutil=shutil)
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), 'exec'), namespace)
        self.make_env = namespace['llama_cpp_env']

    def test_local_libraries_precede_existing_search_path(self):
        with patch.object(sys, 'platform', 'linux'), patch.dict(os.environ, {'LD_LIBRARY_PATH': '/custom/libs'}, clear=True):
            env = self.make_env('/opt/llama/llama-quantize')
            self.assertEqual(env['LD_LIBRARY_PATH'], '/opt/llama:/custom/libs')
            self.assertEqual(os.environ['LD_LIBRARY_PATH'], '/custom/libs')

    def test_unset_search_path_does_not_include_working_directory(self):
        with patch.object(sys, 'platform', 'linux'), patch.dict(os.environ, {}, clear=True):
            self.assertEqual(self.make_env('/opt/llama/llama-quantize')['LD_LIBRARY_PATH'], '/opt/llama')

    def test_other_platform_preserves_environment(self):
        with patch.object(sys, 'platform', 'darwin'), patch.dict(os.environ, {'EXAMPLE': 'value'}, clear=True):
            self.assertEqual(self.make_env('/opt/llama/llama-quantize'), {'EXAMPLE': 'value'})


if __name__ == '__main__':
    unittest.main()
