"""Mock API contract checks only. Not CUDA evidence."""
import importlib.util,os,sys,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch,Mock

class Diagnostic(unittest.TestCase):
 def test_history_contract(self):
  spec=importlib.util.spec_from_file_location('diag',Path(__file__).parent/'diagnostic-instrumentation/lifecycle_worker.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
  record=Mock();fake=SimpleNamespace(cuda=SimpleNamespace(is_initialized=lambda:False,memory=SimpleNamespace(_record_memory_history=record)))
  with patch.dict(sys.modules,torch=fake),patch.dict(os.environ,{'PHYSICAL_PEAK_ALLOCATOR_HISTORY':'1','PHYSICAL_PEAK_HISTORY_MAX_ENTRIES':'100000'}),patch.object(m,'_event'):
   m.enable_allocator_history()
  record.assert_called_once_with(enabled='all',context='all',stacks='python',max_entries=100000)
 def test_original_unchanged(self):
  original=Path(__file__).parents[1]/'experiment/instrumentation/lifecycle_worker.py'
  if original.exists():self.assertIn('context=None',original.read_text())
