"""Current nested executors retain original checks and explicit actual receipts."""
import ast
import importlib
import json
from pathlib import Path
import sqlite3
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))


def function_tree(filename,name):
    body=ast.parse((ROOT/'scripts'/filename).read_text()).body
    return next(node for node in body if isinstance(node,(ast.FunctionDef,ast.ClassDef))and node.name==name)


class NinthNestedInterfaces(unittest.TestCase):
    def test_entire_raw_source_digest_retains_original_algorithm(self):
        self.assertEqual(ast.dump(function_tree('audit_eighth_owned_source_preservation.py','digest_rows')),
            ast.dump(function_tree('audit_ninth_owned_source_preservation.py','digest_rows')))

    def test_source_contract_all_original_independent_predicates_are_unchanged(self):
        old=ast.parse((ROOT/'scripts/audit_eighth_source_contract_candidate.py').read_text())
        new=ast.parse((ROOT/'scripts/audit_ninth_source_contract_candidate.py').read_text())
        functions={node.name:node for node in new.body if isinstance(node,ast.FunctionDef)}
        for node in old.body:
            if isinstance(node,ast.FunctionDef)and node.name not in {'audit','main'}:
                with self.subTest(predicate=node.name):self.assertEqual(ast.dump(node),ast.dump(functions[node.name]))

    def test_cars_all_original_scope_projection_and_no_index_leak_helpers_are_unchanged(self):
        old=ast.parse((ROOT/'scripts/audit_temporal_cars_projection_view_repairs.py').read_text())
        new=ast.parse((ROOT/'scripts/audit_temporal_ninth_cars_projection_view_repairs.py').read_text())
        functions={node.name:node for node in new.body if isinstance(node,ast.FunctionDef)}
        for node in old.body:
            if isinstance(node,ast.FunctionDef)and node.name!='run':
                with self.subTest(predicate=node.name):self.assertEqual(ast.dump(node),ast.dump(functions[node.name]))

    def test_source7_all_original_scope_predicates_are_unchanged(self):
        old=ast.parse((ROOT/'scripts/audit_temporal_eighth_owned_scope_repairs.py').read_text())
        new=ast.parse((ROOT/'scripts/audit_temporal_ninth_owned_scope_repairs.py').read_text())
        functions={node.name:node for node in new.body if isinstance(node,ast.FunctionDef)}
        for node in old.body:
            if isinstance(node,ast.FunctionDef)and node.name!='run':
                with self.subTest(predicate=node.name):self.assertEqual(ast.dump(node),ast.dump(functions[node.name]))

    def test_all_nested_executors_require_explicit_nominal_actual_argument(self):
        for name in ('audit_temporal_ninth_owned_scope_repairs.py','audit_ninth_owned_source_preservation.py',
                     'audit_ninth_source_contract_candidate.py','audit_temporal_ninth_cars_projection_view_repairs.py'):
            text=(ROOT/'scripts'/name).read_text();tree=ast.parse(text)
            calls=[node for node in ast.walk(tree)if isinstance(node,ast.Call)
                   and isinstance(node.func,ast.Attribute)and node.func.attr=='add_argument'
                   and node.args and isinstance(node.args[0],ast.Constant)and node.args[0].value=='--nominal-scope-audit']
            with self.subTest(executor=name):
                self.assertEqual(len(calls),1)
                self.assertTrue(any(key.arg=='required'and isinstance(key.value,ast.Constant)and key.value.value is True for key in calls[0].keywords))

    def test_preservation_nested_command_has_all_actual_dependencies_and_new_source3_guard(self):
        text=(ROOT/'scripts/audit_ninth_owned_source_preservation.py').read_text()
        self.assertIn("'audit_temporal_ninth_complete_subject_scope_repairs.py'",text)
        self.assertIn('require_temporal_ninth_subject_receipt(report, database, inputs, revision, ROOT)',text)
        self.assertIn("'--owned-audit',str(owned_audit),'--complete-owned-audit',str(complete_owned_audit),'--nominal-scope-audit',str(nominal_scope_audit)",text)
        self.assertNotIn('audit_temporal_eighth_complete_subject_scope_repairs.py',text)


class ExactCurrentSourceRowControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.contract=importlib.import_module('structure_ninth_owned_scope_temporal_contract')
    def setUp(self):
        self.c=sqlite3.connect(':memory:');self.c.row_factory=sqlite3.Row;self.addCleanup(self.c.close)
        self.c.execute('CREATE TABLE edges(id INTEGER,child_uid TEXT,parent_uid TEXT,relation TEXT,status TEXT,data TEXT,source TEXT,reason TEXT)')
        self.c.execute('CREATE TABLE usability_changes(stage TEXT,object_type TEXT,object_id TEXT,before_json TEXT,after_json TEXT,evidence TEXT)')
        self.before={'id':13,'child_uid':'own','parent_uid':'narrow','relation':'IS_A','status':'ACTIVE','data':'{"exact":"oldsource"}','source':'original source','reason':'original reason'}
        self.after={**self.before,'status':'SOURCE_SCOPE_REVIEW'}
        self.op={'op':'review_class_edge','before_assertion':self.before,'after_status':'SOURCE_SCOPE_REVIEW','proof':{'scope':'whole independently approved'}}
        self.c.execute('INSERT INTO edges VALUES(?,?,?,?,?,?,?,?)',list(self.after.values()))
        self.c.execute('INSERT INTO usability_changes VALUES(?,?,?,?,?,?)',('nominal_design_scope_repairs','class_scope_review','13',json.dumps(self.before),json.dumps({'status':'SOURCE_SCOPE_REVIEW'}),json.dumps(self.op['proof'])))
    def call(self,before=None,operations=None):return self.contract.exact_nominal_after(self.c,[self.op]if operations is None else operations,'edges',self.before if before is None else before)
    def test_exact_fullrow_class_retirement_and_unique_history_pass(self):
        after,op=self.call();self.assertEqual(after,self.after);self.assertEqual(op,self.op)
    def test_an_unrelated_old_row_gets_no_wildcard_retirement_permission(self):
        before={**self.before,'id':99};after,op=self.call(before);self.assertEqual(after,before);self.assertIsNone(op)
    def test_changed_old_data_or_source_is_not_a_nominal_permission(self):
        for field in ('data','source','reason'):
            with self.subTest(field=field),self.assertRaises(ValueError):self.call({**self.before,field:'changed'})
    def test_current_review_cannot_discard_original_source_reason(self):
        self.c.execute('UPDATE edges SET reason=NULL')
        with self.assertRaises(ValueError):self.call()
    def test_missing_or_duplicate_history_is_rejected(self):
        self.c.execute('INSERT INTO usability_changes SELECT *FROM usability_changes')
        with self.assertRaises(ValueError):self.call()
        self.c.execute('DELETE FROM usability_changes')
        with self.assertRaises(ValueError):self.call()
    def test_duplicate_permission_is_rejected(self):
        with self.assertRaises(ValueError):self.call(operations=[self.op,self.op])

    def test_transition_inventory_is_derived_from_complete_original_rows(self):
        original={'op':'link','uid':'own','parent':'narrow','relation':'IS_A','source':'original source','proof':{'prior_assertions':[{'before':self.before}]}}
        op={**self.op,'uid':'own','parent':'narrow','relation':'IS_A'}
        self.assertEqual(self.contract.referenced_nominal_transitions([original],[op]),[('edges',self.before)])
        self.assertEqual(self.contract.referenced_nominal_transitions([], [op]),[])

    def test_source7_requires_current_new_source8_audit_before_original_constructor(self):
        self.c.execute('CREATE TABLE metadata(key TEXT,value TEXT)');self.c.execute('INSERT INTO metadata VALUES("database_revision",?)',(json.dumps('actual'),))
        with patch.object(self.contract,'require_complete_type_receipt',side_effect=ValueError('preflight is not actual')),patch.object(self.contract.EighthOwnedTemporalContract,'__init__')as old:
            with self.assertRaises(ValueError):self.contract.NinthOwnedTemporalContract(self.c,'actual.sqlite','inputs','preflight.json','nominal.json')
            old.assert_not_called()

    def test_source7_requires_current_nominal_audit_and_rejects_unfrozen_fixture(self):
        self.c.execute('CREATE TABLE metadata(key TEXT,value TEXT)');self.c.execute('INSERT INTO metadata VALUES("database_revision",?)',(json.dumps('actual'),))
        with patch.object(self.contract,'require_complete_type_receipt'),patch.object(self.contract,'load_nominal_operations',side_effect=ValueError('missing nominal actual')),patch.object(self.contract.EighthOwnedTemporalContract,'__init__')as old:
            with self.assertRaises(ValueError):self.contract.NinthOwnedTemporalContract(self.c,'actual.sqlite','inputs','complete.json','missing.json')
            old.assert_not_called()
        with self.assertRaises(ValueError):self.contract.NinthOwnedTemporalContract(self.c,'actual.sqlite','inputs','complete.json','nominal.json',True)


if __name__=='__main__':unittest.main()
