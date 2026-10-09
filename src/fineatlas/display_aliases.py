"""Editorial navigation names have no identity or taxonomy effect."""
from __future__ import annotations
from collections import Counter
import json
from ._text import norm


def apply_display_domain_aliases(m):
    payload=json.loads((m.inputs/'display_domain_aliases.json').read_text())
    if payload['schema']!='FINEATLAS_NAVIGATION_NAMES_V1':
        raise ValueError('Unsupported display-name input')
    counts=Counter()
    for row in payload['domains']:
        domain=m.c.execute('SELECT * FROM domain_registry WHERE canonical_name=?',(row['domain'],)).fetchone()
        if not domain or domain['description']!=row['definition'] or json.loads(domain['root_uids'])!=row['root_uids']:
            raise ValueError('Navigation alias scope differs from the frozen domain')
        proof={'navigation_only':True,'identity_assertion':False,'domain':row['domain'],
               'definition':row['definition'],'root_uids':row['root_uids'],'aliases':row['aliases'],
               'basis':'Reviewed Chinese display names for the existing explicitly defined directory'}
        source='FineAtlas reviewed navigation display aliases'
        eid=m.evidence(source,payload['source_uri'],proof,'NAVIGATION_DISPLAY_NAME')
        for name in row['aliases']:
            alias=norm(name)
            old=m.c.execute('SELECT * FROM domain_aliases WHERE alias=?',(alias,)).fetchone()
            if old:
                if old['domain_id']!=domain['domain_id']:
                    raise ValueError('Display alias is already assigned to another scope: '+name)
                counts['existing_aliases_preserved']+=1
                continue
            provenance=json.dumps({'basis':proof['basis'],'navigation_only':True,'evidence_id':eid},ensure_ascii=False)
            m.c.execute('INSERT INTO domain_aliases VALUES(?,?,?)',(alias,domain['domain_id'],provenance))
            m.change('navigation_display_names','domain_alias',alias,None,
                     {'domain_id':domain['domain_id'],'alias':alias},proof)
            counts['new_navigation_aliases']+=1
    m.c.commit()
    return dict(counts)
