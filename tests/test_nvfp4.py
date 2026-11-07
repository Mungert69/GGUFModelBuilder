"""Exercise command generation without Redis or Hugging Face side effects."""
import ast
import json
from pathlib import Path
import shlex
import re
import unittest
from unittest.mock import Mock

SCRIPTS = Path(__file__).resolve().parents[1] / 'model-converter'


def load_function(filename, name, namespace):
    tree = ast.parse((SCRIPTS / filename).read_text())
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    exec(compile(ast.Module(body=[function], type_ignores=[]), filename, 'exec'), namespace)
    return namespace[name]


class NVFP4Tests(unittest.TestCase):
    def test_nvfp4_command(self):
        namespace = dict(json=json, re=re, shlex=shlex, quant_substitutions={})
        tree = ast.parse((SCRIPTS / 'tensor_list_builder.py').read_text())
        functions = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
        exec(compile(ast.Module(body=functions, type_ignores=[]), 'builder', 'exec'), namespace)
        namespace['get_current_quant_types'] = lambda _: ({
            'blk.0.ffn_up': 'BF16 (30)',
            'blk.0.ffn_down_exps': 'BF16 (30)',
            'blk.0.attn_q': 'BF16 (30)',
            'blk.0.ffn_gate_inp': 'F32 (0)',
            'blk.0.ssm_in': 'BF16 (30)',
            'blk.0.ssm_alpha': 'F32 (0)',
            'token_embd': 'BF16 (30)',
            'output': 'F16 (1)',
        }, 1)
        process = namespace['process_quantization']
        subprocess = Mock()
        subprocess.run.return_value = Mock(returncode=0, stdout=b'', stderr=b'')
        os = Mock()
        namespace = dict(process_quantization=process, quant_rules_path=str(SCRIPTS / 'quant_rules.json'),
                         base_dir='/models', threads=2, shlex=shlex,
                         subprocess=subprocess, os=os,
                         needs_compatibility_check=lambda *args: False)
        quantize = load_function('make_files.py', 'quantize_with_fallback', namespace)
        self.assertTrue(quantize('input.gguf', 'output-nvfp4.gguf', 'NVFP4', use_pure=True))
        command = subprocess.run.call_args.args[0]
        self.assertEqual(command[-4:], ['input.gguf', 'output-nvfp4.gguf.tmp', 'Q8_0', '2'])
        self.assertIn('--pure', command)
        overrides = [command[i + 1].rsplit('=', 1) for i, arg in enumerate(command)
                     if arg == '--tensor-type']
        def tensor_type(name):
            matches = [kind for pattern, kind in overrides if re.search(pattern, name)]
            self.assertEqual(len(matches), 1)
            return matches[0]
        for name in ['blk.0.ffn_up.weight', 'blk.0.ffn_down_exps.weight', 'blk.0.attn_q.weight']:
            self.assertEqual(tensor_type(name), 'NVFP4')
        for name in ['blk.0.ssm_in.weight', 'token_embd.weight']:
            self.assertEqual(tensor_type(name), 'Q8_0')
        self.assertEqual(tensor_type('output.weight'), 'Q8_0')
        self.assertEqual(tensor_type('blk.0.ffn_gate_inp.weight'), 'Q8_0')
        self.assertEqual(tensor_type('blk.0.ssm_alpha.weight'), 'F32')
        self.assertNotIn('--imatrix', command)
        os.rename.assert_called_once_with('output-nvfp4.gguf.tmp', 'output-nvfp4.gguf')

    def test_distributed_preset(self):
        configs = json.loads((SCRIPTS / 'quant_configs_all.json').read_text())
        config, = [c for c in configs if c['type'] == 'NVFP4']
        self.assertEqual(config['name'], 'nvfp4')
        self.assertFalse(config['use_imatrix'])
        self.assertTrue(config['use_pure'])


if __name__ == '__main__':
    unittest.main()
