"""Fail closed on unreviewed lexical parent selection, preserving source facts.

This adapter never merges identities, guesses from names, or trains models.
It freezes each old assertion by its complete content, including the original
proof. A source declaration about a subject does not verify every noun found
in its description as the subject's physical type.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import gzip
import json
from pathlib import Path
import re
import sqlite3

from .hierarchy import source_assertion_sha256, validate_link_roles
from .semantics import role_expression

INPUT_NAME = "structure_source_contracts.json"
REVIEW_STATUS = "SOURCE_SCOPE_REVIEW"
SOURCE_NAME = "Independently frozen whole-subject physical genus"
NATIVE_TRANSFORM_SOURCES = frozenset({
    "Full engineering subject and grain evidence",
    "Source engineering grain and relation repair",
    "Unified role navigation of retained declared subtype",
    "Verified current primary product/cultivar scope",
    "Reviewed native endpoint relation repair",
})

# These are evidence-production cohorts, not domain/label exception lists.
# The original native source taxonomy/design relationships are not included.
LEXICAL_SOURCES = frozenset({
    "Full engineering subject and grain evidence",
    "Independent native product-family definition",
    "Retained independent generic-head definition",
    "Independent legacy generic-head type refinements",
    "Rechecked independent object-kind definitions",
    "Independent encyclopedia nominal head with reviewed native parent sense",
    "Independent encyclopedia type definition",
    "Independent frozen definition rescues retained candidate",
    "Independent nominal head and native parent identity reviewed",
    "independent Wikipedia definition with Wikidata identifier",
    "FDA physical-head scope and WordNet native inclusion",
})

# Explicitly reviewed physical senses. Ambiguous bare plane, fighter, service,
# line, architecture, plant, board, switch, router, balloon, vessel and vehicle
# are deliberately absent. Definitions and hashes are frozen during preparation.
GENERA = (
    (r"(?:aircraft|airplanes?|aeroplanes?|airliners?|biplanes?|monoplanes?|helicopters?|rotorcraft)",
     "wordnet31:02689427-n", "a vehicle that can fly"),
    (r"(?:automobiles?|cars?)", "wordnet31:02961779-n", "a motor vehicle with four wheels"),
    (r"(?:locomotives?)", "wordnet31:03690149-n", "a wheeled vehicle consisting of a self-propelled engine"),
    (r"(?:laptops?|laptop computers?|notebook computers?|subnotebook computers?)",
     "wordnet31:03648120-n", "a portable computer small enough to use in your lap"),
    (r"(?:computers?)", "wordnet31:03086983-n", "a machine for performing calculations automatically"),
    (r"(?:dinnerware)", "wordnet31:03207306-n", "the tableware"),
    (r"(?:loudspeakers?)", "wordnet31:03696785-n", "electro-acoustic transducer"),
    (r"(?:microprocessors?)", "wordnet31:03765845-n", "integrated circuit semiconductor chip"),
    (r"(?:capacitors?)", "wordnet31:02958683-n", "an electrical device characterized by its capacity to store an electric charge"),
)

# A closed reviewed adjective grammar, separately from the genus. Unknown
# words cause review: a book *about* aircraft or a game *named* Cars cannot
# acquire the type of its final noun. Product/subject names are never modifiers.
GENERAL_MODIFIERS = frozenset("American British Canadian Chinese Czech European French German Indian Italian Japanese Russian Soviet Spanish Swedish Swiss Turkish Australian Dutch Belgian Polish modern old new early late historical light heavy medium small large compact subcompact professional experimental proposed prototype civil civilian military commercial regional passenger cargo transport utility general purpose powered single twin double two three four six eight multi engine engined seat seater seating wing fixed rotary naval armed unarmed manned unmanned piloted remote radio control controlled supersonic subsonic turboprop turbofan jet piston electric electrical battery fuel cell diesel petrol gasoline hybrid hydrogen sports sport racing road motor mid rear front wheel wheeled drive luxury family executive business production reusable reusable digital analogue analog electronic electromechanical relay personal portable handheld mobile desktop server mainframe mini micro super pocket tablet notebook laptop subnotebook embedded industrial UNIX Linux gaming barebone all one form factor home built homebuilt kit agricultural training trainer attack bomber fighter reconnaissance observation wide narrow body variable fixed ceramic multilayer monolithic tantalum aluminium aluminum film electrolytic chip capacitor surface mount low high voltage ceramic axial radial dielectric semiconductor silicon germanium Zener audio electro acoustic dynamic permanent magnet".casefold().split())


def sha(value: str | bytes) -> str:
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def read_manifest(path):
    return json.loads(gzip.decompress(path.read_bytes()) if path.suffix == ".gz" else path.read_bytes())


def own_subject_genus(statement: str, label: str) -> tuple[str, str] | None:
    """Independent restrictive subject parser; never select a trailing token.

    An explicit genus is accepted only in the first subject clause, before
    relative/purpose/material/location clauses or named design arguments.
    This is a small reviewed statement contract, not a language-wide classifier.
    Anything outside it remains review. No identity equality is asserted.
    """
    whole_statement = statement or ""
    text = re.sub(r"\([^()]*\)", "", whole_statement).strip()
    wrapper = re.fullmatch(r"Native source label:\s*(.*?);\s*subject definition:\s*(.+)", text, re.I | re.S)
    if wrapper:
        if wrapper[1].strip().casefold() != label.strip().casefold():
            return None
        text = wrapper[2].strip()
    elif ":" in text:
        return None  # unparsed source/label packaging is not a subject assertion
    text = re.split(r"[.;]\s+(?=[A-Z])", text, maxsplit=1)[0]
    copula = re.search(r"\b(?:is|was|are|were)\b\s+", text, re.I)
    if copula:
        prefix = text[:copula.start()]
        if re.search(r"\b(?:that|which|whose|who|where)\b", prefix, re.I):
            return None
        words = lambda value: re.findall(r"[a-z0-9]+", value.casefold())
        wanted, present = words(label), words(prefix)
        if present[:1] == ["the"]:
            present = present[1:]
        if present[:-1] == wanted and present[-1:] in (["series"], ["family"], ["range"], ["model"]):
            present = wanted
        if not wanted or wanted != present:
            return None  # a redirected or different-subject sentence
        text = text[copula.end():]
    text = re.sub(r"^(?:an?|the)\s+", "", text, flags=re.I)
    if re.match(r"(?:about|used|designed|produced|manufactured|built|made|located|called|named|known)\b", text, re.I):
        return None
    text = re.sub(r"^(?:family|series|line|range|type|kind|class)\s+of\s+", "", text, flags=re.I)
    # A comma before a restrictive/relative clause can coordinate distinct
    # subject kinds. Do not reduce a laptops/desktops/tablets range to laptops.
    main_scope = re.split(r"\s+(?:based|whose|with|without|that|which|for|to|in|near|of|by|from|since)\b|[.;]", text, maxsplit=1, flags=re.I)[0]
    if "," in main_scope and not re.match(r"\s*(?:licen[cs]e-built|(?:a )?version|originally|first|introduced|released|produced|manufactured|designed)\b", main_scope.split(",", 1)[1], re.I):
        return None
    text = re.split(r"\s+(?:based|whose|with|without|that|which|for|to|in|near|of|by|from|since|"
                    r"used|intended|designed|developed|manufactured|produced|built|made|released|"
                    r"introduced|marketed|capable|containing|consisting|featuring|belonging)\b|[,;]",
                    text, maxsplit=1, flags=re.I)[0].strip()
    if (not text or re.search(r"\b(?:toy|scale|miniature|fictional|imaginary|standard|protocol|"
                              r"architecture|language|software|engine|parts?|components?|"
                              r"accessories|one-off|sole|only example|railroad|railway|cable|elevator|airship)\b", text, re.I)):
        return None
    # Remaining coordinated nouns and unparsed parenthetical references are
    # not reduced to one last word. Pure size/adjective coordination is review.
    if re.search(r"\b(?:and|or|as)\b", text, re.I):
        return None
    if re.search(r"\b(?:not|never|no|neither|without)\b", text, re.I):
        return None
    for pattern, uid, definition_prefix in GENERA:
        matched = re.search(r"\b(" + pattern + r")\s*(?:model|variant|family|series|design|prototype)?\s*$", text, re.I)
        if matched:
            modifiers = re.findall(r"[A-Za-z]+|\d+", text[:matched.start()].casefold())
            if any(word not in GENERAL_MODIFIERS and not word.isdigit() for word in modifiers):
                continue
            if uid == "wordnet31:02961779-n":
                wheels = re.search(r"\b(one|two|three|four|five|six|seven|eight|nine|ten|single|twin|\d+)[ -]+wheel(?:s|ed|er)?\b", text, re.I)
                if wheels and wheels[1].casefold() not in {"four", "4"}:
                    continue  # the retained WordNet car sense requires four wheels
                # Relative/body qualifiers cannot disappear when the noun
                # phrase is cropped. This checks actual subject properties,
                # rather than any incidental mention of a different vehicle.
                count = r"(one|two|three|four|five|six|seven|eight|nine|ten|single|twin|\d+)"
                wheel_properties = re.finditer(r"\b(?:with|has|had|having|uses|using|on)\s+(?:only\s+)?" + count + r"[ -]+wheels?\b", whole_statement, re.I)
                if any(w[1].casefold() not in {"four", "4"} for w in wheel_properties):
                    continue
            if re.search(r"\b(?:that|which)\s+(?:is|was)\s+(?:an?\s+)?(?:toy|fictional|imaginary|scale model)\b|\b(?:that|which)\s+(?:is|was)\s+not\s+(?:an?\s+)?(?:real|physical)\b", whole_statement, re.I):
                continue
            return matched.group(1), uid
    return None


def own_family_scope(statement: str, label: str) -> bool:
    """Require the subject itself to be a family, rather than mentioning one."""
    text = re.sub(r"\([^()]*\)", "", statement or "").strip()
    wrapper = re.fullmatch(r"Native source label:\s*(.*?);\s*subject definition:\s*(.+)", text, re.I | re.S)
    if wrapper:
        if wrapper[1].strip().casefold() != label.strip().casefold():
            return False
        text = wrapper[2].strip()
    copula = re.search(r"\b(?:is|was|are|were)\b\s+", text, re.I)
    if copula:
        words = lambda s: re.findall(r"[a-z0-9]+", s.casefold())
        prefix = words(text[:copula.start()])
        if prefix[:1] == ["the"]:
            prefix = prefix[1:]
        wanted = words(label)
        if prefix != wanted and not (prefix[:-1] == wanted and prefix[-1:] in (["series"], ["family"], ["range"])):
            return False
        text = text[copula.end():]
    text = re.sub(r"^(?:an?|the)\s+", "", text, flags=re.I)
    main = re.split(r"\s+(?:in|by|from|which|that|for|with|based|developed|manufactured|produced|designed)\b|[,.;]", text, maxsplit=1, flags=re.I)[0]
    if re.search(r"\b(?:not|possibly|alleged|fictional|toy)\b", main, re.I):
        return False
    return bool(re.match(r"(?:family|series|line|range)\s+of\b", main, re.I) or re.search(r"\b(?:family|series|line|range)\s*$", main, re.I))


def _record(c, uid):
    row = c.execute("SELECT n.*," + role_expression("n", "p") + " role FROM nodes n "
                    "LEFT JOIN node_profiles p ON p.uid=n.uid WHERE n.uid=?", (uid,)).fetchone()
    return dict(row) if row else None


def _load_role_reviews(c, path):
    """Apply only frozen, actual whole-subject grain reviews to exact-ID peers."""
    if not path:
        return [], {}, []
    operations, roles, blocked = [], {}, []
    for review in json.loads(path.read_text()):
        subject = _record(c, review["uid"])
        if not subject or sha(subject["data"]) != review["native_record_sha256"]:
            raise ValueError("Reviewed whole-subject grain source record changed")
        proof = review["proof"]
        if not proof.get("individual_semantic_review") or not proof.get("scope_observation") or not proof.get("source_statement"):
            raise ValueError("A grain review needs an actual whole-subject scope decision")
        peers = [_record(c, row[0]) for row in c.execute("SELECT uid FROM nodes WHERE component_id=? ORDER BY uid", (subject["component_id"],))]
        qid = subject["uid"].split(":")[-1]
        if not all(p["uid"].startswith(("wikidata:", "wikidata-v4:")) and p["uid"].split(":")[-1] == qid for p in peers):
            blocked.append({"uid": subject["uid"], "status": "REVIEW_IDENTITY_PEER_SCOPE_FIRST", "peer_uids": [p["uid"] for p in peers], "proof": proof})
            continue
        for peer in peers:
            if peer["role"] not in {"CLASS", "MODEL", "MODEL_FAMILY", "INSTANCE"}:
                raise ValueError("Reviewed grain cannot replace a different source unit")
            roles[peer["uid"]] = review["role"]
            p = {**proof, "basis": "REVIEWED_GENERIC_WHOLE_SUBJECT_REPLACES_ADAPTER_DESIGN_ROLE" if review["role"] == "CLASS" else "REVIEWED_WHOLE_SUBJECT_DESIGN_OR_NAMED_INSTANCE_SCOPE",
                 "native_record_sha256": sha(peer["data"]), "source_record_uid": peer["uid"],
                 "reviewed_subject_uid": subject["uid"], "same_source_id": qid,
                 "identity_member_uids": [p["uid"] for p in peers],
                 "peer_scope_basis": "Identical native Wikidata identifier across source namespaces; no name-based equality", "source_role": review["role"],
                 "subject_kind_head": proof["source_statement"], "allowed_views": ["strict", "taxonomy", "membership", "unified"]}
            operations.append({"op": "role", "uid": peer["uid"], "role": review["role"], "source": "Individually frozen whole-subject grain", "uri": review["uri"], "proof": p})
    return operations, roles, blocked


def _statement(node, claim):
    data = json.loads(claim["data"] or "{}")
    basis = data.get("admission_basis", data)
    for key in ("source_statement", "source_description", "sentence"):
        if basis.get(key):
            return basis[key], key
    raw = json.loads(node["data"] or "{}")
    for key in ("definition", "intro", "wikidata_description", "description"):
        if raw.get(key):
            return raw[key], "nodes.data." + key
    return node["description"], "nodes.description"


def _locator(table, row):
    keys = ("child_uid", "parent_uid", "relation", "source", "layer") if table == "edges" else (
        "subject_uid", "object_uid", "relation", "source")
    return {key: row[key] for key in keys} | {"content_sha256": source_assertion_sha256(row)}


def native_catalog_witness(child, parent):
    """Protect actual catalog fields, never an ungrounded 'verified' flag.

    These are independently reviewed source schemas. The exact manufacturer
    record identifier, explicit object-kind field/catalogue and actual parent
    definition must agree. No manufacturer or commercial name is a type.
    """
    raw = json.loads(child["data"] or "{}")
    record = raw.get("source_record", {})
    definition = parent["description"].casefold()
    witness = None
    if child["source"] == "Vishay native parametric catalog":
        native = record.get("P1009") or record.get("P1001")
        catalog = {"vishay-zener": ("vishay-type:zener-diode", "zener"),
                   "vishay-switching": ("vishay-type:small-signal-switching-diode", "switching")}.get(raw.get("source_id"))
        if (catalog and native and record.get("T8270") == "Single"
            and child["uid"] == "vishay-part:" + str(native).lower()
            and raw.get("parent_uid") == parent["uid"] == catalog[0]
            and "diode" in definition and catalog[1] in definition and raw.get("source_sha256")):
            witness = {"source_record_identifier_field": "P1009" if record.get("P1009") else "P1001",
                       "native_identifier": native, "source_catalog_kind": raw["source_id"]}
    # NVIDIA compute capability covers chips, boards and multi-GPU systems.
    # Matching its identifiers does not verify the whole product's GPU type.
    if witness:
        witness.update(source_record_uid=child["uid"], native_record_sha256=sha(child["data"]),
                       reviewed_parent_uid=parent["uid"], parent_definition=parent["description"],
                       parent_definition_sha256=sha(parent["description"]),
                       source_scope_entails_parent=True, source_uri=raw.get("source_uri"),
                       source_snapshot_sha256=raw.get("source_sha256"))
    return witness


def freeze_native_catalogues(c):
    """Actual publisher inventories stay discoverable as explicit directories."""
    groups, members = {}, []
    sources = {"NVIDIA native CUDA GPU model table": "nvidia-cuda-catalogue",
               "Vishay native parametric catalog": "vishay-native-catalogue"}
    for source, namespace in sources.items():
        for row in c.execute("SELECT * FROM nodes WHERE source=? ORDER BY uid", (source,)):
            node = dict(row); raw = json.loads(node["data"] or "{}")
            # Adapter namespaces, never a commercial-name series heuristic.
            prefix = "nvidia-cuda-gpu:" if namespace == "nvidia-cuda-catalogue" else "vishay-part:"
            if not node["uid"].startswith(prefix):
                continue
            record = raw.get("source_record", {})
            native_id = record.get("gpu_model_designation") if namespace == "nvidia-cuda-catalogue" else (record.get("P1009") or record.get("P1001"))
            source_id, snapshot, uri = raw.get("source_id"), raw.get("source_sha256"), raw.get("source_uri")
            if not native_id or not source_id or not snapshot or not uri:
                raise ValueError("Native catalogue directory lacks actual retained source fields: " + node["uid"])
            gid = namespace + ":" + source_id
            group = groups.setdefault(gid, {"group_uid": gid, "namespace": namespace,
                "source_version": "sha256:" + snapshot, "source_group_id": source_id,
                "label": source + " — " + source_id, "parent_group_uid": None, "source_uri": uri,
                "proof": {"kind": "SOURCE_NATIVE_CATALOG_DIRECTORY", "source_id": source_id,
                    "navigation_domains": ["gpus", "computer_hardware", "electronic_devices"] if namespace == "nvidia-cuda-catalogue" else ["semiconductor_diodes", "electronic_components", "source_semiconductor_diodes"],
                    "source_snapshot_sha256": snapshot, "source": source,
                    "source_uri": uri, "is_class_inclusion": False, "is_design_lineage": False,
                    "scope_observation": "The publisher's retained native catalogue grouping; NVIDIA lists CUDA-compatible hardware including multi-GPU systems, and Vishay lists packaged parts and ranges. Catalogue membership does not verify the whole object's physical type, global exact identity, or visual distance.",
                    "license": "Manufacturer copyright retained; factual identifiers and catalogue membership only; no images or full publisher document redistributed"}})
            if group["source_version"] != "sha256:" + snapshot or group["source_uri"] != uri:
                raise ValueError("One native directory ID has incompatible snapshots")
            members.append({"group_uid": gid, "member_uid": node["uid"], "source_member_id": str(native_id),
                "relation": "CATALOG_ENTRY", "status": "SOURCE_DECLARED", "proof": {
                    "source_record_uid": node["uid"], "native_record_sha256": sha(node["data"]),
                    "source_id": source_id, "source_snapshot_sha256": snapshot, "source_uri": uri,
                    "native_identifier_field": "gpu_model_designation" if namespace == "nvidia-cuda-catalogue" else "P1009" if record.get("P1009") else "P1001",
                    "native_identifier": native_id, "native_family_range": record.get("P1001") if namespace == "vishay-native-catalogue" else None,
                    "native_compute_capability": record.get("compute_capability"), "native_topology": record.get("T8270"),
                    "world_physical_type_verified_by_directory": False, "world_identity_assertion": False,
                    "is_class_inclusion": False, "is_design_lineage": False,
                    "source_organization_group": False}})
    return list(groups.values()), members


def freeze_canon_catalogues(c):
    """Canon's category field defines a directory, not one camera design."""
    groups, members = {}, []
    for row in c.execute("SELECT * FROM nodes WHERE source='Canon Camera Museum' AND uid LIKE 'canon:%' ORDER BY uid"):
        n = dict(row)
        raw = json.loads(n["data"] or "{}")
        attrs = raw.get("attributes", {})
        category, native_id = attrs.get("catalog_category"), attrs.get("native_catalog_id")
        ev = c.execute("SELECT payload FROM evidence WHERE evidence_id=?", (raw.get("evidence_id"),)).fetchone()
        ev = json.loads(ev[0]) if ev else {}
        if not category or not native_id or ev.get("catalog_category") != category or ev.get("native_catalog_id") != native_id or not ev.get("source_sha256"):
            raise ValueError("Canon catalogue source fields changed or are missing")
        group_id = "canon-catalogue:" + sha(category)[:20]
        if group_id not in groups:
            groups[group_id] = {"group_uid": group_id, "namespace": "canon-camera-museum-catalogue",
                "source_version": "sha256:" + ev["source_sha256"], "source_group_id": category,
                "label": "Canon " + category, "parent_group_uid": None, "source_uri": ev["source_uri"],
                "proof": {"kind": "SOURCE_NATIVE_CATALOG_DIRECTORY", "source_id": category,
                    "source_snapshot_sha256": ev["source_sha256"], "source_field": "catalog_category",
                    "navigation_domains": ["cameras", "lenses", "electronic_devices"],
                    "is_class_inclusion": False, "is_design_lineage": False,
                    "scope_observation": "Publisher catalogue product category, including distinct design series; no design family or world type identity is asserted."}}
        members.append({"group_uid": group_id, "member_uid": n["uid"], "source_member_id": native_id,
            "relation": "CATALOG_ENTRY", "status": "SOURCE_DECLARED", "proof": {
                "source_record_uid": n["uid"], "native_record_sha256": sha(n["data"]),
                "source_snapshot_sha256": ev["source_sha256"], "catalog_category": category,
                "native_catalog_id": native_id, "source_uri": raw.get("source_uri"),
                "is_class_inclusion": False, "is_design_lineage": False}})
    return list(groups.values()), members


