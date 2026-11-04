"""Adversarial checks for the candidate-local transparent-delay audit."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools/timing'))
from headroom_eco import audit_transparent, render_script
from headroom_campaign import arcs
from headroom_release import checked_precheck, comparison
from check_signoff import REQUIRED_CORNERS


class TransparentDelayAuditTests(unittest.TestCase):
    def fixture(self):
        cells = {'clock': ('sg13cmos5l_buf_8', {'A': 'clk', 'X': 'ctree'}),
                 'gate': ('sg13cmos5l_a21oi_1', {'A1': 'a', 'A2': 'b', 'B1': 'c', 'Y': 'data'}),
                 'ff': ('sg13cmos5l_dfrbpq_1', {'D': 'data', 'CLK': 'ctree', 'Q': 'q'})}
        return (cells, {'clk': 'clk'}, {'clk', 'ctree', 'a', 'b', 'c', 'data', 'q'},
                {'clk': [('clock', 'A')], 'ctree': [('ff', 'CLK')], 'data': [('ff', 'D')]}, {('ff', 'CLK')})

    def repaired(self, master='sg13cmos5l_dlygate4sd1_1'):
        result = self.fixture()
        result[0]['eco_data_0_0'] = (master, {'A': 'data', 'X': 'delayed'})
        result[0]['ff'][1]['D'] = 'delayed'
        result[2].add('delayed')
        result[3]['data'] = [('eco_data_0_0', 'A')]
        result[3]['delayed'] = [('ff', 'D')]
        return result

    def operation(self, **kwargs):
        return dict(kind='buffer', target='gate/Y', old='sg13cmos5l_a21oi_1',
                    max_loads=1, buffer_cell=kwargs.get('buffer_cell', 'sg13cmos5l_dlygate4sd1_1'))

    def test_declared_delay_preserves_original_data_and_clock(self):
        result = audit_transparent(self.fixture(), self.repaired(), [self.operation()])
        self.assertEqual(result['added_buffers'], 1)
        self.assertTrue(result['clock_topology_unchanged'])
        self.assertEqual(result['declared_transparent_masters']['eco_data_0_0'], 'sg13cmos5l_dlygate4sd1_1')

    def test_wrong_cell_even_if_transparent_is_rejected(self):
        with self.assertRaises(ValueError):
            audit_transparent(self.fixture(), self.repaired('sg13cmos5l_buf_4'), [self.operation()])

    def test_unknown_delay_and_sequential_cell_rejected(self):
        for master in ('sg13cmos5l_dlygate4sd2_1', 'sg13cmos5l_dfrbpq_1', 'sg13cmos5l_inv_1'):
            with self.subTest(master=master), self.assertRaises(ValueError):
                audit_transparent(self.fixture(), self.repaired(master), [self.operation(buffer_cell=master)])

    def test_undeclared_data_clock_and_boundary_changes_rejected(self):
        for kind in ('data', 'clock', 'boundary', 'sink', 'extra_net'):
            after = self.repaired()
            if kind == 'data': after[0]['gate'][1]['B1'] = 'q'
            if kind == 'clock': after[0]['ff'][1]['CLK'] = 'clk'
            if kind == 'boundary': after[1]['clk'] = 'ctree'
            if kind == 'sink': after[3]['delayed'] = [('gate', 'A1')]
            if kind == 'extra_net': after[2].add('unapproved')
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                audit_transparent(self.fixture(), after, [self.operation()])

    def test_clock_target_and_duplicate_source_rejected(self):
        for ops in ([dict(kind='buffer', target='clock/X', old='sg13cmos5l_buf_8', max_loads=1)],
                    [self.operation(), self.operation()]):
            with self.assertRaises(ValueError):
                audit_transparent(self.fixture(), self.repaired(), ops)

    def test_repair_script_uses_exact_declared_masters(self):
        ops = [self.operation(), dict(kind='buffer', target='other/Y', old='sg13cmos5l_a21oi_1', max_loads=2)]
        script = render_script(ops)
        self.assertEqual(script.count('insert_buffer -buffer_cell sg13cmos5l_dlygate4sd1_1'), 1)
        self.assertEqual(script.count('insert_buffer -buffer_cell sg13cmos5l_buf_4'), 1)
        self.assertEqual(script.count('global_route -start_incremental'), 1)
        self.assertEqual(script.count('global_route -end_incremental'), 1)

    def test_inventory_excludes_launch_clock_arcs(self):
        report = '''0.010 0.020 0.030 ^ clock/X (sg13cmos5l_buf_8)
0.010 0.020 0.040 ^ ff/Q (sg13cmos5l_dfrbpq_1)
2 0.030 0.040 0.050 0.090 ^ data/Y (sg13cmos5l_a21oi_1)
0.090 data arrival time
0.010 0.200 0.300 ^ capture/X (sg13cmos5l_buf_8)
'''
        self.assertEqual(arcs(report), [dict(pin='data/Y', master='sg13cmos5l_a21oi_1',
                                            delay_ns=0.05, fanout=2, cap_pf=0.03)])


class ReserveComparisonTests(unittest.TestCase):
    def metrics(self):
        result = {}
        for corner in REQUIRED_CORNERS:
            for analysis in ('setup', 'hold'):
                result[f'timing__{analysis}__ws__corner:{corner}'] = 0.1
                result[f'timing__{analysis}__tns__corner:{corner}'] = 0
                result[f'timing__{analysis}_vio__count__corner:{corner}'] = 0
            for kind in ('slew', 'cap', 'fanout'):
                result[f'design__max_{kind}_violation__count__corner:{corner}'] = 0
            result[f'timing__unannotated_net_filtered__count__corner:{corner}'] = 0
        for kind in ('design__inferred_latch__count', 'design__instance_unmapped__count', 'synthesis__check_error__count'):
            result[kind] = 0
        return result

    def test_numeric_tie_preserves_raw_consumption_but_real_budget_loss_rejects(self):
        parent, candidate = self.metrics(), self.metrics()
        key = f'timing__hold__ws__corner:{REQUIRED_CORNERS[-1]}'
        candidate[key] -= 0.0000001
        result = comparison(parent, candidate)
        self.assertEqual(result['status'], 'pass')
        self.assertGreater(result['margins'][REQUIRED_CORNERS[-1]]['hold']['consumed_ns'], 0)
        candidate[key] -= 0.000002
        self.assertEqual(comparison(parent, candidate)['status'], 'rejected')

    def test_tolerance_never_waives_negative_slack_or_electrical_violation(self):
        for analysis in ('setup', 'hold'):
            parent, candidate = self.metrics(), self.metrics()
            key = f'timing__{analysis}__ws__corner:{REQUIRED_CORNERS[-1]}'
            parent[key], candidate[key] = 0.0000001, -0.0000001
            self.assertEqual(comparison(parent, candidate)['status'], 'rejected')
        parent, candidate = self.metrics(), self.metrics()
        candidate[f'design__max_fanout_violation__count__corner:{REQUIRED_CORNERS[0]}'] = 1
        self.assertEqual(comparison(parent, candidate)['status'], 'rejected')


class CompletePrecheckTests(unittest.TestCase):
    def test_nine_distinct_passes_are_bound_to_the_report(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / 'results.xml'
            report.write_text('<testsuite>' + ''.join(f'<testcase name="check{i}"/>' for i in range(9)) + '</testsuite>')
            result = checked_precheck(report)
            self.assertEqual(result['tests'], 9)
            self.assertEqual(len(result['names']), 9)
            self.assertEqual(len(result['sha256']), 64)
            self.assertEqual(json.loads(json.dumps(result)), result)

    def test_skips_errors_missing_and_duplicate_checks_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / 'results.xml'
            good = '<testsuite>' + ''.join(f'<testcase name="check{i}"/>' for i in range(9)) + '</testsuite>'
            invalid = [good.replace('<testcase name="check0"/>', '<testcase name="check0"><' + tag + '/></testcase>')
                       for tag in ('skipped', 'error', 'failure')]
            invalid += [good.replace('<testcase name="check0"/>', ''), good.replace('check0', 'check1')]
            for text in invalid:
                report.write_text(text)
                with self.assertRaises(ValueError):
                    checked_precheck(report)


if __name__ == '__main__':
    unittest.main()
