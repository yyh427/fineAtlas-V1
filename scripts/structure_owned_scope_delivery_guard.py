"""Require the independent owned-scope repair audit for this child checkpoint."""
from pathlib import Path
import hashlib
import json
import sqlite3

from structure_delivery_delta_registry import DeltaAudit, input_path, validate_delta_receipt

SPEC = DeltaAudit('owned-scope', 'src/fineatlas/structure_owned_scope_repairs.py',
                 'structure_owned_scope_repairs.json', 'audit_owned_scope_repairs.py',
                 'FINEATLAS_INDEPENDENT_OWNED_SCOPE_AUDIT_V1', 'owned_scope_repairs')


def require_owned_scope_receipt(report, database, inputs, revision, code_root):
    if input_path(SPEC, Path(inputs), Path(code_root)) is None:
        raise ValueError('Owned-scope child requires its frozen seventh delta')
    value = validate_delta_receipt(SPEC, Path(report), Path(database), Path(inputs), revision, Path(code_root))
    if value is None:
        raise ValueError('Complete actual owned-scope evidence is required')
    manifest_path=input_path(SPEC,Path(inputs),Path(code_root));manifest=json.loads(manifest_path.read_text())
    operations=[json.loads(line)for line in (Path(inputs)/manifest['operations_file']).read_text().splitlines()if line]
    purposes=[op for op in operations if op.get('proof',{}).get('owned_physical_scope_kind')=='OWNED_NOMINAL_DESIGN_FUNCTION_OR_PURPOSE']
    if purposes:
        name=manifest.get('source_purpose_review_file','');path=Path(inputs)/name
        if not name or Path(name).name!=name or '\\'in name or not path.is_file():
            raise ValueError('Portable independent source-purpose review is required')
        sha=hashlib.sha256(path.read_bytes()).hexdigest()
        with sqlite3.connect(Path(database).resolve().as_uri()+'?mode=ro&immutable=1',uri=True)as con:
            frozen=json.loads(con.execute('SELECT value FROM metadata WHERE key="structure_frozen_build_manifest"').fetchone()[0])['inputs']
        if sha!=manifest.get('source_purpose_review_sha256')or frozen.get(name)!=sha:
            raise ValueError('Independent source-purpose review is not bound to this frozen database')
        expected=sorted((op['uid'],op['parent'],name,sha)for op in purposes)
        actual=sorted((row['uid'],row['parent'],row['file'],row['sha256'])for row in value.get('verified_purpose_source_reviews',[]))
        if actual!=expected:
            raise ValueError('Every actual nominal purpose requires its independent whole-source check')
    elif value.get('verified_purpose_source_reviews')not in(None,[]):
        raise ValueError('Audit claims source-purpose reviews outside frozen operations')
    def documents(raw):
        if isinstance(raw,dict):
            if raw.get('source_kind')=='PRIMARY_MANUFACTURER_OR_REGULATOR':yield raw
            for item in raw.values():yield from documents(item)
        elif isinstance(raw,list):
            for item in raw:yield from documents(item)
    needed={(doc['source_uri'],doc['sha256'])for op in operations for doc in documents(op.get('proof',{}))}
    if needed:
        directory=Path(value.get('primary_snapshots_dir')or '/MISSING').resolve()
        if not directory.is_dir():raise ValueError('Actual owned-scope primary source directory is required')
        registered={}
        with sqlite3.connect(Path(database).resolve().as_uri()+'?mode=ro&immutable=1',uri=True)as con:
            frozen=json.loads(con.execute('SELECT value FROM metadata WHERE key="structure_frozen_build_manifest"').fetchone()[0])['inputs']
        for name in ('structure_primary_source_snapshots.json','structure_owned_source_snapshots.json'):
            path=Path(inputs)/name
            if not path.exists():continue
            if hashlib.sha256(path.read_bytes()).hexdigest()!=frozen.get(name):raise ValueError('Owned source registry is not frozen')
            registry=json.loads(path.read_text())
            if registry.get('schema')!='FINEATLAS_PORTABLE_PRIMARY_SOURCE_SNAPSHOTS_V1':raise ValueError('Invalid owned portable source registry')
            for doc in registry['documents'].values():
                locator=(doc['source_uri'],doc['sha256'])
                if locator in registered and registered[locator]!=doc:raise ValueError('Conflicting portable source locator')
                registered[locator]=doc
        expected={}
        for locator in needed:
            doc=registered.get(locator)
            if not doc or not locator[0].startswith('https://')or doc.get('hash_basis')!='HTTP_RESPONSE_BODY_BYTES':raise ValueError('Missing required owned portable source')
            name=doc['filename'];path=directory/name
            if (not name or Path(name).name!=name or '\\'in name or name in('.','..')or path.is_symlink()
                    or not path.is_file()or path.resolve().parent!=directory or hashlib.sha256(path.read_bytes()).hexdigest()!=locator[1]):
                raise ValueError('Owned primary source bytes absent or changed')
            expected[name]={'source_uri':locator[0],'sha256':locator[1]}
        if value.get('verified_primary_sources')!=expected:raise ValueError('Complete actual owned documentary source census required')
    elif value.get('verified_primary_sources')not in (None,{}):
        raise ValueError('Owned source report claims documents outside frozen operations')
    if any(op.get('op')=='migrate_nominal_design_mapping'for op in operations):
        if value.get('author_annotations_verified')!=10000:raise ValueError('All 10000 complete author annotations must be independently verified')
        files=manifest.get('author_annotation_files',[])
        if len(files)!=9:raise ValueError('Nine original author annotation files must be frozen')
        with sqlite3.connect(Path(database).resolve().as_uri()+'?mode=ro&immutable=1',uri=True)as con:
            frozen=json.loads(con.execute('SELECT value FROM metadata WHERE key="structure_frozen_build_manifest"').fetchone()[0])['inputs']
        for row in files:
            name=row.get('filename')or row.get('file')or '';path=Path(inputs)/name
            if Path(name).name!=name or not path.is_file()or frozen.get(name)!=row['sha256']or hashlib.sha256(path.read_bytes()).hexdigest()!=row['sha256']or path.stat().st_size!=row['bytes']:
                raise ValueError('Actual complete author annotation bytes changed')
    return value
