import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('bringup_builder',Path(__file__).with_name('build.py'))
builder=importlib.util.module_from_spec(spec); spec.loader.exec_module(builder)


class BuildTests(unittest.TestCase):
    def test_manifest_includes_banked_core_and_bridge(self):
        paths=builder.sources()
        self.assertIn(builder.ROOT/'src/pio_subsystem.sv',paths)
        self.assertIn(builder.ROOT/'fpga/bringup_bridge.sv',paths)
        self.assertEqual(len(paths),len(set(paths)))

    def test_explicit_tool_must_exist(self):
        with self.assertRaises(FileNotFoundError): builder.find_vivado('/missing/vivado')

    def test_success_and_failure_bundles(self):
        for success in (True,False):
            with tempfile.TemporaryDirectory() as temp:
                out=Path(temp)/'new build'
                def launch(*args,**kwargs):
                    if not success: raise builder.subprocess.CalledProcessError(1,args[0])
                    (out/'arty_bringup_top.bit').write_bytes(b'test bitstream')
                with patch.object(builder,'find_vivado',return_value=Path('/mock/vivado')),patch.object(builder.subprocess,'check_output',return_value='test-commit'),patch.object(builder.subprocess,'run',side_effect=launch):
                    code=builder.main(['--out',str(out)])
                self.assertEqual(code,0 if success else 1)
                record=builder.json.loads((out/'build.json').read_text())
                self.assertEqual((out/'.gitignore').read_text(),'*\n')
                self.assertEqual(record['status'],'PASS' if success else 'FAIL')
                self.assertEqual((out/'fixture.json').exists(),success)


if __name__=='__main__': unittest.main()
