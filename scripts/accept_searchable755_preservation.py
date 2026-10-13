"""Read-only preservation, exact-parent and extension compatibility receipts."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from fineatlas import FineAtlas
from fineatlas.repair_candidate import CORE_COUNTS, canonical


def table_digest(con, table, columns, order):
    h = hashlib.sha256(); count = 0
    for row in con.execute('SELECT '+','.join(columns)+' FROM '+table+' ORDER BY '+order):
        h.update(canonical(list(row)).encode()); h.update(b'\n'); count += 1
    return {'rows': count, 'sha256': h.hexdigest()}


def main():
    p = argparse.ArgumentParser(); p.add_argument('--root', type=Path, required=True)
    p.add_argument('--baseline', type=Path, required=True); args = p.parse_args()
    r, b = args.root, args.baseline; errors = []; checks = {}
    with FineAtlas(b/'artifacts/fineatlas.sqlite', relation_view='unified') as old, FineAtlas(r/'artifacts/fineatlas.sqlite', relation_view='unified') as new:
        checks['tested_revision'] = new._revision
        # All core and extension source ranges/IDs/proofs remain unchanged.
        for table, cols, order in [
            ('native_classes', ['dataset','class_id','namespace','source_version','uid','label','raw_label','role','object_granularity','training_id_verified','proof'], 'dataset,class_id'),
            ('integrated_dataset_versions', ['dataset','source_version','payload'], 'dataset,source_version'),
            ('integrated_fg_objects', ['kind','key','payload','sha256'], 'kind,key')]:
            a, z = table_digest(old.con,table,cols,order), table_digest(new.con,table,cols,order)
            checks[table] = {'before': a, 'after': z, 'passed': a==z}
            if a != z: errors.append('Changed protected source table: '+table)
        checks['source_counts'] = dict(new.con.execute('SELECT dataset,count(*) FROM native_classes GROUP BY dataset').fetchall())
        checks['extension_counts'] = dict(new.con.execute('SELECT training_id_verified,count(*) FROM native_classes WHERE dataset NOT IN ('+','.join('?' for _ in CORE_COUNTS)+') GROUP BY training_id_verified', tuple(CORE_COUNTS)).fetchall())
        previous = json.loads((b/'reports/final_interface_acceptance.json').read_text())
        sentinels = []
        for uid, prior in previous['sentinels'].items():
            node = new.node(uid); contract = new.candidate_contract(uid)
            passed = bool(node and node['node_kind']==prior['role'] and node['visibility']==prior['visibility'])
            passed &= contract['native_answer_eligible']==prior['contract']['native_answer_eligible']
            sentinels.append({'uid':uid,'passed':passed,'contract':contract})
            if not passed: errors.append('Extension sentinel changed: '+uid)
        checks['seven_extension_probes'] = sentinels
        facts = []
        for item in json.loads((r/'reports/confirmed_dog_parent_evidence.json').read_text()):
            if item['status']!='GROUNDED_FULL_PARENT_SENSE_MATCH': continue
            target = old._presentation_identity(item['parent'])['key']
            prior_parents = list(old._scope_links(item['world_uid'], direction='parents'))
            equivalent_old = [e for e in prior_parents if old._presentation_identity(e['parent_uid'])['key']==target and e['relation']=='IS_A']
            facts.append({**item,'already_had_same_direct_strict_parent':bool(equivalent_old),
                          'previous_edge_ids':[e['id'] for e in equivalent_old]})
        checks['119_dog_parent_assertions'] = {'assertions':len(facts),
            'new_direct_component_parent_pairs':sum(not x['already_had_same_direct_strict_parent'] for x in facts),
            'repeated_source_support':sum(x['already_had_same_direct_strict_parent'] for x in facts),'items':facts}
    # Original DB stat and historical interfaces are compared with prior receipts.
    protected = json.loads((b/'reports/protected_baselines_acceptance.json').read_text())['checks']
    baseline = json.loads((r/'checkpoints/current.json').read_text())['baseline']
    protected.append({'kind':'previous_delivery','path':baseline['base_database'],'after':baseline['base_stat']})
    protections = []
    for prior in protected:
        path=Path(prior['path']); stat=path.stat()
        if 'sha256' in prior:
            actual=hashlib.sha256(path.read_bytes()).hexdigest();passed=actual==prior['sha256'];detail={'sha256':actual}
        else:
            detail={'size':stat.st_size,'mtime_ns':stat.st_mtime_ns,'inode':stat.st_ino};passed=detail==prior['after']
        protections.append({'kind':prior['kind'],'path':str(path),'passed':passed,**detail})
        if not passed: errors.append('Protected artifact changed: '+str(path))
    checks['protected_artifacts']=protections
    source_checks=[]
    for prior in json.loads((b/'reports/increment_source_file_checks.json').read_text())['files']:
        path=Path(prior['path']);h=hashlib.sha256()
        with path.open('rb') as f:
            for block in iter(lambda:f.read(1<<20),b''):h.update(block)
        passed=h.hexdigest()==prior['actual_sha256'];source_checks.append({'path':str(path),'passed':passed,'sha256':h.hexdigest()})
        if not passed:errors.append('Extension frozen source changed: '+str(path))
    checks['increment_original_file_checks']=source_checks
    checks.update(passed=not errors,errors=errors,scope='All retained source rows and integrated payloads; seven UID contracts; unchanged inputs; no visual or whole-world semantic claim')
    (r/'reports/preservation_and_increment_acceptance.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2))
    print(json.dumps({'passed':not errors,'errors':errors,'119_parent_summary':{k:v for k,v in checks['119_dog_parent_assertions'].items() if k!='items'}},ensure_ascii=False))
    if errors:raise SystemExit(1)


if __name__=='__main__':main()
