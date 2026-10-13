"""Exercise only this round's inverse writes, then discard the transaction."""
import argparse
import json
from pathlib import Path
import sqlite3
from fineatlas.repair_candidate import _rollback_package


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);args=p.parse_args();r=args.root
    target=json.loads((r/'checkpoints/current.json').read_text())['baseline']['base_revision']
    c=sqlite3.connect(r/'artifacts/fineatlas.sqlite');c.row_factory=sqlite3.Row
    c.execute('PRAGMA cache_size=-65536');original=c.execute("SELECT value FROM metadata WHERE key='database_revision'").fetchone()[0]
    packages=[x[0] for x in c.execute("SELECT p.package_id FROM repair_packages p JOIN repair_changes ch USING(package_id) WHERE p.status='APPLIED' GROUP BY p.package_id ORDER BY max(ch.sequence) DESC")]
    new_nodes=[n['uid'] for n in json.loads((r/'inputs/source_graph_plan.json').read_text())['nodes']]
    old_counts={t:c.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ['native_classes','integrated_fg_objects','integrated_dataset_versions']}
    results=[]
    try:
        c.execute('BEGIN IMMEDIATE')
        for package in packages:
            if json.loads(c.execute("SELECT value FROM metadata WHERE key='database_revision'").fetchone()[0])==target:break
            results.append(_rollback_package(c,package))
        restored=json.loads(c.execute("SELECT value FROM metadata WHERE key='database_revision'").fetchone()[0])
        counts={t:c.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in old_counts}
        remaining=sum(c.execute('SELECT 1 FROM nodes WHERE uid=?',(u,)).fetchone() is not None for u in new_nodes)
        assert restored==target and counts==old_counts and remaining==0
        c.rollback()
        preserved=c.execute("SELECT value FROM metadata WHERE key='database_revision'").fetchone()[0]==original
        result={'passed':preserved,'packages':results,'restored_base_revision_in_transaction':restored,
                'restored_extension_and_native_counts':counts,'remaining_round_nodes':remaining,
                'candidate_revision_preserved':preserved,'inverse_writes_committed':False}
        (r/'reports/round_rollback_acceptance.json').write_text(json.dumps(result,indent=2));print(result)
    finally:c.rollback();c.close()


if __name__=='__main__':main()
