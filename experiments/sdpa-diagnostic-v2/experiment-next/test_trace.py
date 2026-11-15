# Generated unit controls, not model evidence.
import unittest
from analyze_allocator_trace import replay
class T(unittest.TestCase):
 def test_pending_free(self):
  r=replay([{'action':'alloc','addr':1,'size':100},{'action':'free_requested','addr':1},{'action':'alloc','addr':2,'size':50},{'action':'free_completed','addr':1}]);self.assertEqual(r['replayed_peak_bytes'],150)
 def test_unknown(self):self.assertFalse(replay([{'action':'free_completed','addr':1}])['trace_complete'])
 def test_duplicate(self):
  with self.assertRaises(ValueError):replay([{'action':'alloc','addr':1,'size':1}]*2)
if __name__=='__main__':unittest.main()

class Completeness(unittest.TestCase):
 def test_no_metadata_is_not_complete(self):
  self.assertFalse(replay([{'action':'alloc','addr':1,'size':1}])['trace_complete'])
 def test_ring_full_is_not_complete(self):
  self.assertFalse(replay([{'action':'alloc','addr':1,'size':1}],max_entries=1,started_before_cuda=True)['trace_complete'])
 def test_verified_untruncated(self):
  r=replay([{'action':'alloc','addr':1,'size':1,'frames':[{'name':'mlp'}]}],max_entries=2,started_before_cuda=True)
  self.assertTrue(r['trace_complete']);self.assertEqual(r['allocation_events_with_stacks'],1)
