#!/usr/bin/env python3
"""Recheck newly generated lexical parents against independent kind evidence."""
import argparse,collections,hashlib,json,sqlite3,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from fineatlas.nominal import WordNetKinds,object_kind_head
from fineatlas.semantics import role_expression
p=argparse.ArgumentParser();p.add_argument('--database',required=True);p.add_argument('--inputs',required=True);p.add_argument('--output',required=True);a=p.parse_args()
I=Path(a.inputs);O=Path(a.output);O.mkdir(parents=True,exist_ok=True);c=sqlite3.connect(Path(a.database).resolve().as_uri()+'?mode=ro&immutable=1',uri=True);c.row_factory=sqlite3.Row;c.execute('PRAGMA cache_size=-1048576');k=WordNetKinds(c,include_native=True)
records=[json.loads(line) for name in ['hierarchy_facts.jsonl','hierarchy_extensions.jsonl'] for line in (I/name).open()];repairs=[];counts=collections.Counter();affected=set();nodes={}
def node(uid):
 if uid not in nodes:nodes[uid]=dict(c.execute('SELECT n.uid,n.label,n.description,n.component_id,'+role_expression('n','p')+' role FROM nodes n LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.uid=?',(uid,)).fetchone())
 return nodes[uid]
for r in records:
 head=r.get('proof',{}).get('head') or r.get('proof',{}).get('nominal_head')
 if r['op']!='link' or not head or r['proof']['basis'] not in {'INDEPENDENT_NOMINAL_HEAD_AND_GENERIC_PARENT_DEFINITION','INDEPENDENT_LEGACY_ARTIFACT_DEFINITION_WITH_VERIFIED_GENERIC_HEAD'}:continue
 counts['checked_lexical_claims']+=1
 if node(r['uid'])['role']=='INSTANCE':counts['instance_endpoint_guard']+=1;continue
 parent=k.resolve_head(object_kind_head(head))
 if parent and node(parent)['role']!='CLASS':parent=None
 if parent and node(parent)['component_id']==node(r['parent'])['component_id'] and k.generic_type(r['parent']):continue
 # Definitions referring to places or tail clauses cannot supply a new
 # nominal parent. Exact original claims remain in their frozen cohort.
 proof={'basis':'RECHECKED_OBJECT_KIND_HEAD_AND_INDEPENDENT_GENERIC_PARENT','original_parent_uid':r['parent'],'original_head':head,'object_kind_head':object_kind_head(head),'original_claim_sha256':hashlib.sha256(json.dumps(r,ensure_ascii=False,sort_keys=True).encode()).hexdigest(),'license':r['proof'].get('license','Original source attribution retained')}
 source='Rechecked independent object-kind definitions';common={'source':source,'uri':r['uri'],'proof':proof};found=False
 if r['relation']=='IS_A':
  for e in c.execute("SELECT id FROM edges WHERE child_uid=? AND parent_uid=? AND source=? AND layer='v1.8-hierarchy-review' AND relation='IS_A' AND status='ACTIVE'",(r['uid'],r['parent'],r['source'])):
   repairs.append({'op':'withdraw_edge','uid':r['uid'],'parent':r['parent'],'edge_id':e['id'],**common});found=True
 else:
  for e in c.execute("SELECT id FROM entity_relations WHERE subject_uid=? AND object_uid=? AND relation=? AND source=? AND status='ACTIVE'",(r['uid'],r['parent'],r['relation'],r['source'])):
   repairs.append({'op':'withdraw_typed','uid':r['uid'],'relation_id':e['id'],**common});found=True
 if not found:continue
 counts['superseded_lexical_claims']+=1;affected.add((r['uid'],r['parent']))
 if parent and node(parent)['component_id']!=node(r['uid'])['component_id'] and k.artifact_type(parent):
  proof={**proof,'parent_definition':node(parent)['description'],'verified_parent_uid':parent,'native_record_sha256':r['proof']['native_record_sha256']}
  relation={'CLASS':'IS_A','MODEL':'DESIGN_TYPE_OF','MODEL_FAMILY':'DESIGN_TYPE_OF'}[node(r['uid'])['role']]
  repairs.append({'op':'link','uid':r['uid'],'parent':parent,'relation':relation,**{**common,'proof':proof}});counts['verified_replacement_claims']+=1
# Restore old source admission only where the withdrawn lexical claim was the
# recorded reason to omit that broad edge. Other professional refinements stay.
restored=set()
for r in records:
 if r['op']!='withdraw_edge':continue
 replacement=r['proof'].get('replacement_parent')
 if (r['uid'],replacement) not in affected or r['edge_id'] in restored:continue
 current=c.execute('SELECT status,data FROM edges WHERE id=?',(r['edge_id'],)).fetchone()
 if not current or current['status']!='HIERARCHY_SUPERSEDED':continue
 disposition=json.loads(current['data']).get('hierarchy_disposition',{})
 if disposition.get('replacement_parent')!=replacement:continue
 repairs.append({'op':'restore_edge','uid':r['uid'],'parent':r['parent'],'edge_id':r['edge_id'],'source':'Source admission retained after lexical-parent review','uri':r['uri'],'proof':{'basis':'ORIGINAL_ADMISSION_RESTORED_AFTER_UNSUPPORTED_LEXICAL_PARENT','unreliable_replacement_parent':replacement,'license':'Original source assertion and terms retained'}});restored.add(r['edge_id']);counts['original_source_edges_restored']+=1
repairs=list({json.dumps(r,ensure_ascii=False,sort_keys=True):r for r in repairs}.values());path=O/'hierarchy_contract_repairs.jsonl'
with path.open('w') as f:
 for r in repairs:f.write(json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n')
(O/'hierarchy_contract_repairs_summary.json').write_text(json.dumps({'records':len(repairs),'counts':dict(counts),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()},indent=2)+'\n');print('COMPLETE',len(repairs),dict(counts),flush=True)
