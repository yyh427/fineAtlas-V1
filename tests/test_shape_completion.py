import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class ShapeCompletionTest(unittest.TestCase):
    def test_generic_restoration_is_explicit_and_absent_proposal_keeps_verified_family(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);inputs=root/'inputs';inputs.mkdir();out=root/'out'
            inventory=[{'uid':'wagon','label':'station wagon','role':'CLASS','data':json.dumps({'definition':'A station wagon is an automotive body-style variant of a sedan.'})},
                       {'uid':'etios','label':'Toyota Etios','role':'MODEL','data':json.dumps({'definition':'The Toyota Etios is a range of cars.'})},
                       {'uid':'car','label':'car','role':'CLASS','data':'{}'}]
            prior=[{'op':'role','uid':'wagon','role':'MODEL'}, {'op':'role','uid':'etios','role':'MODEL_FAMILY'},
                   {'op':'link','uid':'wagon','parent':'car','relation':'DESIGN_TYPE_OF','source':'prior','uri':'https://example.org/wagon','proof':{}}]
            proposed=[{'op':'link','uid':'wagon','parent':'car','relation':'IS_A','source':'new','uri':'https://example.org/wagon','proof':{}}]
            def write(path,rows):path.write_text(''.join(json.dumps(r)+'\n' for r in rows))
            write(inputs/'hierarchy_shape_repairs.jsonl',prior);before=(inputs/'hierarchy_shape_repairs.jsonl').read_bytes()
            write(root/'inventory.jsonl',inventory);write(root/'proposed.jsonl',proposed)
            script=Path(__file__).resolve().parents[1]/'scripts/prepare_shape_completion.py'
            subprocess.run([sys.executable,str(script),'--inputs',str(inputs),'--inventory',str(root/'inventory.jsonl'),'--proposed',str(root/'proposed.jsonl'),'--output',str(out)],check=True,capture_output=True,text=True)
            rows=[json.loads(l) for l in (out/'hierarchy_shape_completion.jsonl').read_text().splitlines()]
            self.assertEqual([(r['uid'],r['role']) for r in rows if r['op']=='role'],[('wagon','CLASS')])
            self.assertEqual([(r['uid'],r['relation']) for r in rows if r['op']=='withdraw_frozen_link'],[('wagon','DESIGN_TYPE_OF')])
            self.assertEqual((inputs/'hierarchy_shape_repairs.jsonl').read_bytes(),before)


if __name__=='__main__':unittest.main()
