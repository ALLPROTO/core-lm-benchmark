import unittest,pathlib,subprocess,sys
class C(unittest.TestCase):
 def test_generator_exact(self):
  p=pathlib.Path(__file__).parent
  before=(p/'benchmark_combined.py').read_bytes()
  subprocess.run([sys.executable,str(p/'patch_harness.py')],check=True,stdout=subprocess.DEVNULL)
  self.assertEqual(before,(p/'benchmark_combined.py').read_bytes())
 def test_norm_contract(self):
  s=(pathlib.Path(__file__).parent/'benchmark_combined.py').read_text()
  self.assertIn("norm_stats['calls']!=2*(2*layers+1)*len(executed_lengths)",s)
  self.assertIn("norm_stats['modules']!=2*layers+1",s)
 def test_runner(self):
  s=(pathlib.Path(__file__).parent/'run-combined.sh').read_text()
  self.assertIn('benchmark_combined.py',s);self.assertIn('combo-quality',s)
if __name__=='__main__':unittest.main()
