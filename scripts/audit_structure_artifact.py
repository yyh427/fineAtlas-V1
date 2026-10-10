#!/usr/bin/env python3
"""Bind complete integrity and frozen inputs/code to the actual structural file."""
from __future__ import annotations

if not __debug__:
    raise RuntimeError("Optimized Python is forbidden for mandatory structural checks")

import argparse
import datetime
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from build_structure_candidate import build_fingerprints
from promote_stable_candidate import canonical_hash, digest_file


def audit(database, inputs, output, integrity=False):
    started=time.monotonic();before=database.stat()
    with sqlite3.connect(database.as_uri()+'?mode=ro&immutable=1',uri=True) as c:
        c.execute('PRAGMA temp_store=MEMORY');c.execute('PRAGMA cache_size=-1048576')
        meta={key:json.loads(value) for key,value in c.execute('SELECT * FROM metadata')}
        freeze=meta['structure_frozen_build_manifest']
        inventory={key:freeze[key] for key in ('inputs','code','packaging')}
        assert inventory==build_fingerprints(inputs),'Actual full input/code inventory differs from the frozen build'
        assert canonical_hash(freeze)==meta['browse_parent_revision'],'Frozen parent revision mismatch'
        assert meta['database_revision']==meta['browse_index_revision'],'Browse cache revision mismatch'
        assert all(meta.get(key) is True for key in ('unified_ready','usability_indexes_ready','browse_indexes_ready')),'Incomplete graphs or caches'
        assert json.loads((inputs/'legacy_policies.json').read_text())==meta['unified_reward_policies'],'Historical policies changed'
        assert json.loads((inputs/'reviewed_policies.json').read_text())==meta['reviewed_reward_policies_v1'],'Original reviewed policies changed'
        resolution_path=inputs/'reviewed_resolution_policies.json'
        resolved=json.loads(resolution_path.read_text()) if resolution_path.exists() else meta['reviewed_reward_policies_v1']
        assert resolved==meta['reviewed_reward_policies'],'Rank resolution policies changed'
        assert json.loads((inputs/'review_release.json').read_text())['version']==meta['release'],'Release input mismatch'
        assert meta['default_relation_view']=='unified' and set(meta['supported_relation_views'])=={'strict','taxonomy','membership','unified'}
        tables=[r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        check=[r[0] for r in c.execute('PRAGMA integrity_check')] if integrity else None
        if integrity:assert check==['ok'],check
    sha=digest_file(database) if integrity else None
    after=database.stat()
    unchanged=(before.st_size,before.st_mtime_ns,before.st_ino)==(after.st_size,after.st_mtime_ns,after.st_ino)
    assert unchanged,'Database changed during verification'
    result={'pass':True,'complete':True,'database':str(database),'database_revision':meta['database_revision'],
            'release':meta['release'],'sha256':sha,'bytes':after.st_size,
            'integrity_check':check,'integrity_pass':check==['ok'] if integrity else None,
            'file_unchanged_during_checks':unchanged,'all_frozen_inputs_and_recipes_checked':True,
            'logical_table_inventory':tables,'table_count':len(tables),
            'seconds':time.monotonic()-started,'ended_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('pass','integrity_pass','release','table_count','seconds')}),flush=True)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('database','inputs','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--integrity',action='store_true')
    a=p.parse_args();audit(a.database.resolve(),a.inputs.resolve(),a.output.resolve(),a.integrity)
