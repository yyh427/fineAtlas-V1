import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

SCRIPT=Path(__file__).resolve().parents[1]/'scripts/promote_structure_stable.py'
spec=importlib.util.spec_from_file_location('structure_promotion_recipe',SCRIPT)
recipe=importlib.util.module_from_spec(spec);spec.loader.exec_module(recipe)


class StructurePromotionGuardTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.source=self.root/'old';self.code=self.root/'stable'
        for directory in ('src/fineatlas','scripts','configs'):(self.source/directory).mkdir(parents=True)
        (self.source/'src/fineatlas/__init__.py').write_text('__version__ = "1.11.0rc1"\n')
        (self.source/'src/fineatlas/graph.py').write_text('CONTRACT = "strict"\n')
        (self.source/'scripts/recipe.py').write_text('ADMISSION = "reviewed"\n')
        (self.source/'configs/rules.json').write_text('{}')
        (self.source/'pyproject.toml').write_text('version = "1.11.0rc1"\n')
        shutil.copytree(self.source,self.code)
        (self.code/'src/fineatlas/__init__.py').write_text('__version__ = "1.11.0"\n')
        (self.code/'pyproject.toml').write_text('version = "1.11.0"\n')
        self.old_inputs=self.root/'old-inputs';self.old_inputs.mkdir()
        (self.old_inputs/'review_release.json').write_text(json.dumps({'version':'v1.11.0rc1','proof':'same'}))
        self.inputs=self.root/'stable-inputs';shutil.copytree(self.old_inputs,self.inputs)
        (self.inputs/'review_release.json').write_text(json.dumps({'version':'v1.11.0','proof':'same'}))
        freeze={'inputs':recipe.files_digest(self.old_inputs),
                'code':{str(p.relative_to(self.source)):recipe.digest_file(p) for directory in ('src/fineatlas','scripts','configs')
                        for p in (self.source/directory).rglob('*') if p.is_file()},
                'packaging':{'pyproject.toml':recipe.digest_file(self.source/'pyproject.toml')},
                'source_graph_revision':'unchanged-graph'}
        self.meta={'unified_ready':True,'usability_indexes_ready':True,'browse_indexes_ready':True,
                   'database_revision':'exact-candidate','browse_index_revision':'exact-candidate',
                   'browse_parent_revision':recipe.canonical_hash(freeze),
                   'release':'v1.11.0rc1','structure_frozen_build_manifest':freeze}

    def tearDown(self):self.temp.cleanup()

    def validate(self):
        return recipe.validate_structure_reuse(self.meta,self.source,self.old_inputs,self.code,self.inputs)

    def test_version_only_reuse_preserves_semantic_revision(self):
        result=self.validate()
        self.assertEqual(result['manifest']['source_graph_revision'],'unchanged-graph')
        self.assertFalse(result['manifest']['promotion']['semantic_graph_recomputed'])

    def test_extra_or_modified_sdk_rejects_reuse(self):
        (self.code/'src/fineatlas/graph.py').write_text('CONTRACT = "loose"\n')
        with self.assertRaisesRegex(ValueError,'Only the literal SDK version'):self.validate()
        shutil.copyfile(self.source/'src/fineatlas/graph.py',self.code/'src/fineatlas/graph.py')
        (self.code/'src/fineatlas/extra.py').write_text('x=1')
        with self.assertRaisesRegex(ValueError,'inventory mismatch'):self.validate()

    def test_release_input_extra_field_rejects_reuse(self):
        (self.inputs/'review_release.json').write_text(json.dumps({'version':'v1.11.0','proof':'different'}))
        with self.assertRaisesRegex(ValueError,'Only candidate to stable'):self.validate()

    def test_changed_recipe_or_packaging_rejects_reuse(self):
        (self.code/'scripts/recipe.py').write_text('ADMISSION = "unsafe"\n')
        with self.assertRaises(ValueError):self.validate()
        shutil.copyfile(self.source/'scripts/recipe.py',self.code/'scripts/recipe.py')
        (self.code/'pyproject.toml').write_text('version = "1.11.0"\nrequires-python = ">=3.12"\n')
        with self.assertRaisesRegex(ValueError,'packaging version'):self.validate()

    def test_incomplete_acceptance_cannot_be_promoted(self):
        with self.assertRaises(ValueError):
            recipe.validate_source_evidence(self.meta,self.source,{}, {}, {})


if __name__=='__main__':unittest.main()
