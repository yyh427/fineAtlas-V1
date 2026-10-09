#!/usr/bin/env python3
"""Verify a published install using its frozen SDK hashes and real public APIs.

Run download_single first: its streamed extraction checks the full file SHA and
size. This command avoids another redundant 64 GB scan, then independently
checks frozen code, graph/index/default-view consistency and actual queries.
"""
import argparse,collections,hashlib,json,pathlib,sys
import fineatlas
from fineatlas import FineAtlas
ROOT=pathlib.Path(__file__).resolve().parents[1]


def validate_runtime_install(metadata, manifest, sdk):
 """Bind the actual installed SDK to the exact release, view and graph caches."""
 assert sdk.__version__ == manifest.get('sdk_version'), 'Installed SDK version differs from release manifest'
 assert metadata.get('schema') == 'FINEATLAS_SINGLE_DB_V1', 'Unsupported installed database schema'
 assert metadata.get('release') == manifest.get('release'), 'Database release differs from manifest'
 assert metadata.get('database_revision') == manifest.get('database_revision'), 'Database revision differs from manifest'
 assert metadata.get('default_relation_view') == manifest.get('default_relation_view') == 'unified', 'Default view differs from manifest'
 assert set(metadata.get('supported_relation_views',[])) == set(manifest.get('supported_relation_views',[])) == {'strict','taxonomy','membership','unified'}, 'Supported views differ'
 assert all(metadata.get(k) is True for k in ['unified_ready','usability_indexes_ready','browse_indexes_ready']), 'Graph/caches are incomplete'
 assert metadata.get('browse_index_revision') == metadata['database_revision'], 'Stale browse index'
 source=pathlib.Path(sdk.__file__).resolve().parent
 code=metadata.get('unified_frozen_build_manifest',{}).get('code',{})
 assert code and 'src/fineatlas/__init__.py' in code, 'Missing frozen SDK manifest'
 for name,digest in code.items():
  relative=pathlib.Path(name)
  assert relative.parts[:2] == ('src','fineatlas') and len(relative.parts) == 3, 'Invalid frozen SDK path'
  assert hashlib.sha256((source/relative.name).read_bytes()).hexdigest() == digest, 'Installed SDK does not match frozen database: '+name
 return {'sdk_version':sdk.__version__,'sdk_module':str(source),'frozen_sdk_files_checked':len(code)}


def validate_installed_sdk(sdk, prefix=sys.prefix):
 source=pathlib.Path(sdk.__file__).resolve()
 assert source.is_relative_to(pathlib.Path(prefix).resolve()) and 'site-packages' in source.parts, 'Use the pip-installed SDK in the active environment, not checkout/src'
 return source


def validate_install_receipt(database, manifest):
 receipt=database.parent/'single_database.json'
 assert receipt.exists() and json.loads(receipt.read_text()) == manifest, 'Use the completed verified installer and its actual receipt'
 assert database.stat().st_size == manifest['database']['bytes'], 'Installed database size differs from manifest'
 for suffix in ('-wal','-journal'):
  sidecar=pathlib.Path(str(database)+suffix)
  assert not sidecar.exists() or sidecar.stat().st_size == 0, 'Installed database has a live SQLite sidecar'

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
 for name in ('database','output'):p.add_argument('--'+name,type=pathlib.Path,required=True)
 p.add_argument('--manifest',type=pathlib.Path,default=ROOT/'unified_data.json')
 p.add_argument('--expected-validation',type=pathlib.Path,default=ROOT/'docs/unified_validation.json')
 a=p.parse_args();m=json.loads(a.manifest.read_text());expected=json.loads(a.expected_validation.read_text())
 validate_acceptance_revision(expected,m)
 validate_installed_sdk(fineatlas)
 a.output.mkdir(parents=True,exist_ok=True)
 validate_install_receipt(a.database,m)
 with FineAtlas(a.database) as tree:
  assert tree.relation_view=='unified' and tree._revision==m['database_revision']
  meta=tree.metadata
  installed=validate_runtime_install(meta,m,fineatlas)
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
  'default_view':'unified','matching_embedded_browse_index':True,**installed,
  'domains':domain_checks,'labels':labels,'pairs':pairs,'unresolved_source_evidence_is_not_certified_by_this_install_test':True,'images_or_models_run':False}
 (a.output/'external_validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'all_pass':True,'domains':len(domain_checks),'labels_per_view':{v:x['labels'] for v,x in labels.items()},'pairs':sum(x['pairs'] for x in pairs.values())}))


if __name__=='__main__':main()
