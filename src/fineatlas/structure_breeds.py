"""Identifier-grounded breed catalogues and reviewed host-type navigation.

FCI groups are organizational facts in separate tables, never IS_A parents or
evolutionary distances. A source's registry cross-reference selects catalogue
membership; it does not merge source identities. WordNet scientific lemmas are
only review candidates. A frozen individual scope adjudication is required to
authorize each host inclusion.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import urljoin

from .hierarchy import apply_refinements
from .semantics import role_expression

INPUT_NAME = 'structure_breeds.json'
LINKS_NAME = 'structure_breeds_links.jsonl'
SCHEMA = 'FINEATLAS_STRUCTURE_BREEDS_V1'
VBO_SOURCE = 'Vertebrate Breed Ontology'
FCI_NAMESPACE = 'fci-nomenclature'
FCI_URI = 'https://www.fci.be/en/Nomenclature/Default.aspx'
RELATION = 'ORGANIZATION_GROUP_MEMBER'


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def sha(value):
    return hashlib.sha256(value if isinstance(value,bytes) else value.encode()).hexdigest()


def source_rank(node):
    return next((p['val'].rsplit('_',1)[-1] for p in node.get('meta',{}).get('basicPropertyValues',[])
                 if p['pred'].endswith('#has_rank')), 'breed' if '/VBO_' in node['id'] else 'no rank')


def scientific_names(node):
    """Literal primary name and asserted scientific synonyms, not common words."""
    names = [node.get('lbl','')]
    names.extend(s['val'] for s in node.get('meta',{}).get('synonyms',[])
                 if s['pred']=='hasExactSynonym' or s.get('synonymType','').endswith('#synonym'))
    return {name for name in names if re.fullmatch(r'[A-Z][a-z]+ [a-z][a-z-]+',name)}


def parse_fci_catalogue(directory):
    """Parse ten frozen official pages; IDs, sections and parents are literal."""
    # Preparation-only optional dependency, not needed by the read-only SDK.
    from bs4 import BeautifulSoup
    directory = Path(directory)
    manifest = json.loads((directory/'fci-manifest.json').read_text())
    if sorted(row['group'] for row in manifest) != list(range(1,11)):
        raise ValueError('FCI snapshot must contain all ten distinct groups')
    provisional_path = directory/'fci-provisional-manifest.json'
    provisional = json.loads(provisional_path.read_text()) if provisional_path.exists() else []
    version = 'snapshot-' + sha(canonical({'groups':[{k:r[k] for k in ('group','url','sha256')} for r in manifest],
                                          'provisional':provisional}))[:16]
    groups, standards = {}, defaultdict(list)
    for snapshot in sorted(manifest,key=lambda r:r['group']):
        path = directory/snapshot['path']
        raw = path.read_bytes()
        if sha(raw) != snapshot['sha256']:
            raise ValueError('FCI source snapshot hash changed: '+path.name)
        soup = BeautifulSoup(raw,'html.parser')
        headings = [h.get_text(' ',strip=True) for h in soup.find_all(['h1','h2','h3'])
                    if re.match(r'^Group\s+\d+\s*:',h.get_text(' ',strip=True))]
        if len(headings) != 1 or int(re.search(r'Group\s+(\d+)',headings[0])[1]) != snapshot['group']:
            raise ValueError('FCI page group heading disagrees with frozen identifier')
        group_id = str(snapshot['group'])
        group_uid = 'fci:'+version+':group:'+group_id
        proof = {'source_uri':snapshot['url'],'source_page_sha256':snapshot['sha256'],
                 'source_version':version,'source_group_id':group_id,
                 'scope':'ORGANIZATION_CATALOGUE','is_class_inclusion':False,
                 'not_evolutionary_or_visual_distance':True,
                 'license':'Derived classification facts only; official text/PDF/image rights remain with FCI'}
        groups[group_uid] = {'group_uid':group_uid,'namespace':FCI_NAMESPACE,'source_version':version,
                             'source_group_id':group_id,'label':headings[0],'parent_group_uid':None,
                             'source_uri':snapshot['url'],'proof':proof}
        anchors = soup.select('a.nom[href]')
        if not anchors:
            raise ValueError('Official FCI group contains no breed rows')
        for anchor in anchors:
            match = re.search(r'-(\d+)\.html$',anchor['href'])
            if not match:
                raise ValueError('Malformed official FCI breed identifier')
            standard = match[1]
            row_text = anchor.get_text(' ',strip=True)
            if '('+standard+')' not in row_text:
                raise ValueError('FCI displayed standard number and URL disagree')
            path_uids = [group_uid]
            section = None
            for ancestor in anchor.parents:
                if ancestor.name != 'li':
                    continue
                spans = ancestor.find_all('span',recursive=False)
                section = next((s.get_text(' ',strip=True) for s in spans
                                if re.search(r'_SectionLabel_\d+$',s.get('id',''))),None)
                if section:
                    break
            if section:
                number = re.match(r'Section\s+(\d+)\s*:',section)
                if not number:
                    raise ValueError('Malformed native FCI section')
                section_uid = group_uid+':section:'+number[1]
                groups.setdefault(section_uid,{'group_uid':section_uid,'namespace':FCI_NAMESPACE,
                    'source_version':version,'source_group_id':group_id+'.'+number[1],
                    'label':section,'parent_group_uid':group_uid,'source_uri':snapshot['url'],
                    'proof':{**proof,'native_section':section}})
                path_uids.append(section_uid)
            standard_row = {'standard_id':standard,'native_group_path':path_uids,
                            'source_uri':urljoin(snapshot['url'],anchor['href']),
                            'page_uri':snapshot['url'],'page_sha256':snapshot['sha256']}
            if standard_row not in standards[standard]:
                standards[standard].append(standard_row)
    for snapshot in provisional:
        raw = (directory/snapshot['path']).read_bytes()
        if sha(raw)!=snapshot['sha256']:
            raise ValueError('FCI provisional snapshot hash changed')
        soup = BeautifulSoup(raw,'html.parser')
        ident = soup.find(id='ContentPlaceHolder1_NumeroLabel')
        group_field = soup.find(id='ContentPlaceHolder1_GroupeHyperLink')
        if ident is None or ident.get_text(strip=True)!=snapshot['standard_id'] or group_field is None:
            raise ValueError('Official provisional record identifier missing or mismatched')
        group_match = re.match(r'n°\s*(\d+)\s*-',group_field.get_text(' ',strip=True))
        if not group_match:
            raise ValueError('Official provisional group number is not explicit')
        group_uid = 'fci:'+version+':group:'+group_match[1]
        if group_uid not in groups:
            raise ValueError('Provisional record group is not in official catalogue')
        path_uids = [group_uid]
        section_field = soup.find(id='ContentPlaceHolder1_SectionLabel')
        if section_field:
            section_text = section_field.get_text(' ',strip=True)
            matching = [g['group_uid'] for g in groups.values() if g['parent_group_uid']==group_uid and
                        re.sub(r'^Section\s+\d+\s*:\s*','',g['label'])==section_text]
            if len(matching)==1:
                path_uids.extend(matching)
        standards[snapshot['standard_id']].append({'standard_id':snapshot['standard_id'],
            'native_group_path':path_uids,'source_uri':snapshot['url'],'page_uri':snapshot['url'],
            'page_sha256':snapshot['sha256'],'recognition_scope':'SOURCE_DECLARED_PROVISIONAL'})
    for standard,rows in standards.items():
        if len({r['native_group_path'][0] for r in rows}) != 1:
            raise ValueError('One FCI standard occurs in incompatible groups: '+standard)
    return {'source_version':version,'groups':list(groups.values()),
            'standards':dict(standards),'manifest':manifest,'provisional_manifest':provisional,
            'redistribution':'Derived numeric standard/group facts and VBO-licensed labels; raw FCI HTML/standards PDFs are not redistributed'}


def identifier_memberships(source_node, catalogue):
    """Use only explicit registry IDs. Ambiguity never authorizes a merge."""
    refs = sorted({x['val'].split(':',1)[1] for x in source_node.get('meta',{}).get('xrefs',[])
                   if re.fullmatch(r'FCI:\d+',x['val'])})
    if not refs:
        return [], 'NO_SOURCE_FCI_IDENTIFIER'
    if any(ref not in catalogue['standards'] for ref in refs):
        return [], 'FCI_IDENTIFIER_NOT_IN_FROZEN_DEFINITIVE_DIRECTORY'
    # A standard may span named varieties; only containers shared by every
    # official record and every source cross-reference are safe for its scope.
    paths = [set(row['native_group_path']) for ref in refs for row in catalogue['standards'][ref]]
    shared = set.intersection(*paths)
    if not shared:
        return [], 'INCOMPATIBLE_ORGANIZATION_GROUP_SCOPES'
    return [{'group_uid':group_uid,'source_member_id':'|'.join('FCI:'+ref for ref in refs),
             'proof':{'native_xrefs':['FCI:'+ref for ref in refs],
                      'fci_rows':[row for ref in refs for row in catalogue['standards'][ref]],
                      'native_ontology_uri':source_node['id'],
                      'native_ontology_record_sha256':sha(canonical(source_node)),
                      'source_version':catalogue['source_version'],
                      'identity_merge_authorized':False,'is_class_inclusion':False,
                      'scope':'ORGANIZATION_CATALOGUE'}} for group_uid in sorted(shared)], 'VERIFIED_NATIVE_REGISTRY_MEMBERSHIP'


def host_candidates(source_nodes, wordnet_nodes):
    """Candidate discovery cannot authorize taxonomic identity or inclusion."""
    senses = defaultdict(list)
    for node in wordnet_nodes:
        for label in json.loads(node['data']).get('labels',[]):
            name = label.replace('_',' ')
            if re.fullmatch(r'[A-Z][a-z]+ [a-z][a-z-]+',name):
                senses[name].append(node)
    candidates = []
    for node in source_nodes:
        if '/NCBITaxon_' not in node['id'] or source_rank(node) not in ('species','subspecies'):
            continue
        names = scientific_names(node)
        matched = {n['uid']:n for name in names for n in senses.get(name,())}
        candidates.append({'source_uid':'vbo:'+node['id'].rsplit('/',1)[-1],
                           'source_name':node['lbl'],'native_rank':source_rank(node),
                           'native_ontology_record_sha256':sha(canonical(node)),
                           'scientific_names':sorted(names),
                           'candidates':[{'uid':uid,'label':n['label'],'definition':n['description'],
                                          'data_sha256':sha(n['data'])} for uid,n in sorted(matched.items())]})
    return candidates


def validate_host_review(candidate, review):
    if review.get('status') != 'APPROVED_TYPE_INCLUSION' or not review.get('scope_reason'):
        raise ValueError('Host link requires individual source-scope inclusion review')
    if review.get('identity_merge_authorized') is not False or review.get('is_class_inclusion') is not True:
        raise ValueError('Host review must authorize type inclusion without identity merging')
    matched = [r for r in candidate['candidates'] if r['uid']==review.get('target_uid')]
    if len(matched) != 1:
        raise ValueError('Reviewed host target lacks retained explicit scientific sense')
    return matched[0]


def catalogue_scope_candidates(source_nodes, wordnet_nodes, catalogue):
    """Find registered-designation candidates; human scope review is separate."""
    from ._text import norm
    registered = defaultdict(list)
    for node in source_nodes:
        assignments,status = identifier_memberships(node,catalogue)
        if not assignments or '/VBO_' not in node['id']:
            continue
        for synonym in node.get('meta',{}).get('synonyms',[]):
            if synonym['pred']=='hasExactSynonym':
                registered[norm(synonym['val'])].append((node,assignments))
    candidates = []
    for wordnet in wordnet_nodes:
        matches = {}
        for name in [wordnet['label'],*json.loads(wordnet['data']).get('labels',[])]:
            for node,assignments in registered.get(norm(name),[]):
                matches[node['id']] = (node,assignments)
        group_sets = [{a['group_uid'] for a in assignments} for _,assignments in matches.values()]
        if not group_sets:
            continue
        shared = set.intersection(*group_sets)
        candidates.append({'uid':wordnet['uid'],'label':wordnet['label'],'definition':wordnet['description'],
                           'data_sha256':sha(wordnet['data']),'group_uids':sorted(shared),
                           'source_breed_uids':['vbo:'+uri.rsplit('/',1)[-1] for uri in sorted(matches)],
                           'source_breed_labels':[matches[uri][0]['lbl'] for uri in sorted(matches)],
                           'source_fci_ids':sorted({a['source_member_id'] for _,ass in matches.values() for a in ass}),
                           'identity_merge_authorized':False,'status':'CANDIDATE_ONLY'})
    return candidates


def dog_component_in(atlas, uid):
    return atlas._basic('wordnet31:02086723-n')['component_id'] in atlas._ancestor_map(uid)


def prepare_structure_breeds(database, vbo, fci, output, *, host_review=None, catalogue_review=None):
    """Freeze complete imported VBO cohort and identifier-grounded additions."""
    database,vbo,output = Path(database),Path(vbo),Path(output)
    output.mkdir(parents=True,exist_ok=True)
    raw = vbo.read_bytes()
    vbo_sha = sha(raw)
    graph = json.loads(raw)['graphs'][0]
    licenses = [x['val'] for x in graph.get('meta',{}).get('basicPropertyValues',[])
                if x['pred']=='http://purl.org/dc/terms/license']
    if licenses != ['https://creativecommons.org/licenses/by/4.0/']:
        raise ValueError('Inspect VBO redistribution licence before importing')
    source_nodes = {n['id']:n for n in graph['nodes'] if n.get('type')=='CLASS' and not n.get('meta',{}).get('deprecated')}
    catalogue = parse_fci_catalogue(fci)
    con = sqlite3.connect(database.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
    con.row_factory = sqlite3.Row
    retained = [dict(r) for r in con.execute('SELECT uid,label,source,rank,data,visibility,component_id FROM nodes WHERE source=?',(VBO_SOURCE,))]
    if not retained:
        raise ValueError('Baseline has no imported VBO cohort')
    active,protected,members,ledger = [],[],[],[]
    for row in retained:
        uri = json.loads(row['data']).get('native_ontology_uri')
        node = source_nodes.get(uri)
        if not node or vbo_sha != json.loads(row['data']).get('source_sha256'):
            raise ValueError('Imported VBO node differs from the frozen source version: '+row['uid'])
        protected.append({'uid':row['uid'],'label':row['label'],'source':row['source'],
                          'rank':row['rank'],'data_sha256':sha(row['data'])})
        if row['visibility'] != 'ACTIVE':
            ledger.append({'uid':row['uid'],'status':'SOURCE_ONLY_NOT_PROMOTED'})
            continue
        active.append(node)
        assignments,status = identifier_memberships(node,catalogue)
        if '/VBO_' in uri:
            ledger.append({'uid':row['uid'],'label':row['label'],'status':status,
                           'fci_ids':[x['val'] for x in node.get('meta',{}).get('xrefs',[]) if x['val'].startswith('FCI:')],
                           'native_rank':source_rank(node),'group_uids':[a['group_uid'] for a in assignments]})
        for assignment in assignments:
            members.append({**assignment,'member_uid':row['uid'],'relation':RELATION,'status':'ACTIVE',
                            'proof':{**assignment['proof'],'vbo_source_sha256':vbo_sha,
                                     'vbo_source_version':graph['meta']['version'],
                                     'license':'VBO CC-BY-4.0; FCI factual registry grouping with attribution'}})
    wordnet = [dict(r) for r in con.execute("SELECT uid,label,data,description,component_id FROM nodes WHERE source='wordnet31' AND visibility='ACTIVE'")]
    candidates = host_candidates(active,wordnet)
    reviews = json.loads(Path(host_review).read_text()) if host_review else []
    by_review = {r['source_uid']:r for r in reviews}
    if len(by_review) != len(reviews) or set(by_review)-{r['source_uid'] for r in candidates}:
        raise ValueError('Host review cohort contains duplicates or non-source taxa')
    links,host_ledger = [],[]
    catalogue_candidates,scope_reviews = [],[]
    from . import FineAtlas
    with FineAtlas(database,relation_view='unified') as atlas:
        dog_uids = {row[0] for row in atlas.con.execute("""WITH RECURSIVE down(uid) AS (VALUES(?) UNION
            SELECT e.child_uid FROM down d JOIN edges e ON e.parent_uid=d.uid
            JOIN nodes n ON n.uid=e.child_uid WHERE e.status='ACTIVE' AND e.relation='IS_A'
            AND n.source='wordnet31') SELECT uid FROM down""",('wordnet31:02086723-n',))}
        dog_types = [node for node in wordnet if node['uid'] in dog_uids]
        # Inspect the remaining retained documentary breed records too; these
        # remain source UIDs even when the WordNet/VBO identities differ.
        documentary = [dict(r) for r in con.execute("""SELECT uid,label,data,description,component_id
            FROM nodes WHERE source IN ('wikidata','wikidata_v4_p31') AND visibility='ACTIVE'
            AND instr(lower(description),'breed')>0 AND instr(lower(description),'dog')>0""")]
        dog_types += [node for node in documentary if dog_component_in(atlas,node['uid'])]
        catalogue_candidates = catalogue_scope_candidates(active,dog_types,catalogue)
        scope_reviews = json.loads(Path(catalogue_review).read_text()) if catalogue_review else []
        by_candidate = {r['uid']:r for r in catalogue_candidates}
        if len({r['uid'] for r in scope_reviews})!=len(scope_reviews):
            raise ValueError('Duplicate source catalogue scope review')
        for review in scope_reviews:
            candidate = by_candidate.get(review['uid'])
            if not candidate or review.get('status')!='APPROVED_ORGANIZATION_MEMBERSHIP' or not review.get('scope_reason') or review.get('identity_merge_authorized') is not False:
                raise ValueError('Organizational membership lacks individual registered-breed scope review')
            if not candidate['group_uids']:
                raise ValueError('Ambiguous registered standards cannot authorize organizational membership')
            native_rows = [r for r in members if r['member_uid'] in candidate['source_breed_uids']]
            for group_uid in candidate['group_uids']:
                evidence = [r for r in native_rows if r['group_uid']==group_uid]
                proof = {'basis':'INDIVIDUALLY_REVIEWED_REGISTERED_BREED_DESIGNATION_AND_DOCUMENTED_DOMESTIC_DOG_SCOPE',
                         'scope_review':review,'candidate_evidence':candidate,
                         'native_registry_records':[r['proof'] for r in evidence],
                         'identity_merge_authorized':False,'is_class_inclusion':False,
                         'scope':'ORGANIZATION_CATALOGUE','source_version':catalogue['source_version'],
                         'source_uri':FCI_URI,'license':'Derived classification facts; VBO CC-BY-4.0 and WordNet attribution retained'}
                members.append({'group_uid':group_uid,'member_uid':candidate['uid'],
                                'source_member_id':'|'.join(candidate['source_fci_ids']),
                                'relation':RELATION,'status':'ACTIVE','proof':proof})
            wn = atlas.con.execute('SELECT uid,label,source,rank,data FROM nodes WHERE uid=?',(candidate['uid'],)).fetchone()
            protected.append({k:wn[k] for k in ('uid','label','source','rank')}|{'data_sha256':sha(wn['data'])})
        for candidate in candidates:
            uid = candidate['source_uid']
            review = by_review.get(uid)
            if not review or review.get('status')!='APPROVED_TYPE_INCLUSION':
                host_ledger.append({**candidate,'status':'REVIEW','reason':(review or {}).get('scope_reason') or
                                    'No individual scope evidence authorizes scientific-lemma candidate; existing native taxonomy retained'})
                continue
            target = validate_host_review(candidate,review)
            own,parent = atlas._basic(uid),atlas._basic(target['uid'])
            if not own or not parent or own['node_kind']!='CLASS' or parent['node_kind']!='CLASS':
                raise ValueError('Host inclusion requires admitted biological class endpoints')
            for node_uid in (uid,target['uid']):
                if atlas.identity(node_uid)['role_status']!='CONSISTENT':
                    raise ValueError('Host inclusion cannot bypass role conflict')
            upward = atlas._ancestor_map(uid)
            if parent['component_id'] in upward:
                status = 'EXISTING_IDENTITY_OR_TYPE_PATH_PRESERVED'
            else:
                if own['component_id'] in atlas._ancestor_map(target['uid']):
                    raise ValueError('Reviewed host inclusion would create a cycle')
                node = source_nodes['http://purl.obolibrary.org/obo/'+uid.split(':',1)[1]]
                proof = {**review,'basis':'INDIVIDUALLY_REVIEWED_NATIVE_HOST_TO_WORDNET_TYPE_INCLUSION','source_uri':node['id'],'source_version':graph['meta']['version'],
                         'vbo_source_sha256':vbo_sha,'source_scientific_names':candidate['scientific_names'],
                         'native_ontology_record_sha256':candidate['native_ontology_record_sha256'],
                         'wordnet_endpoint':target,'source_role':'Native NCBI taxon retained in VBO',
                         'license':'VBO CC-BY-4.0 and Princeton WordNet source attribution retained'}
                links.append({'op':'link','uid':uid,'parent':target['uid'],'relation':'IS_A',
                              'source':'Reviewed VBO native host to WordNet type scope','uri':node['id'],'proof':proof})
                wn = atlas.con.execute('SELECT uid,label,source,rank,data FROM nodes WHERE uid=?',(target['uid'],)).fetchone()
                protected.append({k:wn[k] for k in ('uid','label','source','rank')}|{'data_sha256':sha(wn['data'])})
                status = 'PREPARED_REVIEWED_TYPE_INCLUSION'
            host_ledger.append({**candidate,'status':status,'scope_review':review})
        labels = []
        for dataset in ('pets37','stanford_dogs'):
            for label in atlas.task_labels(dataset):
                uid = label['target_uid']
                closure = atlas._ancestor_map(uid)
                peers = list(atlas.con.execute('SELECT uid,source FROM nodes WHERE component_id=?',
                                               (atlas._basic(uid)['component_id'],)))
                vbo_peers = [p for p in peers if p['source']==VBO_SOURCE]
                group_rows = [m for m in members if any(p[0]==m['member_uid'] for p in peers)]
                labels.append({'dataset':dataset,'class_id':label['class_id'],'label':label['label'],'uid':uid,
                    'native_vbo_identity_peers':[p[0] for p in vbo_peers],
                    'fci_group_memberships':[{'group_uid':m['group_uid'],'native_member_uid':m['member_uid']} for m in group_rows],
                    'dog_boundary_reachable':atlas._basic('wordnet31:02086723-n')['component_id'] in closure,
                    'animal_boundary_reachable':atlas._basic('wordnet31:00015568-n')['component_id'] in closure,
                    'world_identity_verified':label['identity_verified'],
                    'object_scope':'SOURCE_BREED' if vbo_peers else 'REAL_WORLD_LABEL_SCOPE_RETAINED',
                    'no_forced_domestic_dog_mapping':True})
    con.close()
    payload = {'schema':SCHEMA,'source_database_modified':False,'vbo_source_sha256':vbo_sha,
               'vbo_source_version':graph['meta']['version'],'fci_catalogue':catalogue,
               'retained_nodes':protected,'members':members,'links':links,
               'vbo_identifier_ledger':ledger,'host_scope_ledger':host_ledger,'dataset_scope_ledger':labels,
               'catalogue_scope_candidates':catalogue_candidates,'catalogue_scope_reviews':scope_reviews}
    (output/INPUT_NAME).write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
    (output/LINKS_NAME).write_text(''.join(canonical(link)+'\n' for link in links))
    summary = {'vbo_cohort_nodes':len(retained),'breed_cohort_nodes':len(ledger),
               'fci_groups_and_sections':len(catalogue['groups']),'fci_standards':len(catalogue['standards']),
               'matched_native_breed_uids':len({m['member_uid'] for m in members if m['member_uid'].startswith('vbo:')}),
               'catalogue_member_uids':len({m['member_uid'] for m in members}),
               'organization_memberships':len(members),'organization_memberships_are_not_isa':True,
               'host_taxa_scanned':len(candidates),'host_type_links_prepared':len(links),
               'host_statuses':dict(Counter(r['status'] for r in host_ledger)),
               'source_identifier_statuses':dict(Counter(r['status'] for r in ledger)),
               'dataset_labels_audited':len(labels),'input_sha256':sha((output/INPUT_NAME).read_bytes()),
               'reviewed_wordnet_catalogue_members':sum(r['uid'].startswith('wordnet31:') for r in scope_reviews),
               'reviewed_documentary_catalogue_members':sum(not r['uid'].startswith('wordnet31:') for r in scope_reviews),
               'ordinary_classes_added':0,'identity_merges_added':0,
               'source_database_modified':False}
    (output/'structure_breeds_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    return summary


def apply_structure_breeds(m):
    """Replay into a candidate only, before shared caches are reconstructed."""
    path = m.inputs/INPUT_NAME
    if not path.exists():
        return {'status':'not_requested'}
    payload = json.loads(path.read_text())
    if payload.get('schema') != SCHEMA:
        raise ValueError('Unsupported breed source repair schema')
    fingerprint = sha(path.read_bytes())
    prior = m.c.execute("SELECT value FROM metadata WHERE key='structure_breeds_input_sha256'").fetchone()
    if prior and json.loads(prior[0]) == fingerprint:
        return {'status':'already_applied','input_sha256':fingerprint}
    if [json.loads(line) for line in (m.inputs/LINKS_NAME).read_text().splitlines() if line] != payload['links']:
        raise ValueError('Frozen breed link input differs from reviewed manifest')
    for protected in payload['retained_nodes']:
        row = m.c.execute('SELECT uid,label,source,rank,data FROM nodes WHERE uid=?',(protected['uid'],)).fetchone()
        actual = ({k:row[k] for k in ('uid','label','source','rank')}|{'data_sha256':sha(row['data'])}) if row else None
        if actual != protected:
            raise ValueError('Protected source breed payload drift: '+protected['uid'])
    counts = Counter()
    for group in payload['fci_catalogue']['groups']:
        values = tuple(group[k] for k in ('group_uid','namespace','source_version','source_group_id','label','parent_group_uid','source_uri'))+(canonical(group['proof']),)
        old = m.c.execute('SELECT * FROM source_groups WHERE group_uid=?',(group['group_uid'],)).fetchone()
        if old and tuple(old) != values:
            raise ValueError('Organizational group version drift; use a new frozen group UID')
        m.c.execute('INSERT OR IGNORE INTO source_groups VALUES(?,?,?,?,?,?,?,?)',values)
        counts['source_groups_added'] += old is None
    for member in payload['members']:
        if member['relation']!=RELATION or member['proof'].get('identity_merge_authorized') is not False:
            raise ValueError('Registry grouping cannot authorize taxonomic identity')
        eid = m.evidence('FCI grouping through native VBO registry identifier',FCI_URI,member['proof'],'ORGANIZATION_GROUP_MEMBER')
        values = tuple(member[k] for k in ('group_uid','member_uid','source_member_id','relation','status'))+(canonical(member['proof']),)
        old = m.c.execute('SELECT * FROM source_group_members WHERE group_uid=? AND member_uid=?',values[:2]).fetchone()
        if old and tuple(old) != values:
            raise ValueError('Source organizational membership proof drift')
        m.c.execute('INSERT OR IGNORE INTO source_group_members VALUES(?,?,?,?,?,?)',values)
        m.c.execute('INSERT OR IGNORE INTO source_field_values VALUES(?,?,?,?,?)',
                    (member['member_uid'],'organization_group',member['group_uid'],FCI_NAMESPACE,eid))
        counts['organization_memberships_added'] += old is None
    counts.update(apply_refinements(m,LINKS_NAME))
    m.meta('structure_breeds_input_sha256',fingerprint)
    m.meta('source_organization_group_scope',{'namespace':FCI_NAMESPACE,
        'relation':RELATION,'classification_parent':False,'distance_policy':'EXCLUDED',
        'source_version':payload['fci_catalogue']['source_version']})
    m.c.commit()
    return dict(counts)
