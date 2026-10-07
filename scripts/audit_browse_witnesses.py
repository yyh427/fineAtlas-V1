#!/usr/bin/env python3
"""Check staged finer-route witnesses against immutable original source records."""
import argparse
import json
from pathlib import Path
import sqlite3
import time


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline',type=Path,required=True);p.add_argument('--staging',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();started=time.monotonic()
    c=sqlite3.connect(a.staging.resolve().as_uri()+'?mode=ro&immutable=1',uri=True);c.row_factory=sqlite3.Row
    c.execute('ATTACH DATABASE ? AS native',(a.baseline.resolve().as_uri()+'?mode=ro&immutable=1',))
    c.execute('PRAGMA native.cache_size=-1000000')
    revision=json.loads(c.execute("SELECT value FROM native.metadata WHERE key='database_revision'").fetchone()[0])
    bound=json.loads(c.execute("SELECT value FROM main.metadata WHERE key='browse_source_revision'").fetchone()[0])
    assert revision==bound
    wrong_nodes=c.execute('''SELECT count(*) FROM browse_nodes b LEFT JOIN native.nodes n ON n.uid=b.uid
      WHERE n.uid IS NULL OR b.component_id IS NOT n.component_id
        OR b.source IS NOT coalesce(n.source,'') OR n.visibility<>'ACTIVE' ''').fetchone()[0]
    assert wrong_nodes==0,('derived identity or source mismatch',wrong_nodes)
    print('ALL INDEXED SOURCE IDENTITIES MATCH',flush=True)
    preferences={tuple(r[k] for k in ('view','parent_component','child_component','role','relation')):dict(r)
                 for r in c.execute('SELECT * FROM browse_preferences')}
    edges={};expanded={}
    def edge(storage,rid):
        key=storage,rid
        if key in edges:return edges[key]
        table='edges' if storage=='edge' else 'entity_relations'
        row=c.execute('SELECT * FROM native.'+table+' WHERE id=?',(rid,)).fetchone()
        assert row and row['status'] in ('ACTIVE','TYPED_ACTIVE'),key
        child=row['child_uid'] if storage=='edge' else row['subject_uid']
        parent=row['parent_uid'] if storage=='edge' else row['object_uid']
        cn=c.execute('SELECT component_id,role FROM browse_nodes WHERE uid=?',(child,)).fetchone()
        pn=c.execute('SELECT component_id FROM browse_nodes WHERE uid=?',(parent,)).fetchone()
        assert cn and pn,key
        edges[key]=(pn[0],cn[0],cn[1],row['relation']);return edges[key]
    def expand(key,stack=()):
        if key in expanded:return expanded[key]
        assert key not in stack,('witness dependency cycle',key)
        pref=preferences.get(key)
        if not pref:return [key]
        first=edge(pref['first_storage'],pref['first_record_id'])
        second=edge(pref['second_storage'],pref['second_record_id'])
        assert first[1]==key[2] and first[0]==second[1] and second[0]==key[1],key
        assert first[0]==pref['via_component'],key
        result=expand((key[0],*first),stack+(key,))+expand((key[0],*second),stack+(key,))
        assert result[0][2]==key[2] and result[-1][1]==key[1]
        assert all(result[i][1]==result[i+1][2] for i in range(len(result)-1))
        for link in result:
            assert link not in preferences
            assert c.execute('SELECT 1 FROM browse_links WHERE view=? AND parent_component=? AND child_component=? AND role=? AND relation=?',link).fetchone(),link
        expanded[key]=result;return result
    maximum=0
    for i,key in enumerate(preferences):
        maximum=max(maximum,len(expand(key)))
        if i and i%10000==0:print('SOURCE WITNESSES',i,flush=True)
    report={'all_pass':True,'verified_source_preferences':len(preferences),
            'affected_view_parent_pairs':len({key[:2] for key in preferences}),
            'maximum_surviving_witness_edges':maximum,'source_revision':revision,
            'index_identity_and_source_mismatches':wrong_nodes,
            'all_hidden_display_connections_have_surviving_native_routes':True,
            'full_candidate_core_record_comparison_still_required':True,'seconds':time.monotonic()-started}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report),flush=True);c.close()


if __name__=='__main__':main()