def freeze_intel_catalogues(c):
    """Actual Intel ARK collection membership is not design lineage."""
    groups, members = {}, []
    for row in c.execute("SELECT * FROM nodes WHERE uid LIKE 'intel-ark:%' ORDER BY uid"):
        n, raw = dict(row), json.loads(row["data"] or "{}")
        record = raw.get("source_record", {})
        parent = _record(c, raw.get("parent_uid"))
        if not parent or not native_collection_witness(c, n | {"role": "MODEL"}, parent):
            continue
        pr = json.loads(parent["data"])
        group_id = "intel-native-catalogue:" + sha(pr["source_record"]["native_collection_uri"])[:20]
        groups.setdefault(group_id, {"group_uid": group_id, "namespace": "intel-ark-native-catalogue",
            "source_version": "sha256:" + raw["source_sha256"], "source_group_id": raw["source_id"],
            "label": pr["source_record"]["title"], "parent_group_uid": None, "source_uri": raw["source_uri"],
            "proof": {"kind": "SOURCE_NATIVE_CATALOG_DIRECTORY", "source_id": raw["source_id"],
                "source_snapshot_sha256": raw["source_sha256"], "native_collection_uri": raw["source_uri"],
                "navigation_domains": ["microprocessors", "computer_hardware", "electronic_components"],
                "is_class_inclusion": False, "is_design_lineage": False,
                "scope_observation": "Publisher native commercial collection listing; no engineering lineage or ordinary class is asserted."}})
        members.append({"group_uid": group_id, "member_uid": n["uid"], "source_member_id": record["intel_ark_id"],
            "relation": "CATALOG_ENTRY", "status": "SOURCE_DECLARED", "proof": {
                "source_record_uid": n["uid"], "native_record_sha256": sha(n["data"]),
                "source_snapshot_sha256": raw["source_sha256"], "intel_ark_id": record["intel_ark_id"],
                "native_collection_uri": raw["source_uri"], "source_uri": record.get("specifications_uri"),
                "is_class_inclusion": False, "is_design_lineage": False}})
    return list(groups.values()), members


