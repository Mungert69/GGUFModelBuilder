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
                         needs_compatibility_check=lambda *args: False,
                         llama_cpp_env=lambda binary: {"LD_LIBRARY_PATH": "/models/llama.cpp"})
        quantize = load_function('make_files.py', 'quantize_with_fallback', namespace)
        self.assertTrue(quantize('input.gguf', 'output-nvfp4.gguf', 'NVFP4', use_pure=True))
        command = subprocess.run.call_args.args[0]
        self.assertEqual(command[-4:], ['input.gguf', 'output-nvfp4.gguf.tmp', 'Q8_0', '2'])
        self.assertIn('--pure', command)
        self.assertEqual(subprocess.run.call_args.kwargs['env']['LD_LIBRARY_PATH'], '/models/llama.cpp')
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

    def test_mixed_quantization_uses_native_dry_run_before_overrides(self):
        process = Mock(side_effect=['--tensor-type x=Q5_K', '--tensor-type y=Q5_K'])
        subprocess = Mock()
        subprocess.run.side_effect = [
            Mock(returncode=0, stdout=b'', stderr=(
                b'[   1/   2] blk.0.ffn_down.weight - [256, 256], type = f16, size = 1 MiB -> 0.4 MiB (q6_K)\n'
                b'[   2/   2] blk.0.ffn_gate_inp.weight - [256, 8], type = f32, size = 0.008 MiB\n')),
            Mock(returncode=0, stdout=b'', stderr=b''),
        ]
        namespace = dict(process_quantization=process, quant_rules_path='rules.json',
                         base_dir='/models', threads=2, shlex=shlex, re=re,
                         subprocess=subprocess, os=Mock(),
                         needs_compatibility_check=lambda *args: False,
                         llama_cpp_env=lambda _: {})
        quantize = load_function('make_files.py', 'quantize_with_fallback', namespace)
        self.assertTrue(quantize('in.gguf', 'out.gguf', 'Q4_K',
                                 tensor_type='Q8_0', embed_type='Q8_0', use_imatrix='cal.dat'))
        dry, actual = [call.args[0] for call in subprocess.run.call_args_list]
        self.assertIn('--dry-run', dry)
        self.assertNotIn('--tensor-type', dry)
        for command in (dry, actual):
            self.assertEqual(command[command.index('--imatrix') + 1], 'cal.dat')
            self.assertEqual(command[command.index('--output-tensor-type') + 1], 'Q8_0')
        self.assertEqual(process.call_args.kwargs['native_types'], {
            'blk.0.ffn_down.weight': 'q6_K', 'blk.0.ffn_gate_inp.weight': 'f32'})
        self.assertEqual(actual[actual.index('--tensor-type') + 1], 'y=Q5_K')

    def test_failed_native_dry_run_stops_quantization(self):
        subprocess = Mock()
        subprocess.run.return_value = Mock(returncode=1, stdout=b'', stderr=b'unsupported --dry-run')
        namespace = dict(process_quantization=lambda **_: '--tensor-type x=Q5_K',
                         quant_rules_path='rules.json', base_dir='/models', threads=2,
                         shlex=shlex, re=re, subprocess=subprocess, os=Mock(),
                         needs_compatibility_check=lambda *args: False, llama_cpp_env=lambda _: {})
        quantize = load_function('make_files.py', 'quantize_with_fallback', namespace)
        self.assertFalse(quantize('in.gguf', 'out.gguf', 'Q4_K'))
        subprocess.run.assert_called_once()
        namespace['os'].rename.assert_not_called()


if __name__ == '__main__':
    unittest.main()
