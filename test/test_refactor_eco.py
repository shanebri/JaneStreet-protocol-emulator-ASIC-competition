"""Adversarial tests for the candidate's physical replication safety audit."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools/timing'))
from refactor_eco import normalize_replicas, selected_loads


class ReplicaAuditTests(unittest.TestCase):
    def setUp(self):
        cells = {'gate':('sg13cmos5l_nand3_1', dict(A='a',B='b',C='c',Y='n'))}
        loads = {'a':[('gate','A')], 'b':[('gate','B')], 'c':[('gate','C')], 'n':[], 'clk':[], 'reset':[]}
        clocks = set()
        for index in range(4):
            name = 'ff'+str(index)
            cells[name] = ('sg13cmos5l_dfrbpq_1', dict(D='n',Q='q'+str(index),CLK='clk',RESET_B='reset'))
            loads['n'].append((name,'D'))
            loads['clk'].append((name,'CLK'))
            loads['reset'].append((name,'RESET_B'))
            clocks.add((name,'CLK'))
        ports = {name:name for name in ('a','b','c','clk','reset')}
        nets = {'a','b','c','n','clk','reset','q0','q1','q2','q3'}
        self.before = (cells,ports,nets,loads,clocks)
        self.positions = {'ff0':(400000,0),'ff1':(500000,0),'ff2':(600000,0),'ff3':(700000,0),'gate':(450000,0)}
        self.op = dict(kind='clone',target='gate/Y',old='sg13cmos5l_nand3_1',x_min_um=550,max_loads=8,name='eco_control_local')
        self.after = deepcopy(self.before)
        new, _, new_nets, new_loads, _ = self.after
        new['eco_control_local'] = ('sg13cmos5l_nand3_1',dict(A='a',B='b',C='c',Y='replica'))
        new_nets.add('replica')
        new_loads['replica'] = [('ff2','D'),('ff3','D')]
        new_loads['n'] = [('ff0','D'),('ff1','D')]
        for pin,net in (('A','a'),('B','b'),('C','c')):
            new_loads[net].append(('eco_control_local',pin))
        new['ff2'][1]['D'] = 'replica'
        new['ff3'][1]['D'] = 'replica'

    def check(self):
        return normalize_replicas(self.before,self.after,[self.op],self.positions,1000)

    def test_equivalent_replication_preserves_all_original_data_and_clock_connections(self):
        self.assertEqual(self.check()['status'], 'pass')

    def test_wrong_replica_input_is_rejected(self):
        self.after[0]['eco_control_local'][1]['A'] = 'b'
        with self.assertRaisesRegex(ValueError,'input signal'):
            self.check()

    def test_changed_gate_function_is_rejected(self):
        self.after[0]['eco_control_local'] = ('sg13cmos5l_nor3_1',self.after[0]['eco_control_local'][1])
        with self.assertRaisesRegex(ValueError,'gate function'):
            self.check()

    def test_foreign_sink_is_rejected(self):
        self.after[3]['replica'].append(('ff0','D'))
        with self.assertRaisesRegex(ValueError,'sink partition'):
            self.check()

    def test_undeclared_original_connection_change_is_rejected(self):
        self.after[0]['ff0'][1]['D'] = 'a'
        with self.assertRaisesRegex(ValueError,'original signal connectivity'):
            self.check()

    def test_empty_partition_is_rejected(self):
        self.op['x_min_um'] = 900
        with self.assertRaisesRegex(ValueError,'proper subset'):
            self.check()

    def test_overloaded_partition_is_rejected(self):
        self.op['max_loads'] = 1
        with self.assertRaisesRegex(ValueError,'bounded proper subset'):
            self.check()

    def test_clock_sink_is_rejected(self):
        self.before[4].add(('ff2','D'))
        with self.assertRaisesRegex(ValueError,'clock sink'):
            selected_loads(self.before,self.op,self.positions,1000)


if __name__ == '__main__':
    unittest.main()
