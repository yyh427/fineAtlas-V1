"""Public install verification must reject missing or mis-scoped new domains."""
import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('release_install_verifier',Path(__file__).resolve().parents[1]/'scripts/verify_unified_install.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class ReleaseInventoryTests(unittest.TestCase):
    def setUp(self):
        self.domains=[{'domain':'furniture','root_uids':['furniture-root']},{'domain':'lighting','root_uids':['lamp-root','fixture-root']}]
        self.expected={'release':'test-review','database_revision':'exact-test-revision','domains':{'actual':2,'public_contract_passes':2},'domain_inventory':{d['domain']:d['root_uids'] for d in self.domains}}
        self.manifest={'release':'test-review','database_revision':'exact-test-revision','domain_count':2}

    def test_new_inventory_is_checked_without_a_fixed_legacy_size(self):
        self.assertEqual(module.validate_domain_inventory(self.domains,self.expected,self.manifest),2)

    def test_missing_domain_fails(self):
        with self.assertRaises(AssertionError):module.validate_domain_inventory(self.domains[:1],self.expected,self.manifest)

    def test_wrong_root_even_with_correct_domain_count_fails(self):
        wrong=[self.domains[0],{'domain':'lighting','root_uids':['abstract-light-root']}]
        with self.assertRaises(AssertionError):module.validate_domain_inventory(wrong,self.expected,self.manifest)

    def test_wrong_release_fails(self):
        with self.assertRaises(AssertionError):module.validate_domain_inventory(self.domains,self.expected,{'release':'older-review','database_revision':'exact-test-revision','domain_count':2})

    def test_partial_contract_acceptance_fails(self):
        expected={**self.expected,'domains':{'actual':2,'public_contract_passes':1}}
        with self.assertRaises(AssertionError):module.validate_domain_inventory(self.domains,expected,self.manifest)

if __name__=='__main__':unittest.main()
