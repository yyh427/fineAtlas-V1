#!/usr/bin/env python3
"""Compare full source records and prove every preferred route retains reachability."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from fineatlas import FineAtlas


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline',type=Path,required=True)
    p.add_argument('--database',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(a.baseline.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
    c.execute('PRAGMA cache_size=-1000000');c.execute('PRAGMA temp_store=MEMORY')
    c.execute('ATTACH DATABASE ? AS candidate',(a.database.resolve().as_uri()+'?mode=ro&immutable=1',))
    quote=lambda x:'"'+x.replace('"','""')+'"'
    results={};start=time.monotonic()
    tables=[r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'alias_search%' AND name NOT LIKE 'browse_%' ORDER BY name")]
    for table in tables:
        if table=='metadata':continue
        cols=list(c.execute('PRAGMA table_info('+quote(table)+')'))
        names=[x[1] for x in cols];keys=[x[1] for x in sorted(cols,key=lambda x:x[5]) if x[5]]
        counts=[c.execute('SELECT count(*) FROM '+prefix+quote(table)).fetchone()[0] for prefix in ['', 'candidate.']]
        if keys:
            join=' AND '.join('a.'+quote(k)+' IS b.'+quote(k) for k in keys)
            different=' OR '.join('a.'+quote(k)+' IS NOT b.'+quote(k) for k in names if k not in keys) or '0'
            sql='SELECT count(*) FROM '+quote(table)+' a LEFT JOIN candidate.'+quote(table)+' b ON '+join+' WHERE b.'+quote(keys[0])+' IS NULL OR ('+different+')'
        else:
            different=' OR '.join('a.'+quote(k)+' IS NOT b.'+quote(k) for k in names)
            sql='SELECT count(*) FROM '+quote(table)+' a LEFT JOIN candidate.'+quote(table)+' b ON a.rowid=b.rowid WHERE b.rowid IS NULL OR ('+different+')'
        mismatch=c.execute(sql).fetchone()[0]
        results[table]={'counts':counts,'different_rows':mismatch,'pass':counts[0]==counts[1] and mismatch==0}
        (a.output/'core_records.json').write_text(json.dumps(results,indent=2)+'\n')
        print('CORE',table,results[table],flush=True)
        assert results[table]['pass'],table
    changed={}
    for key,value in c.execute('SELECT key,value FROM metadata'):
        other=c.execute('SELECT value FROM candidate.metadata WHERE key=?',(key,)).fetchone()
        if not other or other[0]!=value:changed[key]={'baseline':value,'candidate':other[0] if other else None}
    assert set(changed)<={'release','database_revision'},changed
    added=[r[0] for r in c.execute('SELECT key FROM candidate.metadata WHERE key NOT IN (SELECT key FROM metadata)')]
    assert all(k.startswith('browse_') for k in added),added
    c.close()
    with FineAtlas(a.database) as tree:
        con=tree.con
        rows=con.execute('SELECT * FROM browse_preferences ORDER BY view,parent_component,child_component,role,relation').fetchall()
        preferences={(r['view'],r['parent_component'],r['child_component'],r['role'],r['relation']):dict(r) for r in rows}
        edge_cache={};expanded={};maximum=0
        def edge(storage,rid):
            key=(storage,rid)
            if key not in edge_cache:
                table='edges' if storage=='edge' else 'entity_relations'
                native=con.execute('SELECT * FROM '+table+' WHERE id=?',(rid,)).fetchone()
                assert native is not None and native['status'] in ('ACTIVE','TYPED_ACTIVE'),key
                child=native['child_uid'] if storage=='edge' else native['subject_uid']
                parent=native['parent_uid'] if storage=='edge' else native['object_uid']
                cn=con.execute('SELECT * FROM browse_nodes WHERE uid=?',(child,)).fetchone()
                pn=con.execute('SELECT * FROM browse_nodes WHERE uid=?',(parent,)).fetchone()
                assert cn and pn,key
                edge_cache[key]=(pn['component_id'],cn['component_id'],cn['role'],native['relation'])
            return edge_cache[key]
        def expand(key,stack=()):
            if key in expanded:return expanded[key]
            assert key not in stack,('Preference cycle',key)
            pref=preferences.get(key)
            if not pref:return [key]
            first=edge(pref['first_storage'],pref['first_record_id'])
            second=edge(pref['second_storage'],pref['second_record_id'])
            assert first[1]==key[2] and first[0]==second[1] and second[0]==key[1],key
            assert first[0]==pref['via_component'],key
            value=expand((key[0],*first),stack+(key,))+expand((key[0],*second),stack+(key,))
            assert value[0][2]==key[2] and value[-1][1]==key[1],key
            assert all(value[i][1]==value[i+1][2] for i in range(len(value)-1)),key
            for link in value:
                assert con.execute('SELECT 1 FROM browse_links WHERE view=? AND parent_component=? AND child_component=? AND role=? AND relation=?',link).fetchone(),link
                assert link not in preferences,link
            expanded[key]=value;return value
        for i,key in enumerate(preferences):
            route=expand(key);maximum=max(maximum,len(route))
            if i and i%10000==0:print('PREFERENCE WITNESSES',i,flush=True)
        # This is a graph-wide set-preservation proof, not a count comparison:
        # every omitted display arc has a surviving endpoint-identical path;
        # the complete source graph and identity partition were compared above.
        affected=len({(r['view'],r['parent_component']) for r in rows})
        report={'all_pass':True,'core_tables_exactly_equal':results,
                'allowed_metadata_changes':changed,'added_metadata_keys':added,
                'preferred_connections':len(rows),'affected_view_parent_pairs':affected,
                'all_preference_witnesses_survive_default_presentation':True,
                'full_descendant_identity_sets_preserved_for_every_affected_parent':True,
                'preservation_basis':'Exact graph/node/identity row comparison plus replacement of each omitted display arc by a verified surviving path between the same identity endpoints; therefore complete and preferred transitive reachability sets agree',
                'maximum_expanded_witness_edges':maximum,'seconds':time.monotonic()-start}
        (a.output/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
        print('FULL PRESERVATION AND PREFERENCE WITNESSES PASS',len(rows),affected,flush=True)

if __name__=='__main__':main()
