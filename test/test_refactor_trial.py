"""Negative tests for physical-parent immutability and one-shot trial workers."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools/timing'))
import refactor_trial as trial


class TrialGuardTests(unittest.TestCase):
    def setUp(self):
        directory = ROOT/'test/sim_build'
        directory.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='refactor_guard_tests_', dir=directory)
        self.root = Path(self.temp.name).resolve()
        assert self.root.is_relative_to(directory.resolve())
        self.addCleanup(self.temp.cleanup)
        self.parent = self.root/'parent'
        self.parent.mkdir()
        self.candidate = self.root/'candidate'

    def complete_metadata(self):
        (self.parent/'job.json').write_text(json.dumps(dict(status='complete',physical_signoff=True,frozen_input_changes=[])))
        (self.parent/'qualification').mkdir()
        (self.parent/'qualification/manifest.json').write_text(json.dumps(dict(status='complete',sha256={})))
        (self.parent/'frozen_inputs.json').write_text('{}')

    def test_running_parent_is_refused_before_candidate_creation(self):
        (self.parent/'job.json').write_text('{"status":"running"}')
        with self.assertRaisesRegex(ValueError,'lacks complete'):
            trial.freeze(self.candidate,'buffer_hold',self.parent)
        self.assertFalse(self.candidate.exists())

    def test_changed_frozen_parent_source_is_refused(self):
        self.complete_metadata()
        (self.parent/'source.sv').write_text('changed')
        (self.parent/'frozen_inputs.json').write_text(json.dumps({'source.sv':hashlib.sha256(b'original').hexdigest()}))
        with self.assertRaisesRegex(ValueError,'frozen sources changed'):
            trial.freeze(self.candidate,'buffer_hold',self.parent)
        self.assertFalse(self.candidate.exists())

    def test_changed_qualified_physical_artifact_is_refused(self):
        self.complete_metadata()
        artifact=self.parent/'artifact.gds'
        artifact.write_bytes(b'changed synthetic test fixture')
        (self.parent/'qualification/manifest.json').write_text(json.dumps(dict(status='complete',sha256={str(artifact):hashlib.sha256(b'original').hexdigest()})))
        with self.assertRaisesRegex(ValueError,'qualified physical artifact changed'):
            trial.freeze(self.candidate,'buffer_hold',self.parent)
        self.assertFalse(self.candidate.exists())

    def test_changed_initial_reference_is_refused(self):
        reference=self.root/'reference.json'
        reference.write_text('{}')
        with patch.object(trial,'PARENT',reference):
            with self.assertRaisesRegex(ValueError,'baseline reference was changed'):
                trial.freeze(self.candidate,'hold')
        self.assertFalse(self.candidate.exists())

    def test_worker_cannot_overwrite_a_previous_attempt(self):
        job=self.parent/'job.json'
        job.write_text('{"status":"failed","preserve":"original evidence"}')
        original=job.read_bytes()
        with self.assertRaisesRegex(ValueError,'cannot reuse'):
            trial.worker(self.parent)
        self.assertEqual(job.read_bytes(),original)

    def failed_attempt(self):
        (self.parent/'job.json').write_text(json.dumps(dict(status='rejected_or_failed',physical_signoff=False,frozen_input_changes=[])))
        (self.parent/'frozen_inputs.json').write_text('{}')
        return dict(status='complete',physical_signoff=True,frozen_input_changes=[],
                    original_job_sha256=trial.sha(self.parent/'job.json'),
                    frozen_inputs_manifest_sha256=trial.sha(self.parent/'frozen_inputs.json'))

    def test_incomplete_qualification_retry_is_refused(self):
        receipt=self.failed_attempt(); receipt['status']='failed'
        (self.parent/'qualification_resume.json').write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError,'lacks complete'):
            trial.validated_parent(self.parent)

    def test_retry_cannot_rebind_a_changed_original_attempt(self):
        receipt=self.failed_attempt(); receipt['original_job_sha256']='0'*64
        (self.parent/'qualification_resume.json').write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError,'original attempt changed'):
            trial.validated_parent(self.parent)

    def test_retry_cannot_rebind_a_changed_source_manifest(self):
        receipt=self.failed_attempt(); receipt['frozen_inputs_manifest_sha256']='0'*64
        (self.parent/'qualification_resume.json').write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError,'original source manifest changed'):
            trial.validated_parent(self.parent)


if __name__ == '__main__':
    unittest.main()
