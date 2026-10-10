#!/usr/bin/env python3
"""Extend the unchanged delivery coordinator with mandatory fifth, sixth and seventh delta gates.

Uses normal subclass extension and explicit delegation. Old local/public checks,
receipts and exact public evidence keys remain intact. No registry changes and
no synthetic or patched acceptance results.
"""
from __future__ import annotations
import argparse
from pathlib import Path

from _download import digest
from coordinate_structure_delivery import Coordinator, ROOT, lease, metadata, read, write
from structure_acceptance_contract import validate_public_evidence
from structure_literal_jet_delivery_guard import SPEC, require_literal_jet_receipt, require_literal_jet_child_build
from structure_primary_aircraft_delivery_guard import SPEC as FAMILY_SPEC, require_primary_aircraft_receipt
from structure_owned_scope_delivery_guard import SPEC as OWNED_SPEC, require_owned_scope_receipt
from primary_source_snapshot_delivery import require_fresh_retrieval
from structure_regression_temporal_contract import require_temporal_receipt
from structure_subject_scope_temporal_contract import require_temporal_subject_receipt
from structure_regression_support import package_support, download_public_support, require_public_support
from owned_source_snapshot_delivery import NAME as OWNED_SOURCE_REGISTRY, require_owned_retrieval


class LiteralJetCoordinator(Coordinator):
    def cmd(self, script, *values, python=None):
        # Explicit additive executors keep the old frozen programs unchanged.
        replacements = {'audit_structure_regression_repairs.py':'audit_temporal_structure_regression_repairs.py',
                        'accept_resumed_structure_candidate.py':'accept_owned_structure_candidate.py',
                        'audit_complete_subject_scope_repairs.py':'audit_temporal_complete_subject_scope_repairs.py',
                        'run_structure_public_checks.py':'run_literal_jet_public_checks.py'}
        if script=='run_structure_public_checks.py':
            package=read(self.root/'package/delivery_assets.json')
            support,_=download_public_support(package,self.root/'public',self.c['public_base_url'],self.accepted())
            replacements_values={'--legacy-reference':support.root/'reference.csv',
                '--legacy-baseline-matrix':support.root/'baseline','--legacy-dispositions':support.root/'dispositions.json',
                '--reference':support.root/'source-row-digests.json','--inventory':support.root/'domain-inventory.json'}
            values=list(values)
            for key,path in replacements_values.items():values[values.index(key)+1]=path
            values.extend(['--regression-support-registry',support.path,
                           '--primary-snapshots-dir',self.prepare_public_primary_snapshots(self.root/'public/frozen/inputs')])
        elif script in {'audit_structure_regression_repairs.py','audit_complete_subject_scope_repairs.py',
                        'audit_owned_scope_repairs.py','accept_resumed_structure_candidate.py'}:
            if '--primary-snapshots-dir' not in values:
                snapshots=self.root/'public/source-snapshots' if python else self.primary_snapshots_directory()
                values=(*values,'--primary-snapshots-dir',snapshots)
        return super().cmd(replacements.get(script,script),*values,python=python)

    def prepare_public_primary_snapshots(self,inputs):
        snapshots=self.root/'public/source-snapshots'
        report=self.root/'public/checks/primary-source-retrieval.json'
        if not report.exists():
            self.execute('public-primary-source-retrieval',self.cmd('primary_source_snapshot_delivery.py',
                '--inputs',inputs,'--snapshots-dir',snapshots,'--output',report,
                python=self.root/'public/venv/bin/python'))
        require_fresh_retrieval(report,inputs,snapshots)
        if (Path(inputs)/OWNED_SOURCE_REGISTRY).exists():
            owned_report=self.root/'public/checks/owned-source-retrieval.json'
            if not owned_report.exists():
                self.execute('public-owned-source-retrieval',self.cmd('owned_source_snapshot_delivery.py',
                    '--inputs',inputs,'--snapshots-dir',snapshots,'--output',owned_report,'--primary-receipt',report,
                    python=self.root/'public/venv/bin/python'))
            require_owned_retrieval(owned_report,inputs,snapshots,report)
        return snapshots

    def __init__(self, config):
        super().__init__(config)
        self.validate_child_builds()

    def validate_child_builds(self):
        for receipt in (self.lineage_primary, self.lineage_reproduction):
            require_literal_jet_child_build(receipt)
        lineage = self.meta.get('structure_delta_resume_parent', {})
        if (not lineage.get('parent_revision') or lineage.get('repair_recipe') != 'resume_literal_jet_repairs.py'
                or lineage.get('previous_source_stages_replayed') is not False
                or lineage.get('previous_repair_stages_replayed') is not False
                or lineage.get('all_derived_indexes_recomputed') is not True):
            raise ValueError('Actual aircraft child metadata and separate parent lineage required')

    def validate_local_fifth(self):
        self.validate_child_builds()
        for name, key in (('primary','database'),('reproduction','reproduction')):
            require_literal_jet_receipt(self.root / (name + '-literal-jet-scope.json'),
                Path(self.c[key]), self.inputs, self.meta['database_revision'], ROOT)
            require_primary_aircraft_receipt(self.root / (name + '-primary-aircraft-family.json'),
                Path(self.c[key]), self.inputs, self.meta['database_revision'], ROOT)
            require_owned_scope_receipt(self.root / (name + '-owned-scope.json'),
                Path(self.c[key]), self.inputs, self.meta['database_revision'], ROOT)
        directory = self.primary_snapshots_directory()
        for name in ('primary','reproduction'):
            for suffix in ('primary-aircraft-family','owned-scope'):
                actual = read(self.root / (name + '-' + suffix + '.json'))
                if Path(actual.get('primary_snapshots_dir') or '/MISSING').resolve() != directory:
                    raise ValueError('Local primary source receipt must use configured explicit snapshots')

    def primary_snapshots_directory(self):
        value = self.c.get('primary_snapshots_directory')
        if not value or not Path(value).is_dir():
            raise ValueError('Explicit verified local primary_snapshots_directory is required')
        return Path(value).resolve()

    def accepted(self):
        accepted = super().accepted()
        self.validate_local_fifth()
        # A completed core receipt may precede the supplemental jobs during
        # an interrupted local run. Packaging requires local_complete.json.
        if (self.root / 'local_complete.json').exists():
            self.require_local_temporal()
        return accepted

    def require_local_temporal(self):
        for name, key in (('primary','database'),('reproduction','reproduction')):
            require_temporal_receipt(self.root / (name + '-scope-repairs.json'),
                self.c[key],self.inputs,self.meta['database_revision'])
            require_temporal_subject_receipt(self.root / (name + '-complete-subject-scope.json'),
                self.c[key],self.inputs,self.meta['database_revision'],ROOT)
            for suffix in ('scope-repairs','complete-subject-scope'):
                actual=read(self.root/(name+'-'+suffix+'.json'))
                if Path(actual.get('primary_snapshots_dir')or '/MISSING').resolve()!=self.primary_snapshots_directory():
                    raise ValueError('Temporal local audit must use configured explicit source snapshots')

    def local(self):
        self.validate_child_builds()
        # Bind both complete child databases before the original local controller
        # can regard its own fourteen-job receipt as sufficient for packaging.
        for name, key in (('primary','database'),('reproduction','reproduction')):
            report = self.root / (name + '-literal-jet-scope.json')
            if not report.exists():
                self.execute(name + '-literal-jet-scope', self.cmd(SPEC.auditor,
                    '--database',self.c[key],'--inputs',self.inputs,'--output',report))
            require_literal_jet_receipt(report,Path(self.c[key]),self.inputs,self.meta['database_revision'],ROOT)
        for name, key in (('primary','database'),('reproduction','reproduction')):
            report = self.root / (name + '-primary-aircraft-family.json')
            if not report.exists():
                self.execute(name + '-primary-aircraft-family', self.cmd(FAMILY_SPEC.auditor,
                    '--database',self.c[key],'--inputs',self.inputs,'--output',report,
                    '--primary-snapshots-dir',self.primary_snapshots_directory()))
            require_primary_aircraft_receipt(report,Path(self.c[key]),self.inputs,self.meta['database_revision'],ROOT)
        for name, key in (('primary','database'),('reproduction','reproduction')):
            report = self.root / (name + '-owned-scope.json')
            if not report.exists():
                self.execute(name + '-owned-scope', self.cmd(OWNED_SPEC.auditor,
                    '--database',self.c[key],'--inputs',self.inputs,'--output',report))
            require_owned_scope_receipt(report,Path(self.c[key]),self.inputs,self.meta['database_revision'],ROOT)
        super().local()
        write(self.root / 'owned_scope_local_extension.json', {
            'schema':'FINEATLAS_OWNED_SCOPE_LOCAL_EXTENSION_V1','pass':True,
            'revision':self.meta['database_revision'],'fingerprints':self.fingerprints,
            'evidence':{name:{'path':str(self.root / (name + '-owned-scope.json')),
                              'sha256':digest(self.root / (name + '-owned-scope.json'))}
                        for name in ('primary','reproduction')}})
        write(self.root / 'primary_aircraft_local_extension.json' , {
            'schema':'FINEATLAS_PRIMARY_AIRCRAFT_LOCAL_EXTENSION_V1','pass':True,
            'revision':self.meta['database_revision'],'fingerprints':self.fingerprints,
            'evidence':{name:{'path':str(self.root / (name + '-primary-aircraft-family.json')),
                              'sha256':digest(self.root / (name + '-primary-aircraft-family.json'))}
                        for name in ('primary','reproduction')}})
        write(self.root / 'literal_jet_local_extension.json', {
            'schema':'FINEATLAS_LITERAL_JET_LOCAL_EXTENSION_V1','pass':True,
            'revision':self.meta['database_revision'],'fingerprints':self.fingerprints,
            'evidence':{name:{'path':str(self.root / (name + '-literal-jet-scope.json')),
                              'sha256':digest(self.root / (name + '-literal-jet-scope.json'))}
                        for name in ('primary','reproduction')}})

    def package(self):
        self.validate_local_fifth()
        self.require_local_temporal()
        super().package()
        package_path=self.root/'package/delivery_assets.json'; package=read(package_path)
        manifest,archive=package_support(self.c,self.root/'package/regression-support',self.accepted())
        descriptors={name:{'path':str(path),'name':path.name,'bytes':path.stat().st_size,'sha256':digest(path)}
                     for name,path in (('manifest',manifest),('archive',archive))}
        package['assets'].extend(descriptors.values())
        package['regression_support']={**descriptors,'original_ledger_sha256':digest(Path(self.c['legacy_dispositions']))}
        write(package_path,package)

    def validate_public_fifth(self):
        extension_path = self.root / 'public/checks/literal_jet_public_extension.json'
        extension = read(extension_path); accepted = self.accepted()
        database = self.root / 'public/data/fineatlas.sqlite'
        if (extension.get('schema') != 'FINEATLAS_LITERAL_JET_PUBLIC_EXTENSION_V1'
                or extension.get('pass') is not True
                or extension.get('database_revision') != accepted['database_revision']
                or extension.get('database_sha256') != accepted['database_sha256']
                or Path(extension.get('database','')).resolve() != database.resolve()):
            raise ValueError('Complete actual public fifth-delta evidence is required')
        parent_proof = self.root / 'public/checks/public_verification.json'
        if digest(parent_proof) != extension.get('original_public_verification_sha256'):
            raise ValueError('Original public evidence changed after literal-jet checks')
        validate_public_evidence(read(parent_proof),accepted,parent_proof)
        sdk_evidence = extension.get('evidence',{}).get('installed-sdk-inventory')
        if not sdk_evidence or digest(Path(sdk_evidence['path'])) != sdk_evidence['sha256']:
            raise ValueError('Full actual installed fifth SDK inventory evidence required')
        sdk = read(sdk_evidence['path'])
        expected_modules = {name[len('src/fineatlas/'):]:sha for name,sha in self.fingerprints['code'].items() if name.startswith('src/fineatlas/')}
        if (sdk.get('schema') != 'FINEATLAS_LITERAL_JET_INSTALLED_SDK_V1' or sdk.get('pass') is not True or sdk.get('full_source_inventory_checked') is not True
                or sdk.get('database_revision') != accepted['database_revision']
                or Path(sdk.get('database','')).resolve() != database.resolve()
                or sdk.get('source_modules') != expected_modules
                or not Path(sdk.get('sdk_package','')).resolve().is_relative_to((self.root / 'public/venv').resolve())):
            raise ValueError('Matching actual installed complete fifth SDK proof required')
        evidence = extension.get('evidence',{}).get('literal-jet-scope')
        if not evidence or digest(Path(evidence['path'])) != evidence['sha256']:
            raise ValueError('Actual public literal-jet report is absent or changed')
        downloaded_inputs = self.root / 'public/frozen/inputs'
        report = require_literal_jet_receipt(Path(evidence['path']),database,downloaded_inputs,accepted['database_revision'],ROOT)
        # All frozen downloaded inputs must still equal the accepted local freeze.
        actual = {str(p.relative_to(downloaded_inputs)):digest(p) for p in sorted(downloaded_inputs.rglob('*')) if p.is_file()}
        if actual != self.fingerprints['inputs']:
            raise ValueError('Actual downloaded fifth-delta inputs differ from accepted freeze')
        return extension, report

    def validate_public_primary(self):
        fifth, _ = self.validate_public_fifth()
        extension = read(self.root / 'public/checks/primary_aircraft_public_extension.json')
        database = self.root / 'public/data/fineatlas.sqlite'
        if (extension.get('schema') != 'FINEATLAS_PRIMARY_AIRCRAFT_PUBLIC_EXTENSION_V1'
                or extension.get('pass') is not True
                or extension.get('database_revision') != fifth['database_revision']
                or extension.get('database_sha256') != fifth['database_sha256']
                or Path(extension.get('database','')).resolve() != database.resolve()
                or extension.get('literal_jet_public_extension_sha256') != digest(self.root / 'public/checks/literal_jet_public_extension.json')
                or extension.get('original_public_verification_sha256') != fifth['original_public_verification_sha256']):
            raise ValueError('Complete actual public sixth-delta evidence is required')
        evidence = extension.get('evidence',{}).get('primary-aircraft-family')
        if not evidence or digest(Path(evidence['path'])) != evidence['sha256']:
            raise ValueError('Actual public primary-aircraft family report is absent or changed')
        sdk = extension.get('evidence',{}).get('installed-sdk-inventory')
        if sdk != fifth['evidence']['installed-sdk-inventory']:
            raise ValueError('Sixth delta requires the same actual complete installed SDK proof')
        if 'src/fineatlas/structure_primary_aircraft_family_repairs.py' not in self.fingerprints['code']:
            raise ValueError('Sixth delta adapter is absent from the actual frozen SDK inventory')
        report = require_primary_aircraft_receipt(Path(evidence['path']),database,
            self.root / 'public/frozen/inputs',fifth['database_revision'],ROOT)
        retrieval = extension.get('evidence',{}).get('primary-source-retrieval')
        if not retrieval or digest(Path(retrieval['path'])) != retrieval['sha256']:
            raise ValueError('Actual fresh official primary source retrieval evidence is required')
        snapshots = self.root / 'public/source-snapshots'
        require_fresh_retrieval(retrieval['path'],self.root / 'public/frozen/inputs',snapshots)
        if Path(report.get('primary_snapshots_dir') or '/MISSING').resolve() != snapshots.resolve():
            raise ValueError('Public auditor must use the fresh public source snapshots directory')
        original_extension = read(self.root / 'public/checks/resume_public_extension.json')
        temporal = original_extension.get('evidence',{}).get('regression-repairs')
        if not temporal or digest(Path(temporal['path'])) != temporal['sha256']:
            raise ValueError('Actual public temporal regression SQL evidence is required')
        temporal_report=require_temporal_receipt(temporal['path'],database,self.root / 'public/frozen/inputs',fifth['database_revision'])
        if Path(temporal_report['primary_snapshots_dir']).resolve()!=snapshots.resolve():
            raise ValueError('Public temporal audit cannot borrow a host snapshot directory')
        support,downloads=require_public_support(read(self.root/'package/delivery_assets.json'),
            self.root/'public',self.accepted())
        support_evidence=extension.get('evidence',{}).get('regression-support-downloads')
        if not support_evidence or Path(support_evidence['path']).resolve()!=downloads.resolve() or digest(downloads)!=support_evidence['sha256']:
            raise ValueError('Public extension must bind the fresh regression support transfers')
        regression=original_extension.get('evidence',{}).get('legacy-regressions')
        if not regression or digest(Path(regression['path']))!=regression['sha256']:
            raise ValueError('Actual public portable regression gate evidence is required')
        gate=read(regression['path'])
        if (gate.get('pass')is not True or gate.get('complete')is not True
                or gate.get('host_evidence_fallback')is not False or gate.get('original_ledger_bytes_preserved')is not True
                or gate.get('candidate_revision')!=fifth['database_revision']
                or gate.get('dispositions_sha256')!=support.value['dispositions_sha256']
                or gate.get('portable_support_registry_sha256')!=digest(support.path)):
            raise ValueError('Public regression gate must use downloaded original support bytes')
        subject = original_extension.get('evidence',{}).get('complete-subject-scope')
        if not subject or digest(Path(subject['path'])) != subject['sha256']:
            raise ValueError('Actual public temporal complete-subject evidence is required')
        subject_report=require_temporal_subject_receipt(subject['path'],database,self.root / 'public/frozen/inputs',fifth['database_revision'],ROOT)
        if Path(subject_report['primary_snapshots_dir']).resolve()!=snapshots.resolve():
            raise ValueError('Public temporal subject audit must use fresh source snapshots')
        preservation = original_extension.get('evidence',{}).get('resumed-source-preservation')
        if not preservation or digest(Path(preservation['path'])) != preservation['sha256']:
            raise ValueError('Actual temporal raw source preservation evidence is required')
        from structure_owned_source_guard import validate_source_preservation
        validate_source_preservation(preservation['path'],database,self.c['baseline'],support.root/'source-row-digests.json',
            self.root / 'public/frozen/inputs',fifth['database_revision'],ROOT)
        return extension, report

    def validate_public_owned(self):
        primary, _ = self.validate_public_primary()
        extension = read(self.root / 'public/checks/owned_scope_public_extension.json')
        database = self.root / 'public/data/fineatlas.sqlite'
        if (extension.get('schema') != 'FINEATLAS_OWNED_SCOPE_PUBLIC_EXTENSION_V1'
                or extension.get('pass') is not True
                or extension.get('database_revision') != primary['database_revision']
                or extension.get('database_sha256') != primary['database_sha256']
                or Path(extension.get('database','')).resolve() != database.resolve()
                or extension.get('primary_aircraft_public_extension_sha256') != digest(self.root / 'public/checks/primary_aircraft_public_extension.json')
                or extension.get('original_public_verification_sha256') != primary['original_public_verification_sha256']):
            raise ValueError('Complete actual public seventh-delta evidence is required')
        evidence = extension.get('evidence',{}).get('owned-scope')
        if not evidence or digest(Path(evidence['path'])) != evidence['sha256']:
            raise ValueError('Actual public owned-scope report is absent or changed')
        if extension.get('evidence',{}).get('installed-sdk-inventory') != primary['evidence']['installed-sdk-inventory']:
            raise ValueError('Owned-scope delta requires the same actual complete installed SDK proof')
        if 'src/fineatlas/structure_owned_scope_repairs.py' not in self.fingerprints['code']:
            raise ValueError('Owned-scope adapter is absent from the actual frozen SDK inventory')
        report = require_owned_scope_receipt(Path(evidence['path']),database,
            self.root / 'public/frozen/inputs',primary['database_revision'],ROOT)
        expected=self.root/'public/source-snapshots'
        if Path(report.get('primary_snapshots_dir')or '/MISSING').resolve()!=expected.resolve():
            raise ValueError('Public owned audit must use the actual fresh explicit source folder')
        if (self.root/'public/frozen/inputs'/OWNED_SOURCE_REGISTRY).exists():
            item=extension.get('evidence',{}).get('owned-source-retrieval')
            if not item or digest(Path(item['path']))!=item['sha256']:raise ValueError('Actual seventh fresh source retrieval evidence required')
            require_owned_retrieval(item['path'],self.root/'public/frozen/inputs',expected,
                self.root/'public/checks/primary-source-retrieval.json')
        return extension, report

    def public(self):
        self.validate_local_fifth()
        self.require_local_temporal()
        prior_proof = self.root / 'public/checks/public_verification.json'
        if prior_proof.exists():
            # Resume only a complete, verifiable old public run. No repeated
            # download or replacement of an earlier failed/incomplete receipt.
            accepted = self.accepted()
            validate_public_evidence(read(prior_proof),accepted,prior_proof)
            previous = read(self.root / 'public/checks/resume_public_extension.json')
            if previous.get('pass') is not True or previous.get('database_revision') != accepted['database_revision']:
                raise ValueError('Previous complete public extension is required for resumption')
            for item in previous['evidence'].values():
                if digest(Path(item['path'])) != item['sha256']:
                    raise ValueError('Prior public extension evidence changed')
        else:
            super().public()
        database = self.root / 'public/data/fineatlas.sqlite'
        inputs = self.root / 'public/frozen/inputs'; report = self.root / 'public/checks/literal-jet-scope.json'
        if not report.exists():
            self.execute('public-literal-jet-scope',self.cmd(SPEC.auditor,
                '--database',database,'--inputs',inputs,'--output',report,
                python=self.root / 'public/venv/bin/python'))
        require_literal_jet_receipt(report,database,inputs,self.meta['database_revision'],ROOT)
        sdk_report = self.root / 'public/checks/literal-jet-installed-sdk.json'
        if not sdk_report.exists():
            self.execute('public-literal-jet-installed-sdk',
                [str(self.root / 'public/venv/bin/python'),'-I','-B',str(ROOT / 'scripts/verify_literal_jet_installed_sdk.py'),
                 '--database',str(database),'--output',str(sdk_report)])
        accepted = self.accepted()
        extension = {'schema':'FINEATLAS_LITERAL_JET_PUBLIC_EXTENSION_V1','pass':True,
            'database':str(database.resolve()),'database_revision':accepted['database_revision'],
            'database_sha256':accepted['database_sha256'],
            'original_public_verification_sha256':digest(prior_proof),
            'evidence':{'literal-jet-scope':{'path':str(report),'sha256':digest(report)},
                        'installed-sdk-inventory':{'path':str(sdk_report),'sha256':digest(sdk_report)}}}
        write(self.root / 'public/checks/literal_jet_public_extension.json',extension)
        self.validate_public_fifth()
        family_report = self.root / 'public/checks/primary-aircraft-family.json'
        snapshots = self.prepare_public_primary_snapshots(inputs)
        retrieval = self.root / 'public/checks/primary-source-retrieval.json'
        if not family_report.exists():
            self.execute('public-primary-aircraft-family',self.cmd(FAMILY_SPEC.auditor,
                '--database',database,'--inputs',inputs,'--output',family_report,
                '--primary-snapshots-dir',snapshots,
                python=self.root / 'public/venv/bin/python'))
        require_primary_aircraft_receipt(family_report,database,inputs,self.meta['database_revision'],ROOT)
        write(self.root / 'public/checks/primary_aircraft_public_extension.json', {
            'schema':'FINEATLAS_PRIMARY_AIRCRAFT_PUBLIC_EXTENSION_V1','pass':True,
            'database':str(database.resolve()),'database_revision':accepted['database_revision'],
            'database_sha256':accepted['database_sha256'],
            'original_public_verification_sha256':digest(prior_proof),
            'literal_jet_public_extension_sha256':digest(self.root / 'public/checks/literal_jet_public_extension.json'),
            'evidence':{'primary-aircraft-family':{'path':str(family_report),'sha256':digest(family_report)},
                        'primary-source-retrieval':{'path':str(retrieval),'sha256':digest(retrieval)},
                        'regression-support-downloads':{'path':str(self.root/'public/regression-support-downloads.json'),
                            'sha256':digest(self.root/'public/regression-support-downloads.json')},
                        'installed-sdk-inventory':extension['evidence']['installed-sdk-inventory']}})
        self.validate_public_primary()
        owned_report = self.root / 'public/checks/owned-scope.json'
        if not owned_report.exists():
            self.execute('public-owned-scope',self.cmd(OWNED_SPEC.auditor,
                '--database',database,'--inputs',inputs,'--output',owned_report,
                python=self.root / 'public/venv/bin/python'))
        require_owned_scope_receipt(owned_report,database,inputs,self.meta['database_revision'],ROOT)
        write(self.root / 'public/checks/owned_scope_public_extension.json', {
            'schema':'FINEATLAS_OWNED_SCOPE_PUBLIC_EXTENSION_V1','pass':True,
            'database':str(database.resolve()),'database_revision':accepted['database_revision'],
            'database_sha256':accepted['database_sha256'],
            'original_public_verification_sha256':digest(prior_proof),
            'primary_aircraft_public_extension_sha256':digest(self.root / 'public/checks/primary_aircraft_public_extension.json'),
            'evidence':{'owned-scope':{'path':str(owned_report),'sha256':digest(owned_report)},
                        'installed-sdk-inventory':extension['evidence']['installed-sdk-inventory']}})
        if (inputs/OWNED_SOURCE_REGISTRY).exists():
            path=self.root/'public/checks/owned_scope_public_extension.json';owned_extension=read(path)
            owned_retrieval=self.root/'public/checks/owned-source-retrieval.json'
            owned_extension['evidence']['owned-source-retrieval']={'path':str(owned_retrieval),'sha256':digest(owned_retrieval)}
            write(path,owned_extension)
        self.validate_public_owned()

    def finalize(self):
        self.validate_public_owned()
        support,_=require_public_support(read(self.root/'package/delivery_assets.json'),self.root/'public',self.accepted())
        portable_config={**self.c,'reference':str(support.root/'source-row-digests.json')}
        portable_config_path=self.root/'public/portable-finalize-config.json'
        write(portable_config_path,portable_config)
        Coordinator(portable_config_path).finalize()
        write(self.root / 'literal_jet_finalized_extension.json', {
            'schema':'FINEATLAS_LITERAL_JET_FINALIZED_EXTENSION_V1','pass':True,
            'database_revision':self.meta['database_revision'],
            'public_extension_sha256':digest(self.root / 'public/checks/literal_jet_public_extension.json')})
        write(self.root / 'primary_aircraft_finalized_extension.json', {
            'schema':'FINEATLAS_PRIMARY_AIRCRAFT_FINALIZED_EXTENSION_V1','pass':True,
            'database_revision':self.meta['database_revision'],
            'public_extension_sha256':digest(self.root / 'public/checks/primary_aircraft_public_extension.json')})
        write(self.root / 'owned_scope_finalized_extension.json', {
            'schema':'FINEATLAS_OWNED_SCOPE_FINALIZED_EXTENSION_V1','pass':True,
            'database_revision':self.meta['database_revision'],
            'public_extension_sha256':digest(self.root / 'public/checks/owned_scope_public_extension.json')})


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('local','package','public','finalize'))
    parser.add_argument('--config',type=Path,required=True); args=parser.parse_args()
    if not __debug__: raise RuntimeError('Mandatory literal-jet checks cannot run optimized')
    coordinator=LiteralJetCoordinator(args.config)
    # Use the original action lease names to exclude concurrent old/new workers.
    with lease(coordinator.root / (args.action + '.lease.json')):
        getattr(coordinator,args.action)()