def native_collection_witness(c, child, parent):
    """Ground commercial membership without treating it as design lineage.

    A retained P279 assertion plus two design role flags alone cannot establish
    a design lineage. Canon's physical catalogue categories are deliberately
    not protected by the commercial-series rules below.
    """
    raw, pr = json.loads(child["data"] or "{}"), json.loads(parent["data"] or "{}")
    ev = c.execute("SELECT payload FROM evidence WHERE evidence_id=?", (raw.get("evidence_id"),)).fetchone()
    ev = json.loads(ev[0]) if ev else {}
    scope = None
    if child["source"] == "Apple model-identification support" and parent["source"] == child["source"]:
        ids = raw.get("attributes", {}).get("native_model_identifiers")
        if (ids and ids == ev.get("native_model_identifiers") and ev.get("source_sha256")
            and ev.get("source_section_sha256") and raw.get("source_uri") == pr.get("source_uri")
            and "reusable product family" in parent["description"] and parent["role"] == "MODEL_FAMILY"):
            scope = {"basis": "PUBLISHER_IDENTIFICATION_PAGE_AND_EXACT_MODEL_IDENTIFIER_SECTION",
                "native_model_identifiers": ids, "source_snapshot_sha256": ev["source_sha256"],
                "source_section_sha256": ev["source_section_sha256"]}
    if child["source"].startswith("intel-") and parent["source"] == child["source"]:
        record, prec = raw.get("source_record", {}), pr.get("source_record", {})
        if (record.get("intel_ark_id") and raw.get("parent_uid") == parent["uid"]
            and raw.get("source_uri") == prec.get("native_collection_uri")
            and "/products/series/" in (raw.get("source_uri") or "")
            and raw.get("source_sha256") == pr.get("source_sha256")
            and parent["role"] == "MODEL_FAMILY" and "processor family" in parent["description"].lower()):
            scope = {"basis": "PUBLISHER_NATIVE_COMMERCIAL_SERIES_COLLECTION_AND_EXACT_SKU",
                "native_identifier": record["intel_ark_id"], "native_collection_uri": prec["native_collection_uri"],
                "source_snapshot_sha256": raw["source_sha256"]}
    if not scope:
        return None
    return {**scope, "reviewed_rule_verified": True, "human_individual_review": False,
        "is_design_lineage": False, "is_class_inclusion": False, "world_identity_assertion": False,
        "source_record_uid": child["uid"], "reviewed_parent_uid": parent["uid"],
        "native_record_sha256": sha(child["data"]), "parent_native_record_sha256": sha(parent["data"]),
        "parent_definition_sha256": sha(parent["description"]), "source_uri": raw.get("source_uri"),
        "source_scope_entails_parent": True,
        "scope_observation": "Native publisher commercial-series membership is retained; this does not assert evolutionary descent, shared visual granularity or an identity bridge."}


