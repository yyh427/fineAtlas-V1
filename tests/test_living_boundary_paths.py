"""A configuration needs a real domain path without false parent subsumption."""
import importlib.util
from pathlib import Path
import sqlite3
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/audit_living_candidate.py'
SPEC = importlib.util.spec_from_file_location('independent_living_boundary', SCRIPT)
A = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(A)


class LivingBoundaryPathsTest(unittest.TestCase):
    def test_real_cleaning_type_and_general_brush_are_distinct_routes(self):
        with sqlite3.connect(':memory:') as c:
            c.row_factory = sqlite3.Row
            c.execute('CREATE TABLE edges(id,child_uid,parent_uid,relation,status)')
            c.executemany('INSERT INTO edges VALUES(?,?,?,?,?)', [
                (1, 'cleaning-brush', 'cleaning-implement', 'IS_A', 'ACTIVE'),
                (2, 'general-brush', 'implement', 'IS_A', 'ACTIVE')])
            roots = {'cleaning-implement'}
            paths = {parent: A.native_boundary_path(c, parent, roots, 'strict')
                     for parent in ('cleaning-brush', 'general-brush')}
            result = A.boundary_branch_selection(paths)
            self.assertTrue(result['pass'])
            self.assertEqual(result['selected_paths'][0]['parent'], 'cleaning-brush')
            self.assertEqual(result['excluded_branches'], [
                {'parent': 'general-brush', 'reason': 'OUTSIDE_DOMAIN_BOUNDARY'}])
            self.assertEqual(c.execute('SELECT count(*) FROM edges').fetchone()[0], 2)
            c.execute("UPDATE edges SET status='SOURCE_SCOPE_REVIEW' WHERE id=1")
            invalid = {parent: A.native_boundary_path(c, parent, roots, 'strict')
                       for parent in paths}
            self.assertFalse(A.boundary_branch_selection(invalid)['pass'])

    def test_root_endpoint_empty_path_is_valid_and_all_missing_paths_fail(self):
        self.assertTrue(A.boundary_branch_selection({'root': []})['pass'])
        self.assertFalse(A.boundary_branch_selection({'a': None, 'b': None})['pass'])
        self.assertFalse(A.boundary_branch_selection({})['pass'])


if __name__ == '__main__':
    unittest.main()
