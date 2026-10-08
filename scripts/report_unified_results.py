#!/usr/bin/env python3
import argparse,csv,gzip,json,pathlib,sqlite3,sys
parser=argparse.ArgumentParser(description='Compile completed unified acceptance checkpoints without hiding unresolved records')
parser.add_argument('--reports',type=pathlib.Path,required=True)
parser.add_argument('--output',type=pathlib.Path,required=True)
parser.add_argument('--workspace',type=pathlib.Path,required=True)
a=parser.parse_args();reports=a.reports.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True);root=a.workspace.resolve()
def load(p):return json.loads(p.read_text())
def dump(name,x):(out/name).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
domains=load(reports/'domains/domains.json');labels=load(reports/'labels/label_summary.json');pairs=load(reports/'labels/pair_summary.json')
structure=load(reports/'structure/structure.json');retention=load(reports/'preservation/preservation.json');nonfocus=load(reports/'nonfocus/nonfocus_summary.json')
browsing=load(reports/'browse/summary.json');cycles=load(reports/'cycles.json');contracts=load(reports/'contracts.json');cli=load(reports/'cli/summary.json')
# Preserve counts and explicit unresolved objects; remove host-specific paths.
def portable(x):
 if isinstance(x,dict):return {k:portable(v) for k,v in x.items()}
 if isinstance(x,list):return [portable(v) for v in x]
 if isinstance(x,str) and x.startswith(str(root)):return '<local-workspace>/'+x[len(str(root))+1:]
 return x
peer_checks={}
for view in labels:
 rows=load(reports/('labels/'+view+'_labels.json'))
 peer_checks[view]={'peer_representations_checked':sum(len(r['peer_states']) for r in rows),
  'peer_internal_path_state_mismatches':sum(p['path_status']!=p['status']['path_status'] for r in rows for p in r['peer_states']),
  'peer_vs_target_status_differences':sum(p['path_status']!=r['path']['status'] for r in rows for p in r['peer_states'])}
summary={'schema':'FINEATLAS_UNIFIED_ACCEPTANCE_V1','release':'v1.10.0-unified-review',
 'domains':{'actual':len(domains),'public_contract_passes':sum(d['pass'] for d in domains)},
 'labels':labels,'identity_peer_checks':peer_checks,'pairs':pairs,'retention':retention,'nonfocus':nonfocus,'browsing':browsing,
 'cycles':cycles,'contracts':contracts,'real_cli_calls':cli['real_cli_calls'],
 'unrooted_active_classification_source_records':sum(r['records'] for r in structure['unrooted_classification_records']),
 'unrooted_navigation_source_records':structure['retained_unrooted_navigation_source_uids'],
 'universal_all_active_source_navigation_complete':structure['universal_all_active_source_navigation_complete'],
 'identity_role_conflict_groups':len(structure['identity_role_conflicts']),
 'all_source_edges_independently_semantically_certified':False,'images_or_visual_models_run':False}
dump('unified_validation.json',portable(summary));dump('unified_structure.json',portable(structure))
compact_domains=portable(domains)
for d in compact_domains:
 for r in d['roots']:
  r['path']=[{k:n[k] for k in ('uid','label','parent_uid','parent_label','source','node_kind','rank','edge') if k in n} for n in r['path']]
dump('unified_domains.json',compact_domains)
for name,path in [('unified_cub_examples.json',reports/'labels/cub_examples.json'),('unified_performance.json',reports/'browse/performance.json'),('unified_branch_details.json',reports/'browse/branches.json'),('unified_nonfocus_summary.json',reports/'nonfocus/nonfocus_summary.json'),('unified_source_corrections.json',reports/'preservation/corrected_root_relations.json')]:dump(name,portable(load(path)))
with (out/'unified_domains.csv').open('w',newline='') as stream:
 w=csv.writer(stream);w.writerow(['domain','entry','native_root','WordNet_anchor','synset','definition','relation','selection_basis','path_status','public_contract_pass','member_identities','root_to_native_uid_path'])
 for d in domains:
  total=sum(m['identities'] for m in d['member_census'])
  for r in d['roots']:w.writerow([d['domain'],d['entry_uid'],r['native_root_uid'],r['wordnet_anchor_uid'],r['synset_id'],r['definition'],r['attachment_relation'],r['basis'],r['status'],d['pass'],total,' -> '.join(([r['path'][0]['parent_uid']] if r['path'] and r['path'][0].get('parent_uid') else [])+[n['uid'] for n in r['path']])])
with (out/'unified_labels.csv').open('w',newline='') as stream:
 w=csv.writer(stream);w.writerow(['view','dataset','class_id','label','UID','source','role','stored_identity_claim','current_identity_verified','root_reachable','path_status','path_state_agree','task_usable','mapping_review'])
 for view in labels:
  for r in load(reports/('labels/'+view+'_labels.json')):w.writerow([view,r['dataset'],r['class_id'],r['label'],r['uid'],r['source'],r['role'],r['stored_identity_claim_verified'],r['identity_verified'],r['state']['root_reachable'],r['path']['status'],r['consistent'],r['task_admission']['usable'],r['mapping_review']])
with (out/'unified_pairs.jsonl.gz').open('wb') as f:
 with gzip.GzipFile(filename='',mode='wb',fileobj=f,mtime=0) as zipped:
  for ds in pairs:
   for line in (reports/'labels/training'/ds/'pairs.jsonl').open('rb'):zipped.write(line)
with (out/'unified_unrooted_navigation.csv.gz').open('wb') as f:
 with gzip.GzipFile(filename='',mode='wb',fileobj=f,mtime=0) as zipped:zipped.write((reports/'structure/unrooted_navigation_source_uids.csv').read_bytes())
print(json.dumps({'domains':summary['domains'],'all_pair_outputs':sum(v['pairs'] for v in pairs.values()),'unresolved_navigation':summary['unrooted_navigation_source_records']}))
