"""Check role-equivalent layer policies across quant presets and boundaries."""
import ast
import json
from pathlib import Path
import re
import shlex
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'model-converter'


def load_policy():
    tree = ast.parse((SCRIPTS / 'tensor_list_builder.py').read_text())
    names = {'iq_ladder', 'k1_ladder', 'k_ladder', 'iq_overflow_ladder', 'quant_substitutions'}
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) or
             (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names for t in n.targets))]
    namespace = dict(json=json, re=re, shlex=shlex)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), 'tensor_list_builder.py', 'exec'), namespace)
    return namespace


class QuantRuleCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = load_policy()
        cls.rules = json.loads((SCRIPTS / 'quant_rules.json').read_text())['rules']
        cls.bases = sorted({base for r in cls.rules for base in r.get('base_type', [])})

    def tier(self, name, base, order=5, moe=True):
        return self.policy['determine_quant_tier']('BF16', base, 'blk.4.' + name,
                                                  moe, order, self.rules)

    def test_role_aliases_inherit_existing_bumps(self):
        pairs = [
            ('ffn_gate_up_exps', 'ffn_gate_exps'),
            ('ffn_gate_chexps', 'ffn_gate_exps'),
            ('ffn_up_chexps', 'ffn_up_exps'),
            ('ffn_down_chexps', 'ffn_down_exps'),
            ('attn_qkv_gate', 'attn_qkv'),
            ('shortconv.in_proj', 'ssm_in'),
            ('shortconv.out_proj', 'ssm_out'),
            ('time_mix_key', 'attn_k'),
            ('time_mix_value', 'attn_v'),
            ('time_mix_output', 'attn_output'),
        ]
        for base in self.bases:
            for order in (0, 1, 2, 5, 8, 9, 10):
                for moe in (False, True):
                    for new, old in pairs:
                        # NVFP4 deliberately keeps specialized attention at Q8_0.
                        if base == 'NVFP4' and new in {
                            'attn_qkv_gate', 'time_mix_key', 'time_mix_value', 'time_mix_output'
                        }:
                            continue
                        with self.subTest(base=base, order=order, moe=moe, layer=new):
                            actual, expected = self.tier(new, base, order, moe), self.tier(old, base, order, moe)
                            self.assertEqual((actual[0], actual[2]), (expected[0], expected[2]))

    def test_nvfp4_attention_selection_and_exclusions(self):
        for moe in (False, True):
            for name in ('attn_q', 'attn_k', 'attn_v', 'attn_qkv', 'attn_output'):
                with self.subTest(name=name, moe=moe):
                    self.assertEqual(self.tier(name, 'NVFP4', moe=moe)[0], 'NVFP4')
            for name in ('attn_q_a', 'attn_q_b', 'attn_k_b', 'attn_v_b',
                         'attn_kv_a_mqa', 'attn_qkv_gate', 'attn_gate',
                         'time_mix_key', 'time_mix_value', 'time_mix_output',
                         'ssm_in', 'ssm_out', 'token_embd', 'output'):
                with self.subTest(name=name, moe=moe):
                    self.assertEqual(self.tier(name, 'NVFP4', moe=moe)[0], 'Q8_0')

    def test_concrete_edge_and_middle_values(self):
        cases = [
            ('Q1_0', 'ffn_gate_up_exps', 0, 'IQ1_M'),
            ('IQ2_XS', 'ffn_gate_up_exps', 0, 'IQ3_XXS'),
            ('IQ3_S', 'ffn_down_chexps', 0, 'IQ4_XS'),
            ('Q2_K', 'ffn_gate_up_exps', 0, 'Q3_K'),
            ('Q4_K', 'ffn_gate_up_exps', 0, 'Q5_K'),
            ('Q4_K', 'ffn_gate_up_exps', 5, 'Q4_K'),
            ('Q5_K', 'ffn_down_chexps', 0, 'Q6_K'),
            ('NVFP4', 'ffn_gate_up_exps', 5, 'NVFP4'),
        ]
        for base, name, order, expected in cases:
            with self.subTest(base=base, name=name, order=order):
                self.assertEqual(self.tier(name, base, order)[0], expected)

    def test_sensitive_controls_use_q8_across_quantized_presets(self):
        controls = next(r for r in self.rules if r.get('force_type') == 'Q8_0')
        for base in controls['base_type']:
            for layer in controls['layer_name']:
                with self.subTest(base=base, layer=layer):
                    kind, _, emit = self.tier(layer.lstrip('*'), base)
                    self.assertEqual(kind, 'Q8_0')
                    self.assertTrue(emit)
        for path in SCRIPTS.glob('quant_configs*.json'):
            for config in json.loads(path.read_text()):
                base = config['type']
                if base not in {'BF16', 'F16', 'F32', 'MXFP4_MOE'}:
                    self.assertIn(base, controls['base_type'])

    def test_full_precision_and_f32_exceptions(self):
        apply = self.policy['apply_precision_override_rule']
        for override in ('BF16', 'F16'):
            kind, _, emit = apply('blk.4.ssm_dt', 'Q8_0', '', True,
                                 self.rules, override, is_moe=True, layer_order=5)
            self.assertEqual(kind, override)
            self.assertTrue(emit)
        for override in (None, 'BF16', 'F16'):
            kind, _, emit = apply('blk.4.ssm_beta_alpha', 'Q8_0', '', True,
                                 self.rules, override, is_moe=True, layer_order=5)
            self.assertEqual(kind, 'F32')
            self.assertTrue(emit)

    def test_generated_patterns_do_not_select_neighbors(self):
        namespace = load_policy()
        namespace['get_current_quant_types'] = lambda _: ({
            'blk.0.ffn_gate': 'BF16', 'blk.0.ffn_gate_inp_shexp': 'BF16',
            'blk.1.ffn_gate_up_exps': 'BF16', 'blk.1.ffn_gate_chexps': 'BF16',
        }, 1)
        for base in ('NVFP4', 'Q2_K', 'IQ3_S', 'Q4_0', 'Q8_0'):
            args = shlex.split(namespace['process_quantization']('unused', str(SCRIPTS / 'quant_rules.json'), base, True))
            patterns = [args[i + 1].rsplit('=', 1) for i in range(0, len(args), 2)]
            router = [kind for pattern, kind in patterns if re.search(pattern, 'blk.0.ffn_gate_inp_shexp.weight')]
            self.assertEqual(router, ['Q8_0'])
            self.assertFalse(any(re.search(pattern, 'blkX0Xffn_gate.weight') for pattern, _ in patterns))

    def test_native_mxfp4_policy_remains_delegated(self):
        self.assertTrue(self.policy['uses_native_llama_tensor_mixing']('MXFP4_MOE'))

    def test_native_precision_is_a_floor_for_protective_bumps(self):
        namespace = load_policy()
        namespace['get_current_quant_types'] = lambda _: ({
            'blk.0.ffn_down': 'BF16', 'blk.0.ffn_up': 'BF16',
            'blk.4.ffn_down': 'BF16', 'blk.0.attn_gate': 'BF16',
            'blk.0.ssm_beta_alpha': 'BF16',
        }, 23)
        native = {'blk.0.ffn_down.weight': 'q6_K', 'blk.0.ffn_up.weight': 'q4_K',
                  'blk.4.ffn_down.weight': 'q6_K', 'blk.0.attn_gate.weight': 'q4_K',
                  'blk.0.ssm_beta_alpha.weight': 'f16'}
        args = shlex.split(namespace['process_quantization'](
            'unused', str(SCRIPTS / 'quant_rules.json'), 'Q4_K', native_types=native))
        patterns = [args[i + 1].rsplit('=', 1) for i in range(0, len(args), 2)]
        def selected(name):
            return [kind for pattern, kind in patterns if re.search(pattern, name + '.weight')]
        self.assertEqual(selected('blk.0.ffn_down'), [])  # Native Q6_K survives.
        self.assertEqual(selected('blk.4.ffn_down'), [])
        self.assertEqual(selected('blk.0.ffn_up'), ['Q5_K'])  # Actual uplift retained.
        self.assertEqual(selected('blk.0.attn_gate'), ['Q8_0'])
        self.assertEqual(selected('blk.0.ssm_beta_alpha'), ['F32'])
        exceeds = namespace['protective_bump_exceeds_native']
        self.assertFalse(exceeds('Q5_K', 'Q6_K'))
        self.assertFalse(exceeds('Q5_K', 'unknown_future_type'))
        self.assertFalse(exceeds('IQ4_NL', 'Q4_K'))
        self.assertTrue(exceeds('Q6_K', 'IQ4_XS'))


if __name__ == '__main__':
    unittest.main()
