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
        self.assertNotIn(builder.ROOT/'fpga/usb_ls_setup_ack.sv',paths)
        self.assertEqual(len(paths),len(set(paths)))

    def test_explicit_tool_must_exist(self):
        with self.assertRaises(FileNotFoundError): builder.find_vivado('/missing/vivado')

    def test_feeder_image_has_capability_and_pinned_fixture(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)/'feeder'
            def launch(command,**kwargs):
                self.assertEqual(command[-1],'1')
                (out/'arty_bringup_top.bit').write_bytes(b'feeder bitstream')
            with patch.object(builder,'find_vivado',return_value=Path('/mock/vivado')),patch.object(builder.subprocess,'check_output',return_value='test-commit'),patch.object(builder.subprocess,'run',side_effect=launch):
                self.assertEqual(builder.main(['--packet-feeder','--out',str(out)]),0)
            fixture=builder.json.loads((out/'fixture.json').read_text())
            record=builder.json.loads((out/'build.json').read_text())
            self.assertTrue(fixture['packet_feeder'])
            self.assertEqual(fixture['expected_image_sha256'],record['image_sha256'])
            self.assertEqual(fixture['capture']['mode'],'none')

    def test_usb_bench_build_is_explicitly_opt_in(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)/'usb'

            def launch(command, **kwargs):
                self.assertEqual(command[-2:], ['1', '1'])
                (out/'arty_bringup_top.bit').write_bytes(b'usb bench bitstream')

            with (
                patch.object(builder, 'find_vivado', return_value=Path('/mock/vivado')),
                patch.object(builder.subprocess, 'check_output', return_value='test-commit'),
                patch.object(builder.subprocess, 'run', side_effect=launch),
            ):
                self.assertEqual(builder.main(['--usb-setup-ack', '--out', str(out)]), 0)
            record = builder.json.loads((out/'build.json').read_text())
            self.assertTrue(record['packet_feeder'])
            self.assertTrue(record['usb_setup_ack'])
            self.assertEqual(record['build_profile'], 'usb-ls-setup-ack-opt-in')
            self.assertEqual(record['board_qualification'], 'PENDING')
            paths = {Path(path).name for path in record['sources_sha256']}
            self.assertIn('usb_ls_setup_ack.sv', paths)
            self.assertIn('arty_usb_ls_setup_ack.xdc', paths)

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
