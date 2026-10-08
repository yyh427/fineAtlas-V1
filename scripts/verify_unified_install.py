#!/usr/bin/env python3
"""Verify a published install using its frozen SDK hashes and real public APIs.

Run download_single first: its streamed extraction checks the full file SHA and
size. This command avoids another redundant 64 GB scan, then independently
checks frozen code, graph/index/default-view consistency and actual queries.
"""
import argparse,collections,hashlib,json,pathlib,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'src'))
import fineatlas
from fineatlas import FineAtlas
def validate_acceptance_revision(expected, manifest):
 """A release name and aggregate counts cannot identify the accepted snapshot."""
 accepted=expected.get('database_revision');published=manifest.get('database_revision')
 assert isinstance(accepted,str) and accepted, 'Expected validation lacks its accepted database revision'
 assert isinstance(published,str) and published, 'Published manifest lacks its database revision'
 assert accepted==published, 'Acceptance revision differs from the published database revision'
 assert expected.get('release')==manifest.get('release'), 'Acceptance belongs to another release'
 if 'database_sha256' in expected:
  assert expected['database_sha256']==manifest.get('database',{}).get('sha256'), 'Acceptance file hash differs from the published artifact'
 return accepted


def validate_domain_page(page, view, revision, limit):
 """Check the documented keyset page schema; success need not carry status."""
 assert page.get('status') in (None, 'OK', 'EMPTY'), page
 assert all(k in page for k in ('items','next_cursor','has_more','relation_view','database_revision'))
 assert isinstance(page['items'], list) and len(page['items']) <= limit
 assert type(page['has_more']) is bool
 assert page['relation_view'] == view and page['database_revision'] == revision
 assert (isinstance(page['next_cursor'], str) and bool(page['next_cursor'])) if page['has_more'] else page['next_cursor'] is None
 if page.get('status') == 'EMPTY': assert not page['items'] and not page['has_more']
 return {'public_page_schema': 'KEYSET_PAGE_V1', 'public_page_status': page.get('status'),
         'public_page_items': len(page['items']), 'public_page_has_more': page['has_more']}


def validate_domain_inventory(domains, expected, manifest):
 """Require the actual release's complete accepted inventory, not an old constant."""
 assert expected['release'] == manifest['release'], 'Acceptance belongs to another release'
 census=expected['domains'];count=census['actual']
 assert type(count) is int and count > 0 and census['public_contract_passes'] == count
 assert len(domains) == count, 'Published domain count differs from accepted inventory'
 names=[d['domain'] for d in domains]
 assert len(names) == len(set(names)), 'Duplicate canonical domain'
 if 'domain_count' in manifest: assert count == manifest['domain_count']
 if 'domain_inventory' in manifest:
  assert 'domain_inventory' in expected and manifest['domain_inventory']==expected['domain_inventory'], 'Manifest and acceptance scopes differ'
 if 'domain_inventory' in expected:
  inventory=expected['domain_inventory']
  assert set(names) == set(inventory), 'Published domains differ from frozen acceptance'
  for d in domains:
   assert set(d['root_uids']) == set(inventory[d['domain']]), d['domain']
 return count


def main():
 p=argparse.ArgumentParser(description=__doc__)
 for name in ('database','manifest','expected-validation','output'):p.add_argument('--'+name,type=pathlib.Path,required=True)
 a=p.parse_args();m=json.loads(a.manifest.read_text());expected=json.loads(a.expected_validation.read_text())
 validate_acceptance_revision(expected,m)
 a.output.mkdir(parents=True,exist_ok=True)
 receipt=a.database.parent/'single_database.json'
 assert receipt.exists() and json.loads(receipt.read_text())==m,'Use the completed verified installer and its actual receipt'
 assert a.database.stat().st_size==m['database']['bytes']
 with FineAtlas(a.database) as tree:
  assert tree.relation_view=='unified' and tree._revision==m['database_revision']
  meta=tree.metadata
  assert all(meta[k] for k in ['unified_ready','usability_indexes_ready','browse_indexes_ready'])
  assert meta['browse_index_revision']==tree._revision
  code=meta['unified_frozen_build_manifest']['code'];source=pathlib.Path(fineatlas.__file__).resolve().parent
  for name,digest in code.items():assert hashlib.sha256((source/pathlib.Path(name).name).read_bytes()).hexdigest()==digest,name
  domains=tree.domains();validate_domain_inventory(domains,expected,m)
  domain_checks=[]
  for d in domains:
   entry=tree.domain(d['domain']);checks=[tree.path_result(uid)['status'] in ('ROOT','CONNECTED') for uid in entry['root_uids']]
   page=tree.domain_page(d['domain'],limit=1)
   assert checks and all(checks),d['domain']
   page_check=validate_domain_page(page,tree.relation_view,tree._revision,1)
   domain_checks.append({'domain':d['domain'],'native_roots':entry['root_uids'],'root_paths_pass':all(checks),**page_check})
  pairs={}
  for dataset,x in expected['pairs'].items():
   index=tree.relation_reward_index(dataset);counts=collections.Counter();n=0
   for result in index.pairs():
    counts[result['status']]+=1;n+=1
    if not result['applicable']:assert result['distance'] is None
   assert n==x['pairs'] and dict(counts)==x['pair_statuses'],dataset
   pairs[dataset]={'pairs':n,'pair_statuses':dict(counts),'equal_published_validation':True}
  cub={'task_path':tree.task_path('cub200','1'),'training_pair':tree.relation_reward_index('cub200').query('1','2')}
  (a.output/'cub_public_example.json').write_text(json.dumps(cub,ensure_ascii=False,indent=2)+'\n')
 labels={}
 for view,x in expected['labels'].items():
  with FineAtlas(a.database,relation_view=view) as tree:
   totals=collections.Counter()
   for dataset in expected['pairs']:
    for t in tree.task_labels(dataset):
     state=tree.connection_status(t['target_uid']);path=tree.path_result(t['target_uid'])
     assert state['path_status']==path['status'],(dataset,t['class_id'],view)
     totals['labels']+=1;totals['stored_identity_claim_verified']+=t['stored_identity_claim_verified'];totals['identity_verified']+=t['identity_verified']
     totals['root_reachable']+=state['root_reachable'];totals['path_state_consistent']+=1;totals['hierarchy_admitted']+=t['task_admission']['usable']
   actual={k:totals[k] for k in x};assert actual==x,(view,actual,x);labels[view]=actual
 result={'all_pass':True,'release':m['release'],'database_revision':m['database_revision'],'database_sha256':m['database']['sha256'],
  'full_hash_verification_stage':'Completed download_single streamed SHA-256/size/exact-revision verification; byte-identical receipt required',
  'default_view':'unified','matching_embedded_browse_index':True,'sdk_module':str(source),'frozen_sdk_files_checked':len(code),
  'domains':domain_checks,'labels':labels,'pairs':pairs,'unresolved_source_evidence_is_not_certified_by_this_install_test':True,'images_or_models_run':False}
 (a.output/'external_validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'all_pass':True,'domains':len(domain_checks),'labels_per_view':{v:x['labels'] for v,x in labels.items()},'pairs':sum(x['pairs'] for x in pairs.values())}))


if __name__=='__main__':main()
