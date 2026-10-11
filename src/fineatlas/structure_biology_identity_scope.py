"""Review exact false identity claims without invalidating native taxon entities."""
import hashlib,json
from fineatlas.hierarchy import apply_refinements, UNIFIED_INPUT_PREFIXES

SCHEMA='FINEATLAS_BIOLOGY_IDENTITY_SCOPE_V1'
STAGE='v1.11-biological-taxonomic-identity-extent'
INPUT_NAME='structure_biology_identity_scope.json'
META_KEY='biology_identity_scope_input_sha256'
canonical=lambda v:json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))
digest=lambda v:hashlib.sha256(canonical(v).encode()).hexdigest()


def require(ok,message):
    if not ok:raise ValueError(message)


def validate(payload,operations):
    require(payload.get('schema')==SCHEMA and payload.get('stage')==STAGE,'Unknown biological identity-scope contract')
    require(payload['label_scope_mismatch_alone_does_not_authorize_identity_split'] is True
            and len(payload['repairs'])==payload['proven_identity_scope_repairs']==len(operations),
            'Identity repair must have its own proven source extent, not an uncertain label')
    for case,op in zip(payload['repairs'],operations):
        proof=case['proof']
        require(op['op']=='split_identity_source' and op['locator']==case['locator'] and op['proof']==proof,
                'Frozen exact identity operation differs')
        require(proof['individual_semantic_review'] is True and proof['source_scope_conflict'] is True
                and proof['world_entities_disposition']=='PRESERVE'
                and proof['native_taxonomy_parent_disposition']=='PRESERVE_ACTIVE'
                and proof['new_identity_equivalence_authorized'] is False,
                'Biological extent repair must preserve real entities and native taxonomy')
        parent=proof['native_parent_witness']
        require(parent['child_uid']==proof['native_included_taxon_uid']
                and parent['parent_uid']==proof['historical_scope_uid']
                and parent['source']=='ott' and parent['source_relation']=='parent_uid'
                and parent['relation']=='IS_A' and parent['status']=='ACTIVE'
                and parent['facet_family']=='TAXONOMIC_LINEAGE'
                and digest({k:v for k,v in parent.items() if k!='id'})==proof['native_parent_witness_sha256'],
                'Identity scope difference lacks an actual native containment statement')
        narrow=proof['modern_narrow_species_record'];excluded=proof['modern_excluded_species_record']
        require(narrow['Taxon_rank']==excluded['Taxon_rank']=='species'
                and narrow['Scientific_name']!=excluded['Scientific_name']
                and excluded['Scientific_name'].split()[1] in narrow['Decision_summary']
                and proof['excluded_modern_taxon_uid']=='avilist:'+excluded['Scientific_name'].lower(),
                'Modern primary taxonomy lacks explicit separate species extent')
        size=proof['scope_size_proof']
        require(size['explicit_old_included_taxon_not_in_modern_species'] is True
                and size['difference_is_extent_not_role_or_label'] is True
                and len(size['old_native_direct_children'])==size['old_native_direct_child_count']
                and len(size['modern_narrow_direct_children'])==size['modern_narrow_direct_child_count'],
                'Extent difference cannot be replaced by a relation degree heuristic')


def preflight(c,payload):
    for case in payload['repairs']:
        loc=case['locator'];rs=list(c.execute('SELECT * FROM bridges WHERE left_uid=? AND right_uid=? AND relation=? AND source=?',
                       tuple(loc[k] for k in ('left_uid','right_uid','relation','source'))))
        require(len(rs)==1 and {k:v for k,v in dict(rs[0]).items() if k!='id'}=={k:v for k,v in case['before_bridge'].items() if k!='id'},
                'Exact original ACTIVE biological identity bridge drifted')
        uid=case['before_bridge']['left_uid'];comp=c.execute('SELECT component_id FROM nodes WHERE uid=?',(uid,)).fetchone()[0]
        members=sorted(r[0] for r in c.execute('SELECT uid FROM nodes WHERE component_id=?',(comp,)))
        require(members==case['prior_component_members'],'Scientific identity component changed before source extent review')
        for n in case['proof']['retained_nodes']:
            row=c.execute('SELECT uid,label,source,rank,data,description,visibility FROM nodes WHERE uid=?',(n['uid'],)).fetchone()
            require(row is not None and dict(row)==n,'Native scientific source endpoint changed')
        p=case['proof']['native_parent_witness'];rows=list(c.execute('SELECT * FROM edges WHERE child_uid=? AND parent_uid=? AND source=? AND source_relation=? AND layer=?',
                    tuple(p[k] for k in ('child_uid','parent_uid','source','source_relation','layer'))))
        require(len(rows)==1 and digest({k:v for k,v in dict(rows[0]).items() if k!='id'})==case['proof']['native_parent_witness_sha256'],
                'Native containment range counterexample changed')


def apply_structure_biology_identity_scope(m):
    path=m.inputs/INPUT_NAME
    if not path.exists():return {'status':'not_requested'}
    payload=json.loads(path.read_text());fingerprint=digest(payload)
    opspath=m.inputs/payload['operations_file']
    require(opspath.name==payload['operations_file'] and hashlib.sha256(opspath.read_bytes()).hexdigest()==payload['operations_sha256'],
            'Frozen identity extent operations hash differs')
    operations=[json.loads(line) for line in opspath.read_text().splitlines() if line.strip()]
    validate(payload,operations)
    prior=m.c.execute('SELECT value FROM metadata WHERE key=?',(META_KEY,)).fetchone()
    if prior:
        require(json.loads(prior[0])==fingerprint,'Immutable identity extent stage already applied with another input')
        return {'status':'already_applied','input_sha256':fingerprint}
    require(UNIFIED_INPUT_PREFIXES.get(payload['operations_file'])=='structure_biology_identity_scope',
            'Exact biological identity scope input must have its own hierarchy metadata prefix')
    preflight(m.c,payload)
    result=apply_refinements(m,payload['operations_file'])
    for case in payload['repairs']:
        actual=[]
        for part in case['expected_partitions']:
            components={m.c.execute('SELECT component_id FROM nodes WHERE uid=?',(u,)).fetchone()[0] for u in part}
            require(len(components)==1,'Surviving scientific identity bridge partition is inconsistent')
            comp=next(iter(components));members=sorted(r[0] for r in m.c.execute('SELECT uid FROM nodes WHERE component_id=?',(comp,)))
            require(members==sorted(part),'Exact source extent partition is not achieved')
            actual.append({'component_id':comp,'members':members})
        require(len({r['component_id'] for r in actual})==len(actual),'Unequal taxonomic extents remain contracted')
        m.change(STAGE,'scientific_identity_scope_review',case['before_bridge']['id'],case['before_bridge'],
                 {'status':'GRAIN_REJECTED','partitions':actual,'all_native_nodes_and_parent_assertions_preserved':True},case['proof'])
    m.meta(META_KEY,fingerprint);m.meta('biology_identity_scope_summary',{
        'reviewed_label_identity_groups':payload['reviewed_cub_label_identity_groups'],
        'actual_scientific_identity_bridges_reviewed':payload['actual_active_bridges_reviewed'],
        'proven_false_identity_bridges_reviewed':len(payload['repairs']),
        'scientific_nodes_invalidated':0,'native_taxonomy_edges_withdrawn':0})
    m.c.commit()
    return {'input_sha256':fingerprint,'proven_identity_scope_repairs':len(payload['repairs']),
            'source_entities_invalidated':0,'native_taxonomy_edges_withdrawn':0,
            'refinements':result,'requires_cache_rebuild':True}
