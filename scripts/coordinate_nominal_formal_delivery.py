#!/usr/bin/env python3
"""Accept an explicit formal four-stage promotion with all original semantic gates."""
from __future__ import annotations
import argparse
import os
from pathlib import Path

from coordinate_nominal_design_scope_delivery import NominalDesignScopeCoordinator
from nominal_scope_prior_delivery import NominalScopePriorCoordinator
from coordinate_structure_delivery import Coordinator, ROOT, metadata, read, write, lease
from build_structure_candidate import build_fingerprints
from portable_nominal_formal_lineage import require_source_binding
from structure_nominal_formal_regression_support import (package_support, download_public_support, require_public_support)
from structure_ninth_complete_type_temporal_contract import require_complete_type_receipt
from structure_nominal_design_scope_delivery_guard import require_nominal_scope_receipt
from _download import digest
from structure_primary_aircraft_delivery_guard import require_primary_aircraft_receipt
from primary_source_snapshot_delivery import require_fresh_retrieval
from structure_eighth_owned_scope_temporal_contract import require_temporal_eighth_regression_receipt as require_temporal_receipt
from structure_eighth_subject_scope_temporal_contract import require_temporal_eighth_subject_receipt


class FormalNominalScopeCoordinator(NominalDesignScopeCoordinator):
    def __init__(self,config):
        self.config_path=Path(config).resolve();self.c=read(config);self.root=Path(self.c['delivery_root']).resolve()
        if Path(self.c['formal_code_root']).resolve()!=ROOT:
            raise ValueError('Formal coordinator must execute its own exact formal code root')
        self.inputs=Path(self.c['inputs']).resolve();self.meta=metadata(self.c['database']);self.fingerprints=build_fingerprints(self.inputs)
        if {key:self.meta['structure_frozen_build_manifest'][key]for key in self.fingerprints}!=self.fingerprints:
            raise ValueError('Formal executable SDK/code/inputs differ from its exact promoted freeze')
        self.env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','PYTHONPATH':str(ROOT/'src')};self.env.pop('PYTHONOPTIMIZE',None)
        builds = self.validate_child_builds()
        self.final_parents={'schema':'FINEATLAS_ACTUAL_FORMAL_VERSION_ONLY_PARENT_INDEPENDENCE_V1','pass':True,
            'stage_count':4,'semantic_candidate_stage_count':6,'generation_count':4,'version_only':True,
            'records':[{'actual_formal_build_id':child['build_id'],'source9_build_id':parent['build_id'],
                'formal_revision':child['revision'],'source9_revision':parent['revision'],
                'formal_build_receipt_sha256':digest(Path(self.c[name+'_build']))}
                for name,(child,parent)in zip(('primary','reproduction'),builds)]}
        # The original controller writes this proof and passes these actual
        # receipts to the public executor. Formal artifacts have four stages;
        # the six-stage source candidate stays in the separate source proof.
        self.parents = self.final_parents
        self.lineage_primary = Path(self.c['primary_build']).resolve()
        self.lineage_reproduction = Path(self.c['reproduction_build']).resolve()

    def validate_child_builds(self):
        rows=[];inodes=[]
        for name in ('primary','reproduction'):
            child,parent,integrity=require_source_binding(self.c,name,Path(self.c[name+'_build']))
            if child['revision']!=self.meta['database_revision']:
                raise ValueError('Actual four-stage formal build does not match this formal database')
            for database in (parent['database'],child['database']):
                stat=Path(database).stat();inodes.append((stat.st_dev,stat.st_ino))
            rows.append((child,parent))
        if len(set(inodes))!=4 or rows[0][0]['build_id']==rows[1][0]['build_id']or rows[0][1]['build_id']==rows[1][1]['build_id']:
            raise ValueError('Formal pair requires two actual independent Source9 sources and formal files')
        return rows

    def cmd(self,script,*values,python=None):
        if script=='run_structure_public_checks.py':
            package=read(self.root/'package/delivery_assets.json')
            support,_=download_public_support(package,self.root/'public',self.c['public_base_url'],self.accepted())
            values=list(values)
            replacements={'--reference':support.root/'source-row-digests.json','--inventory':support.root/'domain-inventory.json',
                '--primary-build':support.root/'builds/primary/build_complete.json',
                '--reproduction-build':support.root/'builds/reproduction/build_complete.json',
                '--legacy-reference':support.root/'reference.csv','--legacy-baseline-matrix':support.root/'baseline',
                '--legacy-dispositions':support.root/'dispositions.json','--regression-support-registry':support.path,
                '--primary-snapshots-dir':self.prepare_public_primary_snapshots(self.root/'public/frozen/inputs')}
            for flag,value in replacements.items():
                if values.count(flag)>1:raise ValueError('Duplicate public evidence flag: '+flag)
                if flag in values:values[values.index(flag)+1]=value
                else:values.extend([flag,value])
            return Coordinator.cmd(self,'run_nominal_formal_public_checks.py',*values,python=python)
        return NominalDesignScopeCoordinator.cmd(self,script,*values,python=python)

    def package(self):
        self.validate_child_builds();self.validate_local_fifth();self.require_local_temporal()
        self.require_local_complete_type();self.require_local_nominal_scope()
        Coordinator.package(self)
        package_path=self.root/'package/delivery_assets.json';package=read(package_path)
        manifest,archive=package_support(self.c,self.root/'package/regression-support',self.accepted())
        assets={}
        for name,path in (('manifest',manifest),('archive',archive)):
            item={'path':str(path),'name':path.name,'bytes':path.stat().st_size,'sha256':digest(path)}
            assets[name]=item;package['assets'].append(item)
        assets['original_ledger_sha256']=digest(Path(self.c['legacy_dispositions']))
        package['regression_support']=assets
        write(package_path,package)

    def public(self):
        self.require_local_complete_type();self.require_local_nominal_scope()
        NominalScopePriorCoordinator.public(self)
        database=self.root/'public/data/fineatlas.sqlite';inputs=self.root/'public/frozen/inputs'
        complete=self.root/'public/checks/complete-owned-type-source-first.json'
        nominal=self.root/'public/checks/nominal-design-scope-source-first.json'
        require_complete_type_receipt(complete,database,inputs,self.meta['database_revision'],ROOT)
        require_nominal_scope_receipt(nominal,database,inputs,self.meta['database_revision'],ROOT)
        support,download_receipt=require_public_support(read(self.root/'package/delivery_assets.json'),self.root/'public',self.accepted())
        extension={'schema':'FINEATLAS_FORMAL_NOMINAL_PUBLIC_EXTENSION_V1','pass':True,
            'database_revision':self.meta['database_revision'],'database_sha256':self.accepted()['database_sha256'],
            'actual_stage_count':4,'semantic_candidate_stage_count':6,'generation_count':4,
            'evidence':{name:{'path':str(path),'sha256':digest(path)}for name,path in (
                ('complete-source-audit',complete),('nominal-source-audit',nominal),
                ('four-generation-support',support.path),('support-download',download_receipt),
                ('prior-owned-public',self.root/'public/checks/owned_scope_public_extension.json'))}}
        write(self.root/'public/checks/formal_nominal_public_extension.json',extension)
        self.validate_public_nominal_scope()

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
        subject_report=require_temporal_eighth_subject_receipt(subject['path'],database,self.root / 'public/frozen/inputs',fifth['database_revision'],ROOT)
        if Path(subject_report['primary_snapshots_dir']).resolve()!=snapshots.resolve():
            raise ValueError('Public temporal subject audit must use fresh source snapshots')
        preservation = original_extension.get('evidence',{}).get('resumed-source-preservation')
        if not preservation or digest(Path(preservation['path'])) != preservation['sha256']:
            raise ValueError('Actual temporal raw source preservation evidence is required')
        from structure_eighth_owned_source_guard import validate_source_preservation
        validate_source_preservation(preservation['path'],database,self.c['baseline'],support.root/'source-row-digests.json',
            self.root / 'public/frozen/inputs',fifth['database_revision'],ROOT)
        return extension, report


    def validate_public_complete_type(self):
        self.validate_public_owned()
        value=read(self.root/'public/checks/formal_nominal_public_extension.json');accepted=self.accepted()
        if (value.get('schema')!='FINEATLAS_FORMAL_NOMINAL_PUBLIC_EXTENSION_V1'or value.get('pass')is not True
                or value.get('database_revision')!=accepted['database_revision']or value.get('database_sha256')!=accepted['database_sha256']
                or value.get('actual_stage_count')!=4 or value.get('semantic_candidate_stage_count')!=6 or value.get('generation_count')!=4):
            raise ValueError('Actual fresh formal four-generation public extension required')
        for row in value['evidence'].values():
            if digest(Path(row['path']))!=row['sha256']:raise ValueError('Actual formal public evidence changed')
        require_complete_type_receipt(value['evidence']['complete-source-audit']['path'],self.root/'public/data/fineatlas.sqlite',
            self.root/'public/frozen/inputs',accepted['database_revision'],ROOT)
        require_public_support(read(self.root/'package/delivery_assets.json'),self.root/'public',accepted)
        return value

    def validate_public_nominal_scope(self):
        value=self.validate_public_complete_type()
        require_nominal_scope_receipt(value['evidence']['nominal-source-audit']['path'],self.root/'public/data/fineatlas.sqlite',
            self.root/'public/frozen/inputs',self.meta['database_revision'],ROOT)
        return value

    def finalize(self):
        self.validate_public_nominal_scope()
        support,_=require_public_support(read(self.root/'package/delivery_assets.json'),self.root/'public',self.accepted())
        original=self.c;self.c={**original,'reference':str(support.root/'source-row-digests.json')}
        try:Coordinator.finalize(self)
        finally:self.c=original
        write(self.root/'formal_nominal_finalized_extension.json',{
            'schema':'FINEATLAS_FORMAL_NOMINAL_FINALIZED_EXTENSION_V1','pass':True,
            'database_revision':self.meta['database_revision'],'actual_stage_count':4,'generation_count':4,
            'public_extension_sha256':digest(self.root/'public/checks/formal_nominal_public_extension.json')})


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('local','package','public','finalize'));p.add_argument('--config',type=Path,required=True)
    args=p.parse_args();coordinator=FormalNominalScopeCoordinator(args.config)
    with lease(coordinator.root/(args.action+'.lease.json')):getattr(coordinator,args.action)()
