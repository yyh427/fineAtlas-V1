"""Bind independent supplement source bytes separately from frozen build code."""

if not __debug__:
    raise RuntimeError('Optimized Python is forbidden for mandatory independent audit gates')

import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require_supplement(plan, phase, here):
    package_root = Path(here).resolve().parent
    binding = plan['external_audit_supplement']
    manifest_path = Path(binding['manifest']).resolve()
    assert manifest_path == package_root / 'SUPPLEMENT_CODE_MANIFEST.json'
    assert digest(manifest_path) == binding['manifest_sha256']
    manifest = json.loads(manifest_path.read_text())
    assert manifest['schema'] == 'FINEATLAS_INDEPENDENT_EXTERNAL_AUDIT_SUPPLEMENT_CODE_V1'
    assert manifest['supplement_version'] == 'source166-class-case-v2'
    expected_seal = plan.get('source9_final_source_seal_sha256', plan['final_source_seal_sha256'])
    assert manifest['frozen_source9_input_seal_sha256'] == expected_seal
    assert manifest['original_frozen_observer_failed'] is True
    assert manifest['files']
    for relative, expected in manifest['files'].items():
        name = Path(relative)
        assert not name.is_absolute() and '..' not in name.parts and '\\' not in relative
        member = package_root / name
        assert not member.is_symlink() and member.resolve().is_relative_to(package_root)
        assert digest(member) == expected
    actual = {str(path.relative_to(package_root)) for path in package_root.rglob('*') if path.is_file()}
    assert actual == set(manifest['files']) | {'SUPPLEMENT_CODE_MANIFEST.json'}
    if phase == 'fresh-public':
        conf = plan['execution'][phase]
        command = conf['command']
        database = Path(command[command.index('--database') + 1]).resolve()
        public_root = database.parent.parent
        assert package_root.is_relative_to(public_root / 'external-audit-supplement')
        proof_path = Path(conf['external_audit_supplement_download_receipt']).resolve()
        assert proof_path.is_relative_to(public_root)
        assert digest(proof_path) == conf['external_audit_supplement_download_receipt_sha256']
        proof = json.loads(proof_path.read_text())
        assert proof['schema'] == 'FINEATLAS_EXTERNAL_AUDIT_SUPPLEMENT_DOWNLOAD_PROOF_V1'
        assert proof['fresh_download'] is True and proof['network_request'] is True and proof['authenticated'] is False
        assert proof['source_url'] == binding['archive_url'] and urlparse(proof['source_url']).scheme == 'https'
        assert urlparse(proof['response_url']).scheme == 'https'
        archive = Path(proof['archive']).resolve()
        assert archive.is_relative_to(public_root) and not archive.is_symlink()
        assert proof['archive_sha256'] == binding['archive_sha256'] == digest(archive)
        assert proof['archive_bytes'] == binding['archive_bytes'] == archive.stat().st_size
        assert proof['archive_stamp'] == [archive.stat().st_size, archive.stat().st_mtime_ns, archive.stat().st_ino]
        assert Path(proof['extracted_root']).resolve() == package_root
        assert proof['manifest_sha256'] == binding['manifest_sha256']
        assert proof['member_sha256'] == {**manifest['files'], 'SUPPLEMENT_CODE_MANIFEST.json': binding['manifest_sha256']}
    return {'pass': True, 'supplement_version': manifest['supplement_version'], 'manifest_sha256': binding['manifest_sha256'], 'source9_input_seal_sha256': expected_seal, 'phase': phase, 'original_frozen_sources_preserved': True}
