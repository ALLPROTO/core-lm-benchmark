# Protocol-control unit tests only, no model evidence.
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'experiment'/'implementation'))
import benchmark_inplace as b
class Protocol(unittest.TestCase):
 def test_registered_pair(self):
  p=b.execution_plan('matrix',['qwen05'],[4096])
  self.assertEqual(p['modes'],['sdpa','sdpa_inplace'])
  for purpose in ('memory','latency'):
   orders=p['pair_orders']['qwen05-L4096'][purpose]
   self.assertEqual(len(orders),6)
   self.assertEqual(sum(o[0]=='sdpa' for o in orders),3)
 def test_no_wrong_harness(self):
  s=Path(b.__file__).read_text()
  self.assertNotIn("frozen/'benchmark_matrix.py'",s)
  self.assertIn("'mlp_adapter':mlp_stats",s)
  self.assertIn("mlp_stats['calls'] != 2*layers*len(executed_lengths)",s)
 def test_original_immutable(self):
  import zipfile,hashlib
  p=Path(__file__).resolve().parent.parent/'experiment'
  with zipfile.ZipFile(p/'prepared.zip') as z:
   for name in ('implementation/benchmark_matrix.py','implementation/attention_adapters.py'):
    self.assertEqual(z.read(name),(p/name).read_bytes())
if __name__=='__main__':unittest.main()
