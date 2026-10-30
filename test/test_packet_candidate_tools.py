"""Declared partial-sink repairs must preserve every other signal/clock load."""
import importlib.util
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'tools/packet_sram'))
from install_candidate_tools import install
sys.path.pop(0)


class CandidateAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.root=Path(cls.temp.name)
        source=REPO/'tools/timing'
        shutil.copytree(source,cls.root/'tools/timing',ignore=shutil.ignore_patterns('__pycache__'))
        install(cls.root)
        for path in (cls.root/'tools/timing').glob('*.py'):
            compile(path.read_text(),str(path),'exec')
        sys.path.insert(0,str(cls.root/'tools/timing'))
        spec=importlib.util.spec_from_file_location('packet_candidate_audit',cls.root/'tools/timing/audit_data_eco.py')
        cls.audit=importlib.util.module_from_spec(spec); spec.loader.exec_module(cls.audit)

    @classmethod
    def tearDownClass(cls):
        sys.path.pop(0); cls.temp.cleanup()

    def fixture(self):
        cells={'clkroot':('sg13cmos5l_buf_8',{'A':'clk','X':'ctree'}),
            'gate':('sg13cmos5l_a21oi_1',{'A1':'a','A2':'b','B1':'c','Y':'data'}),
            'ff':('sg13cmos5l_dfrbpq_1',{'D':'data','CLK':'ctree','Q':'q'}),
            'other':('sg13cmos5l_buf_1',{'A':'data','X':'out'})}
        return cells,{'clk':'clk'},{'clk','ctree','a','b','c','data','q','out'},\
            {'clk':[('clkroot','A')],'ctree':[('ff','CLK')],'data':[('ff','D'),('other','A')]},{('ff','CLK')}

    def repaired(self):
        before=self.fixture(); after=self.fixture()
        after[0]['eco_data_0']=('sg13cmos5l_buf_4',{'A':'data','X':'new'})
        after[0]['ff'][1]['D']='new'; after[2].add('new')
        after[3]['data']=[('eco_data_0','A'),('other','A')]; after[3]['new']=[('ff','D')]
        op=dict(kind='buffer',target='gate/Y',old='sg13cmos5l_a21oi_1',max_loads=1,loads=['ff/D'])
        return before,after,op

    def test_declared_sink_only_preserves_unselected_load(self):
        before,after,op=self.repaired()
        self.assertEqual(self.audit.audit(before,after,[op])['added_buffers'],1)

    def test_undeclared_repartition_is_rejected(self):
        before,after,op=self.repaired()
        after[0]['other'][1]['A']='new'; after[3]['data']=[('eco_data_0','A')]; after[3]['new'].append(('other','A'))
        with self.assertRaises(ValueError): self.audit.audit(before,after,[op])

    def test_duplicate_and_foreign_sink_names_are_rejected(self):
        for names in (['ff/D','ff/D'],['foreign/A']):
            before,after,op=self.repaired(); op['loads']=names
            with self.subTest(names=names),self.assertRaises(ValueError): self.audit.audit(before,after,[op])

    def test_macro_clock_cannot_be_data_buffered(self):
        before,after,op=self.repaired()
        before[3]['data'].append(('memory','A_CLK')); before[4].add(('memory','A_CLK'))
        with self.assertRaises(ValueError): self.audit.audit(before,after,[op])


if __name__=='__main__': unittest.main()
