#!/usr/bin/env python3
"""Append refined decisions without changing any prior frozen cohort."""
import argparse,hashlib,json,re,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from fineatlas.engineering_roles import definition_head
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--inputs',type=Path,required=True);p.add_argument('--inventory',type=Path,required=True);p.add_argument('--proposed',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--prior-cohorts',nargs='+',default=['hierarchy_shape_repairs.jsonl']);p.add_argument('--cohort-name',default='hierarchy_shape_completion.jsonl',choices=['hierarchy_shape_completion.jsonl','hierarchy_subject_repairs.jsonl','hierarchy_admission_reviews.jsonl']);a=p.parse_args()
def key(r):return hashlib.sha256(json.dumps(r,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
old=[json.loads(l) for name in a.prior_cohorts for l in (a.inputs/name).open()]
new=[json.loads(l) for l in a.proposed.open()];new_records=new;oldkeys={key(r) for r in old}
records=[r for r in new if key(r) not in oldkeys]
inventory={r['uid']:r for r in map(json.loads,a.inventory.open())};base={u:r['role'] for u,r in inventory.items()};roles={**base,**{r['uid']:r['role'] for r in new if r['op']=='role'}};roles.update({r['uid']:'UNKNOWN' for r in new if r['op']=='source_review'})
oldroles=dict(base)
for r in old:
 if r['op']=='role':oldroles[r['uid']]=r['role']
 elif r['op']=='source_review':oldroles[r['uid']]='UNKNOWN'
explicit={r['uid'] for r in new if r['op'] in {'role','source_review'}}
for u,role in list(roles.items()):
 if role==oldroles.get(u) or u in explicit:continue
 n=inventory[u];raw=json.loads(n['data']);e=raw.get('evidence_record',{})
 text=raw.get('definition') or raw.get('intro') or e.get('wikipedia_intro') or ''
 head=definition_head(text,n['label'])
 generic=role=='CLASS' and bool(re.search(r'\b(?:body[ -]style|body type|size class|vehicle classification|standards?|protocols?)\b',head,re.I))
 if generic:
  proof={'basis':'INDEPENDENT_GENERIC_KIND_DEFINITION_CORRECTS_EARLIER_DESIGN_VARIANT_HINT','native_record_sha256':hashlib.sha256(n['data'].encode()).hexdigest(),'source_statement':text,'subject_kind_head':head,'previous_frozen_role':oldroles[u],'license':'Retained independent encyclopedia definition CC BY-SA 4.0; native source attribution preserved'}
  records.append({'op':'role','uid':u,'role':'CLASS','source':'Independent generic kind completion contract','uri':raw.get('source_uri') or 'https://www.wikidata.org/wiki/'+u.split(':')[-1],'proof':proof})
 else:
  # An absent newer proposal is not a decision to erase a previously
  # evidenced role. Only explicit new evidence can change that role.
  roles[u]=oldroles[u]
changed={u for u,v in roles.items() if v!=oldroles.get(u,'CLASS')}
for r in old:
 if r['op']!='link' or not {r['uid'],r['parent']} & changed:continue
 c=roles.get(r['uid'],'CLASS');d=roles.get(r['parent'],'CLASS');rel=r['relation']
 valid= rel=='IS_A' and c==d=='CLASS' or rel=='DESIGN_TYPE_OF' and c in {'MODEL','MODEL_FAMILY'} and d=='CLASS' or rel=='NATIVE_DESIGN_PARENT' and c in {'MODEL','MODEL_FAMILY'} and d in {'MODEL','MODEL_FAMILY'} or rel=='INSTANCE_OF' and c=='INSTANCE' and d in {'CLASS','MODEL','MODEL_FAMILY'}
 if valid:continue
 proof={'basis':'LATER_CORROBORATED_GRAIN_SUPERSEDES_PRIOR_FROZEN_LINK','original_frozen_decision_id':key(r),'original_frozen_source':r['source'],'final_endpoint_roles':[c,d],'license':'Prior frozen evidence, declarations and source attribution retained'}
 records.append({'op':'withdraw_frozen_link','uid':r['uid'],'parent':r['parent'],'relation':rel,'source':'Engineering shape completion contract','uri':r['uri'],'proof':proof})
 replacement='NATIVE_DESIGN_PARENT' if c in {'MODEL','MODEL_FAMILY'} and d in {'MODEL','MODEL_FAMILY'} else 'DESIGN_TYPE_OF' if c in {'MODEL','MODEL_FAMILY'} and d=='CLASS' else 'INSTANCE_OF' if c=='INSTANCE' and d in {'CLASS','MODEL','MODEL_FAMILY'} else None
 if replacement and not any(x['op']=='link' and x['uid']==r['uid'] and x['relation']==replacement for x in new_records):
  records.append({'op':'link','uid':r['uid'],'parent':r['parent'],'relation':replacement,'source':'Engineering shape completion contract','uri':r['uri'],'proof':{**proof,'basis':'PRIOR_FROZEN_SUBJECT_KIND_RETAINED_WITH_CORRECTED_GRAIN'}})
# A purpose clause in a prior genus must not keep a generated false parent.
# This is separate from endpoint grain; migration verifies the literal genus
# and requires the narrower replacement assertion to survive.
for old_link in old:
 if old_link['op']!='link' or old_link['relation']!='IS_A' or old_link['uid'] in changed:continue
 old_head=old_link.get('proof',{}).get('subject_kind_head','')
 if not re.search(r'\b(?:enabling|allowing|permitting|requiring|carrying|transporting|housing|comprising|consisting|powering)\b',old_head,re.I):continue
 choices=[r for r in new if r['op']=='link' and r['uid']==old_link['uid'] and r['relation']=='IS_A' and r['parent']!=old_link['parent'] and r.get('proof',{}).get('subject_kind_head')]
 for replacement in choices:
  head=replacement['proof']['subject_kind_head']
  if head==old_head or not old_head.startswith(head+' '):continue
  proof={**replacement['proof'],'basis':'VERIFIED_SUBJECT_GENUS_SUPERSEDES_PRIOR_FROZEN_LINK','original_frozen_decision_id':key(old_link),'original_frozen_source':old_link['source'],'replacement_parent':replacement['parent']}
  records.append({'op':'withdraw_frozen_link','uid':old_link['uid'],'parent':old_link['parent'],'relation':'IS_A','source':'Engineering subject genus completion contract','uri':replacement['uri'],'proof':proof});break
a.output.mkdir(parents=True,exist_ok=True);path=a.output/a.cohort_name;path.write_text(''.join(json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n' for r in records))
summary={'additional_decisions':len(records),'prior_shape_sha256':hashlib.sha256((a.inputs/'hierarchy_shape_repairs.jsonl').read_bytes()).hexdigest(),'changed_role_uids':len(changed),'superseded_generated_links':sum(r['op']=='withdraw_frozen_link' for r in records),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()};(a.output/'shape_completion_summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary),flush=True)
