"""Negative controls for publication inputs, fresh transfers and resumed lineage."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import coordinate_structure_delivery as delivery
import promote_structure_with_regression_gate as promotion


class DeliveryGuards(unittest.TestCase):
    def test_stable_package_preserves_original_sdk_validation(self):
        coordinator = delivery.Coordinator.__new__(delivery.Coordinator)
        coordinator.c = {'database': '/data/stable.sqlite'}
        for release in ('v1.11.0', 'v2.0.0'):
            coordinator.meta = {'release': release}
            command = coordinator.data_package_command(Path('/data/package'))
            self.assertIn('--stable', command)
            self.assertEqual(command[command.index('--release') + 1], release)
            self.assertTrue(command[2].endswith('/package_browse_candidate.py'))

    def test_candidate_package_does_not_claim_stability(self):
        coordinator = delivery.Coordinator.__new__(delivery.Coordinator)
        coordinator.c = {'database': '/data/candidate.sqlite'}
        for release in ('v1.11.0rc1', 'v1.11.0.dev1', 'v1.11.0-night-review'):
            coordinator.meta = {'release': release}
            self.assertNotIn('--stable', coordinator.data_package_command(Path('/data/package')))

    def test_fresh_network_positive(self):
        delivery.require_fresh({'fresh_download': True, 'network_request': True,
                                'authenticated': False, 'initial_cached_bytes': 0})

    def test_cached_sdk_or_input_cannot_count_as_public_download(self):
        with self.assertRaisesRegex(ValueError, 'Fresh unauthenticated'):
            delivery.require_fresh({'fresh_download': False, 'network_request': False,
                                    'authenticated': False, 'initial_cached_bytes': 100})

    def test_authenticated_transfer_rejected(self):
        with self.assertRaises(ValueError):
            delivery.require_fresh({'fresh_download': True, 'network_request': True,
                                    'authenticated': True, 'initial_cached_bytes': 0})

    def test_duplicate_action_lease_rejected_without_removing_existing_owner(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'action.lease'
            with delivery.lease(path):
                with self.assertRaises(FileExistsError):
                    with delivery.lease(path):
                        self.fail('Duplicate action started')
                self.assertTrue(path.exists())

    def archive(self, names):
        raw = io.BytesIO()
        with tarfile.open(fileobj=raw, mode='w') as tar:
            for name, contents in names:
                info = tarfile.TarInfo(name)
                info.size = len(contents)
                tar.addfile(info, io.BytesIO(contents))
        return raw.getvalue()

    def extraction(self, members, expected):
        with tempfile.TemporaryDirectory() as root:
            process = subprocess.Popen([sys.executable, '-c', 'import sys;sys.stdout.buffer.write(sys.stdin.buffer.read())'],
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE)
            process.stdin.write(self.archive(members))
            process.stdin.close()
            try:
                with patch.object(delivery.subprocess, 'Popen', return_value=process):
                    delivery.safe_extract(Path('public.tar.zst'), Path(root) / 'output', expected)
            finally:
                process.wait()
                process.stdout.close()

    def test_complete_frozen_input_roundtrip(self):
        contents = b'{"frozen":true}'
        self.extraction([('inputs/policy.json', contents)],
                        {'inputs/policy.json': hashlib.sha256(contents).hexdigest()})

    def test_archive_path_traversal_rejected(self):
        with self.assertRaisesRegex(ValueError, 'unsafe'):
            self.extraction([('../outside', b'bad')], {'../outside': hashlib.sha256(b'bad').hexdigest()})

    def test_undeclared_frozen_input_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Unexpected'):
            self.extraction([('inputs/extra.json', b'bad')], {})

    def test_missing_frozen_input_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Incomplete'):
            self.extraction([], {'inputs/missing.json': '0' * 64})

    def test_promotion_requires_parent_independence_before_delegation(self):
        argv = []
        for name in ('legacy-reference', 'legacy-baseline-matrix', 'legacy-candidate-matrix',
                     'legacy-dispositions', 'primary-build', 'reproduction-build', 'source', 'source-inputs', 'reports'):
            argv.extend(['--' + name, 'fixture'])
        with patch('resume_structure_repairs.validate_resumed_parent_independence', side_effect=ValueError('copied parent')):
            with patch.object(promotion.subprocess, 'run') as delegate:
                with self.assertRaisesRegex(ValueError, 'copied parent'):
                    promotion.main(argv)
                delegate.assert_not_called()


if __name__ == '__main__':
    unittest.main()
