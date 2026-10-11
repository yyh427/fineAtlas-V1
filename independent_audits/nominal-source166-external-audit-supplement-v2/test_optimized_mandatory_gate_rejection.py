"""Optimized Python must fail before any optional source/data/network work."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parent
MODULES=('external_audit_supplement_binding.py','package_external_audit_supplement.py','verify_sealed_source_operations.py','nominal-design-scope-final-plan-v1/run_final_nominal_design_scope_external_audit.py','nominal-formal-final-plan-v1/run_final_nominal_formal_external_audit.py','nominal-formal-final-plan-v1/independent_nominal_formal_binding.py','nominal-design-scope-final-plan-v1/independent_nominal_design_scope_final_interface_audit.py','nominal-formal-final-plan-v1/independent_nominal_formal_final_interface_audit.py')


class OptimizationCannotRemoveMandatoryGates(unittest.TestCase):
    def reject(self,flag=None,optimize=None):
        for relative in MODULES:
            with self.subTest(module=relative,flag=flag,optimize=optimize):
                environment=dict(os.environ);environment.pop('PYTHONOPTIMIZE',None);environment['PYTHONDONTWRITEBYTECODE']='1'
                if optimize:environment['PYTHONOPTIMIZE']=optimize
                command=[sys.executable,'-B']+([flag]if flag else[])+[str(ROOT/relative)]
                result=subprocess.run(command,capture_output=True,text=True,env=environment)
                self.assertNotEqual(result.returncode,0)
                self.assertIn('RuntimeError: Optimized Python is forbidden',result.stderr)
                self.assertNotIn('usage:',result.stderr)
    def test_O_rejects_all_eight_before_cli_or_module_use(self):self.reject('-O')
    def test_OO_rejects_all_eight_before_cli_or_module_use(self):self.reject('-OO')
    def test_environment_optimization_rejects_all_eight(self):self.reject(optimize='1')
    def test_optimized_module_import_cannot_expose_authorize_or_binding(self):
        for relative in MODULES:
            with self.subTest(module=relative):
                program="import importlib.util; p="+repr(str(ROOT/relative))+";s=importlib.util.spec_from_file_location('gate',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);raise RuntimeError('UNGUARDED IMPORT')"
                result=subprocess.run([sys.executable,'-B','-O','-c',program],capture_output=True,text=True)
                self.assertNotEqual(result.returncode,0);self.assertIn('Optimized Python is forbidden',result.stderr);self.assertNotIn('UNGUARDED IMPORT',result.stderr)
    def test_optimized_downloader_cannot_create_destination_or_touch_network(self):
        with tempfile.TemporaryDirectory()as temp:
            destination=Path(temp)/'never-create';output=Path(temp)/'never-write.json'
            result=subprocess.run([sys.executable,'-B','-O',str(ROOT/'package_external_audit_supplement.py'),'download','--url','https://127.0.0.1:1/should-never-request','--sha256','0'*64,'--bytes','1','--destination',str(destination),'--output',str(output)],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0);self.assertIn('Optimized Python is forbidden',result.stderr);self.assertFalse(destination.exists());self.assertFalse(output.exists())


if __name__=='__main__':unittest.main()
