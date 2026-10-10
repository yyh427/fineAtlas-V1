#!/usr/bin/env python3
"""Add complete-source type gates while preserving the prior delivery checks."""
from __future__ import annotations

if not __debug__:
    raise RuntimeError('Mandatory complete-source checks cannot run optimized')

import argparse
import os
from pathlib import Path

from _download import digest, download
from build_structure_candidate import build_fingerprints
from nominal_scope_checkpoint_proof import (NAME, package_checkpoint_proof, validate_checkpoint_proof)
from nominal_scope_prior_delivery import NominalScopePriorCoordinator
from coordinate_structure_delivery import Coordinator, ROOT, lease, metadata, read, write, require_fresh
from resume_structure_repairs import validate_resumed_parent_independence
from structure_complete_owned_type_delivery_guard import (SPEC, require_complete_type_child_build,
                                                         require_complete_type_receipt)
from structure_literal_jet_delivery_guard import require_literal_jet_child_build
from structure_nominal_design_scope_delivery_guard import SPEC as NOMINAL_SPEC, require_nominal_scope_child_build, require_nominal_scope_receipt
from portable_nominal_structure_lineage import require_source_parent_binding
from structure_nominal_regression_support import require_public_support


class NominalDesignScopeCoordinator(NominalScopePriorCoordinator):
    def __init__(self, config):
        # The previous coordinator's lineage check identifies the artifact
        # itself. Here two explicit lineage levels are checked independently:
        # complete eight-stage ancestors and actual six-stage final builds.
        self.config_path = Path(config).resolve()
        self.c = read(config)
        self.root = Path(self.c['delivery_root']).resolve()
        self.inputs = Path(self.c['inputs']).resolve()
        self.meta = metadata(self.c['database'])
        self.fingerprints = build_fingerprints(self.inputs)
        freeze = self.meta['structure_frozen_build_manifest']
        if {key: freeze[key] for key in self.fingerprints} != self.fingerprints:
            raise ValueError('Coordinator code or inputs differ from the complete final freeze')
        self.lineage_primary = Path(self.c['lineage_primary_build'])
        self.lineage_reproduction = Path(self.c['lineage_reproduction_build'])
        self.parents = validate_resumed_parent_independence(self.lineage_primary, self.lineage_reproduction)
        self.final_parents = validate_resumed_parent_independence(
            Path(self.c['primary_build']), Path(self.c['reproduction_build']))
        self.env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONPATH': str(ROOT / 'src')}
        self.env.pop('PYTHONOPTIMIZE', None)
        self.validate_child_builds()

    def cmd(self, script, *values, python=None):
        # Explicit executors preserve every frozen earlier implementation.
        if script == 'accept_resumed_structure_candidate.py':
            values = (*values, '--primary-snapshots-dir', self.primary_snapshots_directory(),
                      '--owned-scope-audit', self.root / 'primary-owned-scope.json',
                      '--complete-owned-audit', self.root / 'primary-complete-owned-type.json')
            return Coordinator.cmd(self, 'accept_nominal_design_scope_candidate.py', *values, python=python)
        if script == 'audit_cars_projection_view_repairs.py':
            database = Path(values[values.index('--database')+1]).resolve()
            if python:
                owned = self.root / 'public/checks/owned-scope-source-first.json'
                complete = self.root / 'public/checks/complete-owned-type-source-first.json'
            else:
                name = 'primary' if database == Path(self.c['database']).resolve() else 'reproduction'
                if database != Path(self.c['database' if name=='primary' else 'reproduction']).resolve():
                    raise ValueError('A temporal source command must identify one actual child database')
                owned = self.root / (name+'-owned-scope.json')
                complete = self.root / (name+'-complete-owned-type.json')
            values = (*values, '--owned-audit', owned, '--complete-owned-audit', complete)
            return Coordinator.cmd(self, 'audit_temporal_cars_projection_view_repairs.py', *values, python=python)
        if script == 'audit_complete_subject_scope_repairs.py':
            snapshots = self.root / 'public/source-snapshots' if python else self.primary_snapshots_directory()
            values = (*values, '--primary-snapshots-dir', snapshots)
            return Coordinator.cmd(self, 'audit_temporal_eighth_complete_subject_scope_repairs.py', *values, python=python)
        return super().cmd(script, *values, python=python)

    def validate_child_builds(self):
        lineage = self.meta.get('structure_nominal_design_resume_parent', {})
        if (lineage.get('repair_recipe') != 'resume_nominal_design_scope_repairs.py'
                or lineage.get('previous_source_stages_replayed') is not False
                or lineage.get('previous_repair_stages_replayed') is not False
                or lineage.get('all_derived_indexes_recomputed') is not True):
            raise ValueError('Actual nominal-scope six-stage child lineage required')
        for name, key, historical in (('primary', 'primary_build', self.lineage_primary),
                                       ('reproduction', 'reproduction_build', self.lineage_reproduction)):
            path = Path(self.c[key])
            child = require_nominal_scope_child_build(path)
            parent, seal = require_source_parent_binding(self.c, name, path, child)
            ancestor = require_literal_jet_child_build(historical)
            if (child['revision'] != self.meta['database_revision']
                    or parent['revision'] != lineage['parent_revision']
                    or ancestor['revision'] != self.meta['structure_complete_type_resume_parent']['parent_revision']):
                raise ValueError('Final child, direct Source8 parent and c933 ancestor disagree')

    def require_local_nominal_scope(self):
        self.validate_child_builds()
        for name, key in (('primary', 'database'), ('reproduction', 'reproduction')):
            require_nominal_scope_receipt(self.root / (name + '-nominal-design-scope.json'),
                                         self.c[key], self.inputs, self.meta['database_revision'], ROOT)

    def require_local_complete_type(self):
        self.validate_child_builds()
        for name, key in (('primary', 'database'), ('reproduction', 'reproduction')):
            require_complete_type_receipt(self.root / (name + '-complete-owned-type.json'),
                                         self.c[key], self.inputs, self.meta['database_revision'], ROOT)

    def accepted(self):
        accepted = super().accepted()
        self.require_local_complete_type()
        self.require_local_nominal_scope()
        return accepted

    def local(self):
        self.validate_child_builds()
        for name, key in (('primary', 'database'), ('reproduction', 'reproduction')):
            report = self.root / (name + '-nominal-design-scope.json')
            if not report.exists():
                self.execute(name + '-nominal-design-scope', self.cmd(NOMINAL_SPEC.auditor,
                    '--database', self.c[key], '--inputs', self.inputs, '--output', report))
            require_nominal_scope_receipt(report, self.c[key], self.inputs, self.meta['database_revision'], ROOT)
        for name, key in (('primary', 'database'), ('reproduction', 'reproduction')):
            report = self.root / (name + '-complete-owned-type.json')
            if not report.exists():
                self.execute(name + '-complete-owned-type', self.cmd(SPEC.auditor,
                    '--database', self.c[key], '--inputs', self.inputs, '--output', report))
            require_complete_type_receipt(report, self.c[key], self.inputs, self.meta['database_revision'], ROOT)
        super().local()
        write(self.root / 'complete_type_local_extension.json', {
            'schema': 'FINEATLAS_COMPLETE_TYPE_LOCAL_EXTENSION_V1', 'pass': True,
            'database_revision': self.meta['database_revision'], 'fingerprints': self.fingerprints,
            'actual_final_build_independence': self.final_parents,
            'evidence': {name: {'path': str(self.root / (name + '-complete-owned-type.json')),
                               'sha256': digest(self.root / (name + '-complete-owned-type.json'))}
                         for name in ('primary', 'reproduction')}})

    def package(self):
        self.require_local_nominal_scope()
        self.require_local_complete_type()
        super().package()
        package_path = self.root / 'package/delivery_assets.json'
        package = read(package_path)
        proof = package_checkpoint_proof(self.c, self.root / 'package', self.accepted())
        validate_checkpoint_proof(proof, self.accepted())
        descriptor = {'path': str(proof), 'name': proof.name, 'bytes': proof.stat().st_size,
                      'sha256': digest(proof)}
        package['assets'].append(descriptor)
        package['nominal_scope_checkpoint_proof'] = descriptor
        write(package_path, package)

    def public(self):
        self.require_local_nominal_scope()
        self.require_local_complete_type()
        super().public()
        package = read(self.root / 'package/delivery_assets.json')
        expected = package['nominal_scope_checkpoint_proof']
        target = self.root / 'public' / NAME
        retrieval = self.root / 'public/checks/nominal-scope-checkpoint-download.json'
        if not retrieval.exists():
            actual = download(self.c['public_base_url'].rstrip('/') + '/' + expected['name'], target, expected)
            require_fresh(actual)
            write(retrieval, actual)
        require_fresh(read(retrieval))
        if target.stat().st_size != expected['bytes'] or digest(target) != expected['sha256']:
            raise ValueError('Freshly downloaded final checkpoint proof differs from the packaged evidence')
        historical = validate_checkpoint_proof(target, self.accepted())
        database = self.root / 'public/data/fineatlas.sqlite'
        inputs = self.root / 'public/frozen/inputs'
        report = self.root / 'public/checks/complete-owned-type.json'
        if not report.exists():
            self.execute('public-complete-owned-type', self.cmd(SPEC.auditor,
                '--database', database, '--inputs', inputs, '--output', report,
                python=self.root / 'public/venv/bin/python'))
        require_complete_type_receipt(report, database, inputs, self.meta['database_revision'], ROOT)
        write(self.root / 'public/checks/complete_type_public_extension.json', {
            'schema': 'FINEATLAS_COMPLETE_TYPE_PUBLIC_EXTENSION_V1', 'pass': True,
            'database': str(database.resolve()), 'database_revision': self.meta['database_revision'],
            'database_sha256': self.accepted()['database_sha256'], 'historical_final_builds': historical,
            'evidence': {name: {'path': str(path), 'sha256': digest(path)} for name, path in (
                ('complete-source-audit', report), ('checkpoint-download', retrieval),
                ('actual-final-checkpoint', target),
                ('prior-public-owned', self.root / 'public/checks/owned_scope_public_extension.json'))}})

        nominal = self.root / 'public/checks/nominal-design-scope.json'
        if not nominal.exists():
            self.execute('public-nominal-design-scope', self.cmd(NOMINAL_SPEC.auditor,
                '--database', database, '--inputs', inputs, '--output', nominal,
                python=self.root / 'public/venv/bin/python'))
        require_nominal_scope_receipt(nominal, database, inputs, self.meta['database_revision'], ROOT)
        write(self.root / 'public/checks/nominal_scope_public_extension.json', {
            'schema': 'FINEATLAS_NOMINAL_SCOPE_PUBLIC_EXTENSION_V1', 'pass': True,
            'database': str(database.resolve()), 'database_revision': self.meta['database_revision'],
            'database_sha256': self.accepted()['database_sha256'],
            'evidence': {name: {'path': str(path), 'sha256': digest(path)} for name, path in (
                ('nominal-scope-audit', nominal), ('checkpoint-download', retrieval),
                ('actual-final-checkpoint', target),
                ('prior-public-complete-type', self.root / 'public/checks/complete_type_public_extension.json'))}})

    def validate_public_complete_type(self):
        self.validate_public_owned()
        value = read(self.root / 'public/checks/complete_type_public_extension.json')
        accepted = self.accepted()
        if (value.get('schema') != 'FINEATLAS_COMPLETE_TYPE_PUBLIC_EXTENSION_V1'
                or value.get('pass') is not True or value.get('database_revision') != self.meta['database_revision']
                or value.get('database_sha256') != accepted['database_sha256']):
            raise ValueError('Actual complete-source public extension required')
        for row in value['evidence'].values():
            if digest(Path(row['path'])) != row['sha256']:
                raise ValueError('Actual complete-source public evidence changed')
        validate_checkpoint_proof(value['evidence']['actual-final-checkpoint']['path'], accepted)
        require_fresh(read(value['evidence']['checkpoint-download']['path']))
        require_complete_type_receipt(value['evidence']['complete-source-audit']['path'],
            self.root / 'public/data/fineatlas.sqlite', self.root / 'public/frozen/inputs',
            self.meta['database_revision'], ROOT)
        return value

    def validate_public_nominal_scope(self):
        self.validate_public_complete_type()
        value = read(self.root / 'public/checks/nominal_scope_public_extension.json')
        accepted = self.accepted()
        database = self.root / 'public/data/fineatlas.sqlite'
        if (value.get('schema') != 'FINEATLAS_NOMINAL_SCOPE_PUBLIC_EXTENSION_V1'
                or value.get('pass') is not True
                or Path(value.get('database', '')).resolve() != database.resolve()
                or value.get('database_revision') != accepted['database_revision']
                or value.get('database_sha256') != accepted['database_sha256']):
            raise ValueError('Actual nominal source scope public extension required')
        for item in value['evidence'].values():
            if digest(Path(item['path'])) != item['sha256']:
                raise ValueError('Actual nominal public evidence changed')
        require_nominal_scope_receipt(value['evidence']['nominal-scope-audit']['path'],
            database, self.root / 'public/frozen/inputs', accepted['database_revision'], ROOT)
        require_fresh(read(value['evidence']['checkpoint-download']['path']))
        validate_checkpoint_proof(value['evidence']['actual-final-checkpoint']['path'], accepted)
        return value

    def finalize(self):
        self.validate_public_nominal_scope()
        support, _ = require_public_support(read(self.root / 'package/delivery_assets.json'),
                                            self.root / 'public', self.accepted())
        original = self.c
        self.c = {**original, 'reference': str(support.root / 'source-row-digests.json')}
        try:
            Coordinator.finalize(self)
        finally:
            self.c = original
        write(self.root / 'nominal_scope_finalized_extension.json', {
            'schema': 'FINEATLAS_NOMINAL_SCOPE_FINALIZED_EXTENSION_V1', 'pass': True,
            'database_revision': self.meta['database_revision'],
            'public_extension_sha256': digest(self.root / 'public/checks/nominal_scope_public_extension.json')})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('local', 'package', 'public', 'finalize'))
    parser.add_argument('--config', type=Path, required=True)
    args = parser.parse_args()
    coordinator = NominalDesignScopeCoordinator(args.config)
    with lease(coordinator.root / (args.action + '.lease.json')):
        getattr(coordinator, args.action)()
