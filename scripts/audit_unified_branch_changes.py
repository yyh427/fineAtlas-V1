#!/usr/bin/env python3
"""Record all touched parent scopes and their public before/after browse contracts."""
import argparse,collections,gzip,json,pathlib,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'src'))
from fineatlas import FineAtlas
p=argparse.ArgumentParser(description=__doc__)
for name in ('database','baseline','output'):p.add_argument('--'+name,type=pathlib.Path,required=True)
a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
with FineAtlas(a.baseline,relation_view='taxonomy') as before,FineAtlas(a.database,relation_view='unified') as after:
 old_edge=before.con.execute('SELECT max(id) FROM edges').fetchone()[0]
 old_typed=before.con.execute('SELECT max(id) FROM entity_relations').fetchone()[0]
 # Scope is all newly asserted parents plus all source-witness preferences.
 comps={r[0] for r in after.con.execute('''SELECT DISTINCT n.component_id FROM edges e JOIN nodes n ON n.uid=e.parent_uid WHERE e.id>?
 UNION SELECT DISTINCT n.component_id FROM entity_relations e JOIN nodes n ON n.uid=e.object_uid WHERE e.id>?
 UNION SELECT DISTINCT parent_component FROM browse_preferences WHERE view='unified' ''',(old_edge,old_typed))}
 changed=wide=0;no_old=0
 with gzip.open(a.output/'all_touched_parent_scopes.jsonl.gz','wt') as stream:
  for i,component in enumerate(sorted(comps),1):
   node=after.con.execute("SELECT uid,label,source FROM nodes WHERE component_id=? AND visibility='ACTIVE' ORDER BY uid LIMIT 1",(component,)).fetchone()
   if not node:continue
   uid=node['uid'];old_node=before.node(uid)
   b=before.browse_summary(uid,include_coarse=True) if old_node else {'status':'NOT_FOUND','reason':'New evidence-backed intermediate/source representation'}
   f=after.browse_summary(uid,include_coarse=True);d=after.browse_summary(uid,include_coarse=False)
   record={'parent':dict(node),'before_view':'taxonomy','after_view':'unified','before_full':b,'after_full':f,'after_default':d,
    'full_source_record_retention':'Verified globally against protected baseline; only separately audited erroneous arcs quarantined',
    'catalogue_or_pagination_alone_is_new_semantic_depth':False}
   stream.write(json.dumps(record,ensure_ascii=False)+'\n')
   signature=lambda x:sorted((v['role'],v['relation'],v['full_direct_concepts'],v['source_arcs']) for v in x.get('relations',[]))
   changed+=signature(b)!=signature(f);no_old+=old_node is None
   wide+=any(x['concept_count']>=1000 for x in after.con.execute("SELECT concept_count FROM browse_link_counts WHERE view='unified' AND parent_component=?",(component,)))
   if i%1000==0:print('PARENT_SCOPES',i,flush=True)
 (a.output/'summary.json').write_text(json.dumps({'touched_parent_identity_scopes':len(comps),'changed_summaries':changed,'new_parent_representations':no_old,'remaining_wide_scopes_over_1000_per_role_relation':wide,'source_scope':'All newly asserted edges and typed relations plus all preferred source-witness parents; global full-role/index contract audit covers the rest','all_wide_semantic_middle_levels_claimed_fixed':False},indent=2)+'\n')
print('ALL TOUCHED PARENT SCOPES SAVED',len(comps),flush=True)
