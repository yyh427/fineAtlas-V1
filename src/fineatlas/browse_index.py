"""Rebuild direct-link and native-field indexes without changing source graphs."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path

from .semantics import CLASS_ROLES, TYPED_TERMINALS, VIEWS, edge_predicate, role_expression
from .browse_preferences import build_preferences
from .browse_cache import build_group_cache


SCHEMA = """
CREATE TABLE IF NOT EXISTS browse_build_stages(stage TEXT PRIMARY KEY,fingerprint TEXT NOT NULL,summary TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS browse_nodes(uid TEXT PRIMARY KEY,component_id INTEGER NOT NULL,
    role TEXT NOT NULL,view_mask INTEGER NOT NULL,source TEXT NOT NULL) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS browse_nodes_component ON browse_nodes(component_id,role,uid,view_mask);
CREATE TABLE IF NOT EXISTS browse_links(view TEXT NOT NULL,parent_component INTEGER NOT NULL,
    child_component INTEGER NOT NULL,role TEXT NOT NULL,relation TEXT NOT NULL,
    representative_uid TEXT NOT NULL,storage TEXT NOT NULL,record_id INTEGER NOT NULL,
    source_arc_count INTEGER NOT NULL,
    PRIMARY KEY(view,parent_component,child_component,role,relation)) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS browse_links_child ON browse_links(view,child_component,parent_component,relation);
CREATE INDEX IF NOT EXISTS browse_links_role ON browse_links(view,parent_component,role,child_component,relation);
CREATE TABLE IF NOT EXISTS browse_facets(uid TEXT NOT NULL,component_id INTEGER NOT NULL,
    facet TEXT NOT NULL,value TEXT NOT NULL,source_field TEXT NOT NULL,
    PRIMARY KEY(uid,facet,value)) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS browse_facets_component ON browse_facets(component_id,facet,value,uid);
CREATE INDEX IF NOT EXISTS browse_facets_value ON browse_facets(facet,value,component_id,uid);
CREATE TABLE IF NOT EXISTS browse_link_counts(view TEXT NOT NULL,parent_component INTEGER NOT NULL,
    role TEXT NOT NULL,relation TEXT NOT NULL,concept_count INTEGER NOT NULL,source_arc_count INTEGER NOT NULL,
    PRIMARY KEY(view,parent_component,role,relation)) WITHOUT ROWID;
"""


def build_browse_index(database, reports, *, release=None, source=None):
    database=Path(database);reports=Path(reports);reports.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(':memory:' if source else database);c.row_factory=sqlite3.Row
    if source:
        source=Path(source).resolve()
        if database.exists():raise ValueError('Staging output already exists')
        c.execute('ATTACH DATABASE ? AS source',(source.as_uri()+'?mode=ro&immutable=1',))
        c.execute('CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
        c.execute('INSERT INTO metadata SELECT * FROM source.metadata');c.commit()
    c.execute("PRAGMA temp_store="+('MEMORY' if source else 'FILE'));c.execute("PRAGMA cache_size=-500000")
    c.execute("PRAGMA busy_timeout=30000")
    metadata={r[0]:json.loads(r[1]) for r in c.execute("SELECT key,value FROM metadata")}
    if metadata.get("schema")!="FINEATLAS_SINGLE_DB_V1":
        raise ValueError("Unsupported database schema")
    revision=metadata.get("database_revision",metadata.get("release","")+":"+str((source or database).stat().st_size))
    if metadata.get('browse_index_revision')==revision:
        revision=metadata.get('browse_parent_revision',revision)
    if "database_revision" not in metadata:
        c.execute("INSERT OR REPLACE INTO metadata VALUES('database_revision',?)",(json.dumps(revision),))
        c.commit()
    fingerprint=hashlib.sha256(json.dumps({"revision":revision,
        "code":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "preferences":hashlib.sha256(Path(__file__).with_name('browse_preferences.py').read_bytes()).hexdigest(),
        "group_cache":hashlib.sha256(Path(__file__).with_name('browse_cache.py').read_bytes()).hexdigest(),
        "semantics":hashlib.sha256(Path(__file__).with_name('semantics.py').read_bytes()).hexdigest()
    },sort_keys=True).encode()).hexdigest()
    c.executescript('BEGIN;'+SCHEMA+'COMMIT;')
    old=c.execute("SELECT DISTINCT fingerprint FROM browse_build_stages").fetchall()
    if old and any(r[0]!=fingerprint for r in old):
        for table in ['browse_links','browse_nodes','browse_facets','browse_link_counts','browse_build_stages']:
            c.execute('DELETE FROM '+table)
    c.execute("INSERT OR REPLACE INTO metadata VALUES('browse_indexes_ready','false')")
    c.commit()
    summaries={}

    def stage(name,run):
        prior=c.execute('SELECT summary FROM browse_build_stages WHERE stage=? AND fingerprint=?',(name,fingerprint)).fetchone()
        if prior:
            summaries[name]=json.loads(prior[0]);print('SKIP',name,flush=True);return
        start=time.monotonic();print('START',name,flush=True);result=run()
        summaries[name]={**result,'seconds':time.monotonic()-start}
        c.execute('INSERT OR REPLACE INTO browse_build_stages VALUES(?,?,?)',(name,fingerprint,json.dumps(summaries[name],sort_keys=True)))
        c.commit();(reports/(name+'.json')).write_text(json.dumps(summaries[name],indent=2)+'\n')
        print('DONE',name,summaries[name],flush=True)

    def nodes():
        c.execute('DELETE FROM browse_nodes')
        mask='+'.join(f"CASE WHEN p.uid IS NULL OR json_type(p.attributes,'$.allowed_views') IS NOT 'array' OR EXISTS(SELECT 1 FROM json_each(p.attributes,'$.allowed_views') av WHERE av.value='{view}') THEN {bit} ELSE 0 END" for view,bit in zip(VIEWS,[1,2,4]))
        c.execute("INSERT INTO browse_nodes SELECT n.uid,n.component_id,"+role_expression('n','p')+",("+mask+"),coalesce(n.source,'') FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.visibility='ACTIVE'")
        return {'rows':c.execute('SELECT count(*) FROM browse_nodes').fetchone()[0]}
    stage('nodes',nodes)

    for view,bit in zip(VIEWS,[1,2,4]):
        def links(view=view,bit=bit):
            c.execute('DELETE FROM browse_links WHERE view=?',(view,))
            roles=set(CLASS_ROLES)
            if view=='taxonomy':roles.add('BIOLOGICAL_VARIANT')
            if view=='membership':roles.add('DATASET_CATEGORY')
            marks=','.join('?' for _ in roles);ordered=sorted(roles)
            c.execute(f"""INSERT INTO browse_links
                SELECT ?,p.component_id,n.component_id,n.role,e.relation,min(n.uid),'edge',min(e.id),count(*)
                FROM edges e JOIN browse_nodes n ON n.uid=e.child_uid
                JOIN browse_nodes p ON p.uid=e.parent_uid
                WHERE {edge_predicate(view)} AND n.role IN ({marks}) AND p.role IN ({marks})
                AND (n.view_mask & ?)<>0 AND (p.view_mask & ?)<>0
                AND n.component_id<>p.component_id
                GROUP BY p.component_id,n.component_id,n.role,e.relation""",
                [view,*ordered,*ordered,bit,bit])
            before=c.execute('SELECT count(*) FROM browse_links WHERE view=?',(view,)).fetchone()[0]
            combinations=[];arguments=[]
            for role,rels in sorted(TYPED_TERMINALS.items()):
                combinations.append('(n.role=? AND e.relation IN ('+','.join('?' for _ in rels)+'))')
                arguments += [role,*rels]
            c.execute(f"""INSERT INTO browse_links
                SELECT ?,p.component_id,n.component_id,n.role,e.relation,min(n.uid),'entity',min(e.id),count(*)
                FROM entity_relations e JOIN browse_nodes n ON n.uid=e.subject_uid
                JOIN browse_nodes p ON p.uid=e.object_uid
                WHERE e.status='ACTIVE' AND ({' OR '.join(combinations)})
                AND p.role IN ({marks}) AND (n.view_mask & ?)<>0 AND (p.view_mask & ?)<>0
                AND n.component_id<>p.component_id
                GROUP BY p.component_id,n.component_id,n.role,e.relation""",
                [view,*arguments,*ordered,bit,bit])
            after=c.execute('SELECT count(*) FROM browse_links WHERE view=?',(view,)).fetchone()[0]
            return {'classification_links':before,'typed_links':after-before,'identity_self_links_excluded':True}
        stage('links-'+view,links)

    def source_facets():
        c.execute("DELETE FROM browse_facets WHERE facet='source'")
        c.execute("INSERT INTO browse_facets SELECT uid,component_id,'source',source,'nodes.source' FROM browse_nodes WHERE source<>''")
        return {'source_values':c.execute("SELECT count(*) FROM browse_facets WHERE facet='source'").fetchone()[0]}
    stage('facets-source',source_facets)

    def native_facets():
        c.execute("DELETE FROM browse_facets WHERE facet<>'source'")
        conditions=[
            ('manufacturer',"trim(json_extract(n.data,'$.MFR'))","n.source='faa'",'nodes.data.MFR'),
            ('native_model',"trim(json_extract(n.data,'$.MODEL'))","n.source='faa'",'nodes.data.MODEL'),
            ('aircraft_type',"trim(json_extract(n.data,'$.\"TYPE-ACFT\"'))","n.source='faa'",'nodes.data.TYPE-ACFT'),
            ('engine_type',"trim(json_extract(n.data,'$.\"TYPE-ENG\"'))","n.source='faa'",'nodes.data.TYPE-ENG'),
            ('manufacturer',"trim(json_extract(n.data,'$.make'))","n.source='epa'",'nodes.data.make'),
            ('native_model',"trim(json_extract(n.data,'$.model'))","n.source='epa'",'nodes.data.model'),
            ('base_model',"trim(json_extract(n.data,'$.baseModel'))","n.source='epa'",'nodes.data.baseModel'),
            ('year',"trim(json_extract(n.data,'$.year'))","n.source='epa'",'nodes.data.year'),
            ('vehicle_class',"trim(json_extract(n.data,'$.VClass'))","n.source='epa'",'nodes.data.VClass'),
            ('manufacturer',"trim(json_extract(n.data,'$.manufacturer'))","json_type(n.data,'$.manufacturer')='text'",'nodes.data.manufacturer'),
            ('series',"trim(json_extract(n.data,'$.series_designation'))","json_type(n.data,'$.series_designation')='text'",'nodes.data.series_designation'),
            ('catalogue',"trim(json_extract(n.data,'$.catalogue'))","json_type(n.data,'$.catalogue')='text'",'nodes.data.catalogue'),
        ]
        totals={}
        for facet,expression,condition,field in conditions:
            c.execute(f"""INSERT OR IGNORE INTO browse_facets
                SELECT n.uid,n.component_id,?,{expression},? FROM nodes n
                JOIN browse_nodes bn ON bn.uid=n.uid WHERE {condition} AND {expression} IS NOT NULL AND {expression}<>''""",(facet,field))
            totals[field]=c.execute('SELECT changes()').fetchone()[0]
        for facet,expression,field in [
            ('country',"json_extract(p.attributes,'$.country_code')",'node_profiles.attributes.country_code'),
            ('admin1',"json_extract(p.attributes,'$.country_code')||':'||json_extract(p.attributes,'$.admin_codes[0]')",'node_profiles.attributes.country_code + admin_codes[0]'),
        ]:
            nonempty_admin=" AND coalesce(json_extract(p.attributes,'$.country_code'),'')<>'' AND coalesce(json_extract(p.attributes,'$.admin_codes[0]'),'')<>''" if facet=='admin1' else ''
            c.execute(f"""INSERT OR IGNORE INTO browse_facets SELECT n.uid,n.component_id,?,{expression},?
                FROM node_profiles p JOIN browse_nodes n ON n.uid=p.uid
                WHERE n.role='INSTANCE' AND json_type(p.attributes,'$.country_code')='text'
                AND {expression} IS NOT NULL AND {expression}<>'' {nonempty_admin}""",(facet,field))
            totals[field]=c.execute('SELECT changes()').fetchone()[0]
        # Model/variant manufacturer and literal designation are supplied by
        # explicit retained EPA parent-field assertions, not guessed from labels.
        for facet,field in [('manufacturer','make'),('native_model','native_parent_field')]:
            value="json_extract(e.data,'$.admission_basis.make')" if facet=='manufacturer' else "CASE json_extract(e.data,'$.admission_basis.native_parent_field') WHEN 'baseModel' THEN json_extract(e.data,'$.admission_basis.baseModel') WHEN 'model' THEN json_extract(e.data,'$.admission_basis.model') END"
            c.execute(f"""INSERT OR IGNORE INTO browse_facets
              SELECT bn.uid,bn.component_id,?,trim({value}),?
              FROM entity_relations e JOIN browse_nodes bn ON bn.uid=e.object_uid
              WHERE e.status='ACTIVE' AND e.relation='CONFIGURATION_OF'
                AND e.source='EPA normalized native fields'
                AND bn.role IN ('MODEL','MODEL_FAMILY','CONFIGURATION')
                AND json_extract(e.data,'$.admission_basis.native_parent_field') IN ('baseModel','model')
                AND json_type(e.data,'$.admission_basis.native_record_sha256')='text'
                AND {value} IS NOT NULL AND trim({value})<>''""",
              (facet,'entity_relations.data.admission_basis.'+field))
            totals['retained_EPA_parent_field.'+field]=c.execute('SELECT changes()').fetchone()[0]
        return {'source_fields':totals,'inferred_from_labels':0,'missing_fields_not_fabricated':True}
    stage('facets-native',native_facets)

    def counts():
        c.execute('DELETE FROM browse_link_counts')
        c.execute("INSERT INTO browse_link_counts SELECT view,parent_component,role,relation,count(*),sum(source_arc_count) FROM browse_links GROUP BY view,parent_component,role,relation")
        return {'rows':c.execute('SELECT count(*) FROM browse_link_counts').fetchone()[0]}
    stage('counts',counts)
    stage('preferred-links',lambda:build_preferences(c))
    stage('catalogue-counts',lambda:build_group_cache(c))
    if release:
        c.execute("INSERT OR REPLACE INTO metadata VALUES('release',?)",(json.dumps(release),))
    new_revision=hashlib.sha256(json.dumps({'parent':revision,'browse_fingerprint':fingerprint,
        'release':release or metadata.get('release','')},sort_keys=True).encode()).hexdigest()
    c.execute("INSERT OR REPLACE INTO metadata VALUES('browse_parent_revision',?)",(json.dumps(revision),))
    c.execute("INSERT OR REPLACE INTO metadata VALUES('database_revision',?)",(json.dumps(new_revision),))
    c.execute("INSERT OR REPLACE INTO metadata VALUES('browse_index_revision',?)",(json.dumps(new_revision),))
    c.execute("INSERT OR REPLACE INTO metadata VALUES('browse_indexes_ready','true')")
    c.execute('PRAGMA analysis_limit=1000');c.execute('ANALYZE main');c.commit()
    if source:
        c.execute("UPDATE metadata SET value=? WHERE key='schema'",(json.dumps('FINEATLAS_BROWSE_INDEX_V1'),))
        c.execute("INSERT OR REPLACE INTO metadata VALUES('browse_source_revision',?)",(json.dumps(revision),))
        c.commit()
        output=sqlite3.connect(database)
        c.backup(output);output.close()
    c.close()
    result={'database':str(database),'index_revision':new_revision,'parent_revision':revision,'stages':summaries,
            'source_graph_mutated':False,'facet_groups_are_is_a':False,'ready':True,
            'staging_source':str(source) if source else None,
            'staging_artifact_needs_attachment_to_candidate':bool(source)}
    (reports/'browse_index_summary.json').write_text(json.dumps(result,indent=2)+'\n')
    return result