def locate(c, table, locator, *, all_matches=False):
    if table not in {"edges", "entity_relations"}:
        raise ValueError("Unsupported source-contract assertion table")
    keys = ("child_uid", "parent_uid", "relation", "source", "layer") if table == "edges" else (
        "subject_uid", "object_uid", "relation", "source")
    if not locator.get("content_sha256") or not all(locator.get(key) for key in keys):
        raise ValueError("Source contract requires complete frozen locator")
    rows = c.execute("SELECT * FROM " + table + " WHERE " + " AND ".join(key + "=?" for key in keys),
                     tuple(locator[key] for key in keys)).fetchall()
    matches = [row for row in rows if source_assertion_sha256(row) == locator["content_sha256"]]
    if len(matches) != locator.get("source_assertion_multiplicity", 1):
        raise ValueError("Source-contract claim changed, missing or duplicated")
    if all_matches:
        return matches
    if len(matches) != 1:
        raise ValueError("Several identical frozen claims require group disposition")
    return matches[0]


def freeze_sample_dispositions(payload, source_directory, output):
    """Bind independent fixed samples to exact assertion/grain dispositions."""
    reports = []
    for name, source_name in (
        ("original_32_counterexample_dispositions.json", "original-counterexamples.json"),
        ("fixed_106_semantic_sample_dispositions.json", "v1/semantic_sample_decisions.json"),
        ("fixed_102_native_semantic_sample_dispositions.json", "native_semantic_samples.json"),
    ):
        path = source_directory / source_name
        cases = []
        for old in json.loads(path.read_text()):
            uid = old.get("uid") or old.get("subject_uid")
            roles = [r for r in payload["role_operations"] if r["uid"] == uid]
            replacements = [r for r in payload["repairs"] if r["uid"] == uid]
            reviews = [{"table": r["table"], "locator": r["locator"], "status": r["decision"], "reason": r["reason"]}
                       for r in payload["quarantines"] if r["child_source_record"]["uid"] == uid]
            cases.append({"uid": uid, "original_independent_case": old,
                "old_assertion_dispositions": reviews, "new_directional_or_source_membership_claims": replacements,
                "individual_source_grain_review_operations": roles,
                "source_grain_dispositions": [r for r in payload["grain_dispositions"] if r["uid"] == uid],
                "identity_grain_confirmation": "INDIVIDUALLY_REVIEWED" if roles else "NOT_RECONFIRMED_BY_PHYSICAL_TYPE_RULE",
                "remaining_reason": None if roles else "Directional physical type and publisher membership do not automatically confirm world identity range or canonical grain; this remains separately audited."})
        data = {"format": "fineatlas-independent-sample-dispositions-v1", "input_sample_sha256": sha(path.read_bytes()),
                "sample_count": len(cases), "cases": cases}
        target = output / name
        target.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        reports.append({"file": name, "sha256": sha(target.read_bytes()), "sample_count": len(cases)})
    return reports


