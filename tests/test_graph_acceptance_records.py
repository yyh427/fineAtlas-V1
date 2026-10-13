import json
from pathlib import Path
import runpy
import unittest


class GraphAcceptanceRecordsTest(unittest.TestCase):
    def test_heterogeneous_original_record_schemas_preserve_names(self):
        extract = runpy.run_path(str(Path(__file__).resolve().parents[1] /
                                    'scripts/accept_searchable755_graph.py'))['author_name']
        for raw in ('1 001.Black_footed_Albatross', None, ['source row']):
            proof = json.dumps({'increment_native_record': {'raw_record': raw}})
            self.assertEqual(extract(proof, 'original name'), 'original name')
        proof = json.dumps({'increment_native_record': {'raw_record': {
            'raw_record': {'author_category': {'name': 'publisher name'}}}}})
        self.assertEqual(extract(proof, 'local name'), 'publisher name')


if __name__ == '__main__':
    unittest.main()
