"""Reject malformed/stale pages while accepting the real success-page schema."""
import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('install_verifier',Path(__file__).resolve().parents[1]/'scripts/verify_unified_install.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class InstallPageContractTests(unittest.TestCase):
 def page(self):
  return {'items':[{'uid':'native:1'}],'has_more':True,'next_cursor':'opaque-cursor',
          'relation_view':'unified','database_revision':'frozen-revision'}
 def check(self,page):return module.validate_domain_page(page,'unified','frozen-revision',1)
 def test_actual_success_schema_without_status(self):
  result=self.check(self.page());self.assertIsNone(result['public_page_status'])
  self.assertEqual(result['public_page_items'],1)
 def test_empty_success_schema(self):
  p=self.page();p.update(items=[],has_more=False,next_cursor=None)
  self.assertEqual(self.check(p)['public_page_items'],0)
 def test_error_is_not_a_success(self):
  p=self.page();p.update(status='NOT_FOUND',reason='UNKNOWN_DOMAIN')
  with self.assertRaises(AssertionError):self.check(p)
 def test_stale_snapshot_and_wrong_view_rejected(self):
  for field in ('database_revision','relation_view'):
   p=self.page();p[field]='different'
   with self.subTest(field=field),self.assertRaises(AssertionError):self.check(p)
 def test_missing_schema_and_inconsistent_cursor_rejected(self):
  for change in ({'next_cursor':None},{'has_more':False},{'items':[{},{}]}):
   p=self.page();p.update(change)
   with self.subTest(change=change),self.assertRaises(AssertionError):self.check(p)
  p=self.page();p.pop('items')
  with self.assertRaises(AssertionError):self.check(p)

if __name__=='__main__':unittest.main()