def prepare_source_contracts(database: Path, output: Path, fixed_review: Path | None = None,
                             scope_protections: Path | None = None, role_reviews: Path | None = None,
                             independent_review_directory: Path | None = None):
    output.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect("file:" + str(database.resolve()) + "?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA temp_store=MEMORY")
    c.execute("PRAGMA cache_size=-262144")
    ledger, repairs, protected = [], {}, []
    role_operations, reviewed_roles, blocked_roles = _load_role_reviews(c, role_reviews)
    external_protections = json.loads(scope_protections.read_text()) if scope_protections else []
    protections = {(r["table"], r["locator"]["content_sha256"]): r["proof"] for r in external_protections}
    if len(protections) != len(external_protections):
        raise ValueError("Repeated individual scope protection")
    grain_dispositions = {}
    catalog_groups, catalog_members = freeze_native_catalogues(c)
    canon_groups, canon_members = freeze_canon_catalogues(c)
    catalog_groups.extend(canon_groups)
    catalog_members.extend(canon_members)
    intel_groups, intel_members = freeze_intel_catalogues(c)
    catalog_groups.extend(intel_groups)
    catalog_members.extend(intel_members)
    for catalog_row in catalog_groups + catalog_members:
        catalog_row["proof"].update(world_physical_type_verified_by_directory=False, world_identity_assertion=False)
    counts = Counter()
    anchors = {}
    for _, uid, prefix in GENERA:
        n = _record(c, uid)
        if not n or n["role"] != "CLASS" or not n["description"].startswith(prefix):
            raise ValueError("Reviewed physical genus source definition drifted: " + uid)
        anchors[uid] = {"uid": uid, "definition": n["description"], "definition_sha256": sha(n["description"]),
                        "raw_sha256": sha(n["data"]), "source": n["source"]}
    sql_sources = ",".join("?" for _ in LEXICAL_SOURCES)
    for table, child_key, parent_key, relation_filter in (
        ("edges", "child_uid", "parent_uid", "relation='IS_A'"),
        ("entity_relations", "subject_uid", "object_uid", "relation IN ('DESIGN_TYPE_OF','INSTANCE_OF','CONFIGURATION_TYPE_OF')"),
        ("entity_relations", "subject_uid", "object_uid", "relation='NATIVE_DESIGN_PARENT'"),
    ):
        native_design = relation_filter == "relation='NATIVE_DESIGN_PARENT'"
        cohort_sources = NATIVE_TRANSFORM_SOURCES if native_design else LEXICAL_SOURCES
        query = ("SELECT * FROM " + table + " WHERE status='ACTIVE' AND " + relation_filter +
                 " AND source IN (" + ",".join("?" for _ in cohort_sources) + ") ORDER BY id")
        for sqlite_row in c.execute(query, tuple(sorted(cohort_sources))):
            row = dict(sqlite_row)
            child, parent = _record(c, row[child_key]), _record(c, row[parent_key])
            if not child or not parent:
                raise ValueError("Derived source assertion has dangling endpoint")
            statement, statement_field = _statement(child, row)
            child["role"] = reviewed_roles.get(child["uid"], child["role"])
            parent["role"] = reviewed_roles.get(parent["uid"], parent["role"])
            proof = json.loads(row["data"] or "{}").get("admission_basis", {})
            # Only an explicit actual reviewed scope assertion, with its exact
            # source UID and BOTH endpoint definitions, can protect a claim.
            commercial_witness = native_collection_witness(c, child, parent) if native_design else None
            native_witness = None if native_design else native_catalog_witness(child, parent)
            supplied = protections.get((table, source_assertion_sha256(row)))
            if supplied:
                if not (supplied.get("individual_semantic_review") and supplied.get("scope_observation")
                    and supplied.get("source_scope_entails_parent") is True
                    and supplied.get("source_record_uid") == child["uid"]
                    and supplied.get("reviewed_parent_uid") == parent["uid"]
                    and supplied.get("native_record_sha256") == sha(child["data"])
                    and supplied.get("parent_native_record_sha256") == sha(parent["data"])
                    and supplied.get("parent_definition_sha256") == sha(parent["description"])
                    and supplied.get("primary_sources") and supplied.get("external_snapshot_sha256")):
                    raise ValueError("Individual primary source scope protection does not bind actual endpoints")
                external = Path(supplied["external_snapshot_file"])
                if not external.is_file() or sha(external.read_bytes()) != supplied["external_snapshot_sha256"]:
                    raise ValueError("Individual source scope snapshot missing or changed")
                native_witness = supplied
            reviewed = native_witness or (proof.get("individual_semantic_review") and proof.get("scope_observation")
                        and proof.get("source_record_uid") == child["uid"]
                        and proof.get("reviewed_parent_uid") == parent["uid"]
                        and proof.get("parent_definition_sha256") == sha(parent["description"])
                        and proof.get("native_record_sha256") == sha(child["data"])
                        and proof.get("source_scope_entails_parent") is True)
            record = {"table": table, "locator": _locator(table, row), "original_source_assertion": row,
                      "child_source_record": child, "parent_source_record": parent,
                      "child_raw_sha256": sha(child["data"]), "parent_raw_sha256": sha(parent["data"]),
                      "source_statement": statement, "source_statement_field": statement_field,
                      "independent_native_scope_witness": native_witness,
                      "decision": "PROTECTED_INDEPENDENT_SCOPE_WITNESS" if reviewed else REVIEW_STATUS,
                      "reason": "A retained statement/hash/role and an alias match do not independently verify the selected parent sense or whole-subject scope. Review concerns only this parent assertion, not every relation of either entity.",
                      "asserted_semantically_false": False}
            if native_design:
                record["reason"] = "The retained source subtype assertion and endpoint design roles do not independently prove design-family, variant or generation membership. This directional design assertion is reviewed; the original source statement, endpoints, ordinary native classifications and regulatory relations are retained."
                record["reviewed_relation_scope"] = "NATIVE_DESIGN_PARENT"
            if reviewed:
                protected.append(record)
                counts["protected_reviewed_claims"] += 1
                continue
            ledger.append(record)
            counts[table + "_quarantined"] += 1
            counts["source:" + row["source"]] += 1
            if native_design and commercial_witness and child["source"] == "Apple model-identification support":
                key = (child["uid"], parent["uid"], "SERIES_MEMBER_OF")
                repairs[key] = {"uid": child["uid"], "parent": parent["uid"], "relation": "SERIES_MEMBER_OF",
                    "source": "Apple source-native commercial product-line membership", "uri": commercial_witness["source_uri"],
                    "proof": {**commercial_witness, "basis": "PUBLISHER_EXACT_MODEL_SECTION_TO_COMMERCIAL_PRODUCT_LINE",
                        "kind": "PUBLISHER_DECLARED_COMMERCIAL_LINE_MEMBERSHIP",
                        "identity_scope": "SOURCE_NATIVE_COMMERCIAL_LINE", "is_design_lineage": False,
                        "is_class_inclusion": False, "is_visual_distance": False,
                        "actual_relation": "SERIES_MEMBER_OF", "original_claim_locators": [record["locator"]]}}
            genus = own_subject_genus(statement, child["label"])
            attrs = c.execute("SELECT attributes FROM node_profiles WHERE uid=?", (child["uid"],)).fetchone()
            attrs = json.loads(attrs[0]) if attrs else {}
            class_scope_confirmed = (child["uid"] in reviewed_roles and reviewed_roles[child["uid"]] == "CLASS") or attrs.get("canonical_scope_guard") == "GENERIC_PHYSICAL_KIND"
            if child["role"] == "CLASS" and not class_scope_confirmed:
                grain_dispositions[child["uid"]] = {"uid": child["uid"], "canonical_role": "CLASS", "decision": "NEW_IS_A_REJECTED_UNCONFIRMED_ORDINARY_CLASS_SCOPE", "reason": "An explicit physical genus does not prove the subject is an ordinary reusable category. Retained CLASS metadata alone cannot authorize new IS_A; commercial designs, standards and instances require separate scope adjudication.", "source_statement": statement, "native_record_sha256": sha(child["data"])}
                continue
            if child["role"] == "MODEL_FAMILY" and child["uid"] not in reviewed_roles and not own_family_scope(statement, child["label"]):
                grain_dispositions[child["uid"]] = {"uid": child["uid"], "canonical_role": "MODEL_FAMILY",
                    "decision": "NEW_DESIGN_TYPE_REJECTED_UNCONFIRMED_OWN_SUBJECT_FAMILY_SCOPE",
                    "reason": "The selected whole-subject source clause does not declare this subject to be a family/series/line/range. Mentioning another object's family or retained MODEL_FAMILY metadata cannot authorize the grain.",
                    "source_statement": statement, "native_record_sha256": sha(child["data"])}
                continue
            if child["uid"] in reviewed_roles:
                grain_dispositions[child["uid"]] = {"uid": child["uid"], "canonical_role": child["role"], "decision": "INDIVIDUALLY_REVIEWED_SCOPE_AND_EXACT_ID_PEERS", "native_record_sha256": sha(child["data"])}
            if genus and child["visibility"] == "ACTIVE" and child["role"] in {"MODEL", "MODEL_FAMILY", "CLASS", "INSTANCE", "CONFIGURATION"}:
                term, anchor_uid = genus
                relation = {"CLASS": "IS_A", "MODEL": "DESIGN_TYPE_OF", "MODEL_FAMILY": "DESIGN_TYPE_OF",
                            "INSTANCE": "INSTANCE_OF", "CONFIGURATION": "CONFIGURATION_TYPE_OF"}[child["role"]]
                if child["uid"] == anchor_uid:
                    continue
                key = (child["uid"], anchor_uid, relation)
                if key not in repairs:
                    repairs[key] = {"uid": child["uid"], "parent": anchor_uid, "relation": relation,
                        "source": SOURCE_NAME, "uri": (json.loads(child["data"] or "{}").get("source_uri") or
                            "https://www.wikidata.org/wiki/" + child["uid"].split(":")[-1]),
                        "proof": {"basis": "EXPLICIT_WHOLE_SUBJECT_PHYSICAL_GENUS_WITH_FROZEN_NATIVE_SENSE",
                            "individual_semantic_review": False, "reviewed_rule_verified": True,
                            "human_individual_review": False,
                            "reviewed_rule_id": "whole-subject-genus-v2", "source_record_uid": child["uid"],
                            "native_record_sha256": sha(child["data"]), "source_statement": statement,
                            "statement_field": statement_field, "matched_explicit_genus": term,
                            "reviewed_parent_uid": anchor_uid, "parent_definition": anchors[anchor_uid]["definition"],
                            "parent_definition_sha256": anchors[anchor_uid]["definition_sha256"],
                            "source_scope_entails_parent": True, "scope_observation": "Reviewed literal main-subject physical genus, excluding named arguments, relative/purpose/location clauses and ambiguous lexical senses. This is only a directional type relation, not a world identity assertion or visual separability claim.",
                            "license": "Original source attribution retained; WordNet license; Wikidata CC0 facts and encyclopedia attribution where retained",
                            "original_claim_locators": []}}
                repairs[key]["proof"]["original_claim_locators"].append(record["locator"])
    # Role corrections have an independent full-subject record and actual
    # reviewed parent definition, rather than a successful lexical head match.
    for case in json.loads(role_reviews.read_text()) if role_reviews else []:
        uid, target = case["uid"], case.get("type_parent_uid")
        if uid not in reviewed_roles or not target:
            continue
        parent = _record(c, target)
        if not parent or reviewed_roles.get(target, parent["role"]) != "CLASS":
            blocked_roles.append({"uid": uid, "status": "REVIEW_ACTUAL_PHYSICAL_PARENT_SCOPE", "parent": target})
            continue
        if sha(parent["data"]) != case["proof"]["parent_native_record_sha256"] or parent["description"] != case["proof"]["parent_definition"]:
            raise ValueError("Individual physical-parent record changed")
        for op in role_operations:
            if op["proof"]["reviewed_subject_uid"] != uid:
                continue
            peer = _record(c, op["uid"])
            relation = {"CLASS": "IS_A", "MODEL": "DESIGN_TYPE_OF", "MODEL_FAMILY": "DESIGN_TYPE_OF", "INSTANCE": "INSTANCE_OF"}[op["role"]]
            if peer["component_id"] == parent["component_id"]:
                blocked_roles.append({"uid": peer["uid"], "status": "REVIEW_IDENTITY_WITH_ACTUAL_PHYSICAL_PARENT", "parent": target})
                continue
            p = {**case["proof"], "basis": "INDIVIDUALLY_REVIEWED_WHOLE_SUBJECT_GRAIN_AND_ACTUAL_PHYSICAL_TYPE",
                 "native_record_sha256": sha(peer["data"]), "source_record_uid": peer["uid"],
                 "reviewed_subject_uid": uid, "reviewed_parent_uid": target,
                 "parent_definition_sha256": sha(parent["description"]), "source_scope_entails_parent": True,
                 "human_individual_review": True, "role": op["role"], "original_claim_locators": []}
            repairs[(peer["uid"], target, relation)] = {"uid": peer["uid"], "parent": target, "relation": relation,
                "source": "Individually frozen whole-subject physical type", "uri": case["uri"], "proof": p}
            grain_dispositions[peer["uid"]] = {"uid": peer["uid"], "canonical_role": op["role"], "decision": "INDIVIDUALLY_REVIEWED_SCOPE_AND_EXACT_ID_PEERS", "proof": op["proof"]}
    # Any old ordinary inclusion incident to a newly adjudicated non-class
    # endpoint must also be held for review, irrespective of its source name.
    seen_claims = {(x["table"], x["original_source_assertion"]["id"]) for x in ledger + protected}
    from .hierarchy import LINK_ROLES
    for uid in sorted(reviewed_roles):
        for table, left, right in (("edges", "child_uid", "parent_uid"), ("entity_relations", "subject_uid", "object_uid")):
            for raw_row in c.execute("SELECT * FROM " + table + " WHERE status='ACTIVE' AND (" + left + "=? OR " + right + "=?)", (uid, uid)):
                row = dict(raw_row)
                if (table, row["id"]) in seen_claims:
                    continue
                a, b = _record(c, row[left]), _record(c, row[right])
                ar, br = reviewed_roles.get(a["uid"], a["role"]), reviewed_roles.get(b["uid"], b["role"])
                allowed = LINK_ROLES.get(row["relation"])
                if row["relation"] == "IS_A":
                    invalid = ar != "CLASS" or br != "CLASS"
                else:
                    invalid = bool(allowed and (ar not in allowed[0] or br not in allowed[1]))
                if not invalid:
                    continue
                ledger.append({"table": table, "locator": _locator(table, row), "original_source_assertion": row,
                    "child_source_record": a, "parent_source_record": b, "child_raw_sha256": sha(a["data"]), "parent_raw_sha256": sha(b["data"]),
                    "source_statement": next(op["proof"]["source_statement"] for op in role_operations if op["uid"] == uid), "source_statement_field": "Individual whole-subject review",
                    "decision": REVIEW_STATUS, "reason": "Individually verified whole-subject grain is incompatible with this former relation's endpoint role contract; original relation and source payload are retained.",
                    "asserted_semantically_false": False, "current_reviewed_roles": [ar, br]})
                counts[table + "_quarantined"] += 1
                counts["source:" + row["source"]] += 1
                seen_claims.add((table, row["id"]))
    # Truly identical source rows form one frozen multiplicity group. Every
    # record is retained; a uniform review disposition does not pick an alias
    # or choose the first of ambiguous, different evidence claims.
    groups = {}
    for record in ledger + protected:
        key = (record["table"], canonical(record["locator"]))
        groups.setdefault(key, record)
    for (table, key), record in groups.items():
        locator = record["locator"]
        keys = ("child_uid", "parent_uid", "relation", "source", "layer") if table == "edges" else (
            "subject_uid", "object_uid", "relation", "source")
        source_rows = c.execute("SELECT * FROM " + table + " WHERE " + " AND ".join(k + "=?" for k in keys),
                                tuple(locator[k] for k in keys)).fetchall()
        count = sum(source_assertion_sha256(row) == locator["content_sha256"] for row in source_rows)
        groups[(table, key)] = count
    for record in ledger + protected:
        record["locator"]["source_assertion_multiplicity"] = groups[(record["table"], canonical(record["locator"]))]
    # Replacement provenance pointers also retain the exact observed count.
    for repair in repairs.values():
        for locator in repair["proof"]["original_claim_locators"]:
            # Shared locator object has already been annotated above.
            if not locator.get("source_assertion_multiplicity"):
                raise ValueError("Missing exact source-assertion multiplicity")
    # A different claim about the same source UID must not supply an alternate
    # route around an unresolved whole-subject family grain. Human scope
    # adjudications and publisher membership retain their separate contracts.
    rejected_family_uids = {uid for uid, d in grain_dispositions.items()
                            if d["decision"].startswith("NEW_DESIGN_TYPE_REJECTED")}
    for key in list(repairs):
        if key[0] in rejected_family_uids and repairs[key]["source"] == SOURCE_NAME:
            del repairs[key]
            counts["alternate_claim_type_routes_withheld_for_family_scope"] += 1
    fixed = json.loads(fixed_review.read_text()) if fixed_review else None
    payload = {"format": "fineatlas-source-contracts-v1", "baseline_database": str(database),
               "quarantines": ledger, "protected": protected, "repairs": list(repairs.values()),
               "role_operations": role_operations, "grain_dispositions": list(grain_dispositions.values()),
               "source_catalog_groups": catalog_groups, "source_catalog_members": catalog_members,
               "source_membership_repairs": [r for r in repairs.values() if r["relation"] == "SERIES_MEMBER_OF"],
               "blocked_role_reviews": blocked_roles,
               "external_scope_protections_sha256": sha(scope_protections.read_bytes()) if scope_protections else None,
               "reviewed_role_cases_sha256": sha(role_reviews.read_bytes()) if role_reviews else None,
               "reviewed_genus_anchors": list(anchors.values()), "source_cohorts": sorted(LEXICAL_SOURCES),
               "native_transformation_source_cohorts": sorted(NATIVE_TRANSFORM_SOURCES),
               "fixed_review_report_sha256": sha(fixed_review.read_bytes()) if fixed_review else None,
               "confirmed_counterexamples": fixed.get("semantic_findings", []) if fixed else [],
               "summary": dict(counts) | {"reviewed_genus_replacement_claims": len(repairs),
                   "directional_physical_type_replacements": sum(r["relation"] != "SERIES_MEMBER_OF" for r in repairs.values()),
                   "source_native_commercial_series_memberships": sum(r["relation"] == "SERIES_MEMBER_OF" for r in repairs.values()),
                   "unique_source_uids_affected": len({r["child_source_record"]["uid"] for r in ledger}),
                   "new_class_genus_links_rejected_without_ordinary_scope": sum(r["decision"].startswith("NEW_IS_A_REJECTED") for r in grain_dispositions.values()),
                   "individual_role_operations": len(role_operations), "blocked_identity_peer_role_reviews": len(blocked_roles),
                   "native_catalog_directory_groups": len(catalog_groups), "native_catalog_directory_source_uids": len(catalog_members),
                   "native_design_transformed_claims_reviewed": sum(r.get("reviewed_relation_scope") == "NATIVE_DESIGN_PARENT" for r in ledger),
                   "native_design_transformed_claims_protected": sum(r.get("reviewed_relation_scope") == "NATIVE_DESIGN_PARENT" for r in protected),
                   "new_family_type_links_rejected_without_subject_scope": sum(r["decision"].startswith("NEW_DESIGN_TYPE_REJECTED") for r in grain_dispositions.values()),
                   "regulatory_and_independently_frozen_epa_fgvc_native_relations_untouched": True,
                   "quarantines_are_review_not_new_knowledge": True}}
    if independent_review_directory:
        payload["frozen_independent_sample_dispositions"] = freeze_sample_dispositions(payload, independent_review_directory, output)
    (output / INPUT_NAME).write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    (output / "structure_source_contracts_summary.json").write_text(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    c.close()
    return payload["summary"]


def apply_source_contracts(m):
    """Recheck every complete source claim before mutation; ID-independent replay."""
    path = m.inputs / INPUT_NAME
    if not path.exists():
        path = m.inputs / (INPUT_NAME + ".gz")
        if not path.exists():
            return {"status": "not_requested"}
    raw_input = path.read_bytes()
    fingerprint = sha(raw_input)
    payload = json.loads(gzip.decompress(raw_input) if path.suffix == ".gz" else raw_input)
    for member in payload.get("source_catalog_members", []):
        current = m.c.execute("SELECT data FROM nodes WHERE uid=?", (member["member_uid"],)).fetchone()
        if not current or sha(current[0]) != member["proof"]["native_record_sha256"]:
            raise ValueError("Native catalogue member source record changed")
    for op in payload.get("role_operations", []):
        n = _record(m.c, op["uid"])
        if not n or sha(n["data"]) != op["proof"]["native_record_sha256"]:
            raise ValueError("Frozen whole-subject role source changed")
        peers = [r[0] for r in m.c.execute("SELECT uid FROM nodes WHERE component_id=? ORDER BY uid", (n["component_id"],))]
        if peers != sorted(op["proof"]["identity_member_uids"]):
            raise ValueError("Reviewed exact-ID identity peer set changed")
    resolved = []
    seen_rows = set()
    for review in payload["quarantines"]:
        matches = locate(m.c, review["table"], review["locator"], all_matches=True)
        for key, expected_key in (("child_source_record", "child_raw_sha256"),
                                  ("parent_source_record", "parent_raw_sha256")):
            uid = review[key]["uid"]
            current = m.c.execute("SELECT data FROM nodes WHERE uid=?", (uid,)).fetchone()
            if not current or sha(current[0]) != review[expected_key]:
                raise ValueError("Frozen source record drift: " + uid)
        for row in matches:
            key = (review["table"], row["id"])
            if key not in seen_rows:
                resolved.append((review, row))
                seen_rows.add(key)
    for anchor in payload["reviewed_genus_anchors"]:
        n = _record(m.c, anchor["uid"])
        if not n or n["role"] != "CLASS" or sha(n["data"]) != anchor["raw_sha256"] or sha(n["description"]) != anchor["definition_sha256"]:
            raise ValueError("Reviewed genus anchor source/scope drift")
    result = Counter()
    for group in payload.get("source_catalog_groups", []):
        fields = ("group_uid", "namespace", "source_version", "source_group_id", "label", "parent_group_uid", "source_uri")
        values = tuple(group[key] for key in fields) + (canonical(group["proof"]),)
        old = m.c.execute("SELECT * FROM source_groups WHERE group_uid=?", (group["group_uid"],)).fetchone()
        if old:
            if tuple(old) != values:
                raise ValueError("Existing native catalogue directory differs")
            result["catalogue_groups_already_present"] += 1
        else:
            m.c.execute("INSERT INTO source_groups VALUES (?,?,?,?,?,?,?,?)", values)
            result["native_catalogue_directories"] += 1
    for member in payload.get("source_catalog_members", []):
        fields = ("group_uid", "member_uid", "source_member_id", "relation", "status")
        values = tuple(member[key] for key in fields) + (canonical(member["proof"]),)
        old = m.c.execute("SELECT * FROM source_group_members WHERE group_uid=? AND member_uid=?", values[:2]).fetchone()
        if old:
            if tuple(old) != values:
                raise ValueError("Existing native catalogue membership differs")
            result["catalogue_entries_already_present"] += 1
        else:
            m.c.execute("INSERT INTO source_group_members VALUES (?,?,?,?,?,?)", values)
            result["native_catalogue_entries"] += 1
    for review in payload["protected"]:
        rows = locate(m.c, review["table"], review["locator"], all_matches=True)
        if not all(row["status"] == "ACTIVE" for row in rows):
            raise ValueError("Protected scope assertion was unexpectedly retired")
        for key, expected_key in (("child_source_record", "child_raw_sha256"), ("parent_source_record", "parent_raw_sha256")):
            current = m.c.execute("SELECT data FROM nodes WHERE uid=?", (review[key]["uid"],)).fetchone()
            if not current or sha(current[0]) != review[expected_key]:
                raise ValueError("Protected scope source drift")
        witness = review.get("independent_native_scope_witness")
        if witness:
            eid = m.evidence("Individually source-scoped parent protection", witness.get("source_uri") or
                             review["child_source_record"]["uid"], witness, "PARENT_SCOPE_PROTECTION")
            key = sha(canonical({"table": review["table"], "locator": review["locator"], "evidence_id": eid}))
            if not m.c.execute("SELECT 1 FROM hierarchy_decisions WHERE id=?", (key,)).fetchone():
                m.c.execute("INSERT INTO hierarchy_decisions VALUES (?,?,?,?,?,?)", (key, "protect_source_claim",
                            review["child_source_record"]["uid"], review["parent_source_record"]["uid"], eid,
                            canonical({"table": review["table"], "locator": review["locator"], "proof": witness})))
                m.change("source_semantic_contract", "scope_protection", key, {}, {"status": "ACTIVE"}, witness)
                result["new_independent_scope_protections"] += 1
    for review, row in resolved:
        table = review["table"]
        if row["status"] == REVIEW_STATUS:
            result["claims_already_reviewed"] += 1
            continue
        if row["status"] != "ACTIVE":
            result["claims_already_superseded"] += 1
            continue
        m.c.execute("UPDATE " + table + " SET status=? WHERE id=?", (REVIEW_STATUS, row["id"]))
        m.change("source_semantic_contract", table, row["id"], dict(row),
                 {"status": REVIEW_STATUS}, {"basis": "UNREVIEWED_LEXICAL_PARENT_SCOPE",
                    "source_assertion_locator": review["locator"], "review_reason": review["reason"],
                    "asserted_semantically_false": False, "candidate_input_sha256": fingerprint})
        result[table + "_reviewed"] += 1
    # Review does not kill an entity. Literal main-subject evidence may support
    # a separate narrower claim with an actually reviewed physical sense.
    from .hierarchy import apply_refinements
    role_path = m.inputs / "structure_source_contracts_roles.jsonl"
    expected_roles = [{"op": "role", **op} for op in payload.get("role_operations", [])]
    actual_roles = [json.loads(line) for line in role_path.read_text().splitlines() if line] if role_path.exists() else []
    if actual_roles != expected_roles:
        raise ValueError("Frozen whole-subject grain operations differ")
    for op in actual_roles:
        current = m.c.execute("SELECT r.canonical_role,r.source,e.payload FROM normalization_roles r LEFT JOIN evidence e ON e.evidence_id=r.evidence_id WHERE r.uid=?", (op["uid"],)).fetchone()
        if current and current["canonical_role"] == op["role"] and current["source"] == op["source"] and current["payload"] and json.loads(current["payload"]) == op["proof"]:
            result["role_reviews_already_applied"] += 1
            continue
        n = _record(m.c, op["uid"])
        if not n or sha(n["data"]) != op["proof"]["native_record_sha256"]:
            raise ValueError("Frozen whole-subject role source changed")
        m.role(op["uid"], op["role"], op["proof"], op["source"], op["uri"])
        result["individual_role_reviews_applied"] += 1
    operations = []
    for repair in payload["repairs"]:
        child, parent = _record(m.c, repair["uid"]), _record(m.c, repair["parent"])
        if not child or not parent:
            raise ValueError("Missing reviewed physical-type endpoint")
        relation = "SERIES_MEMBER_OF" if repair["relation"] == "SERIES_MEMBER_OF" else {"CLASS": "IS_A", "MODEL": "DESIGN_TYPE_OF", "MODEL_FAMILY": "DESIGN_TYPE_OF",
                    "INSTANCE": "INSTANCE_OF", "CONFIGURATION": "CONFIGURATION_TYPE_OF"}.get(child["role"])
        if not relation or child["visibility"] != "ACTIVE":
            result["replacement_requires_current_endpoint_scope_review"] += 1
            continue
        validate_link_roles(relation, child["role"], parent["role"])
        op = {"op": "link", **repair, "relation": relation}
        operations.append(op)
    # Migration writes only a frozen file supplied with the manifest. Do not
    # create or rewrite shared input files while an active build is running.
    frozen_path = m.inputs / "structure_source_contracts_operations.jsonl"
    frozen = [json.loads(line) for line in frozen_path.read_text().splitlines() if line]
    if [{k: v for k, v in op.items() if k != "relation"} for op in frozen] != [
            {k: v for k, v in op.items() if k != "relation"} for op in operations]:
        raise ValueError("Frozen source-contract replacement operations differ")
    if any(a["relation"] != b["relation"] for a, b in zip(frozen, operations)):
        raise ValueError("Current endpoint role changed; refreeze reviewed relations explicitly")
    result.update(apply_refinements(m, frozen_path.name))
    return dict(result)
