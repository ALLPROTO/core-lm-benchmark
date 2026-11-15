"""Replay trusted, self-produced PyTorch allocation traces; not physical NVML proof."""
from collections import defaultdict

def replay(events, *, max_entries=None, started_before_cuda=False):
 live={};peak=0;peak_live={};unknown_frees=0
 for e in events:
  a=e['action'];addr=e.get('addr');size=e.get('size',0)
  if a=='alloc':
   if addr in live:raise ValueError('Duplicate live allocation')
   live[addr]={'size':size,'frames':e.get('frames',[])}
  elif a=='free_completed':
   if addr not in live:unknown_frees+=1
   else:del live[addr]
  # free_requested is stream-pending and remains live until completion.
  total=sum(x['size']for x in live.values())
  if total>peak:peak=total;peak_live=live.copy()
 groups=defaultdict(int)
 for item in peak_live.values():
  frames=item['frames'];key=' -> '.join(str(f.get('name','?')) for f in frames[:8]) or '<no stack>'
  groups[key]+=item['size']
 return {'replayed_peak_bytes':peak,'live_allocations_at_peak':len(peak_live),'unknown_frees':unknown_frees,
 'complete_trace_required':True,'trace_complete':bool(events) and unknown_frees==0 and started_before_cuda and max_entries is not None and len(events)<max_entries,
 'possible_ring_truncation':max_entries is None or len(events)>=max_entries,
 'all_allocation_stacks_present':any(e['action']=='alloc' for e in events) and all(bool(e.get('frames')) for e in events if e['action']=='alloc'),
 'allocation_events_with_stacks':sum(e['action']=='alloc' and bool(e.get('frames')) for e in events),
 'stack_groups':sorted(groups.items(),key=lambda x:-x[1]),
 'warning':'PyTorch event replay only; excludes driver/library and unrelated process allocations. Verify ring truncation flags separately.'}
if __name__=='__main__':
 import argparse,pickle,json
 p=argparse.ArgumentParser();p.add_argument('trusted_snapshot');p.add_argument('--out',required=True);p.add_argument('--worker-events',required=True);a=p.parse_args()
 # Accept only snapshots produced by our own monitored process; pickle executes code.
 with open(a.trusted_snapshot,'rb')as f:snapshot=pickle.load(f)
 metadata=[json.loads(line) for line in open(a.worker_events)]
 enabled=[e for e in metadata if e['kind']=='allocator_history_enabled']
 saved=[e for e in metadata if e['kind']=='allocator_history_saved']
 if len(enabled)!=1 or len(saved)!=1 or any(e['kind']=='allocator_history_error' for e in metadata):
  raise ValueError('Missing/failed allocator history metadata')
 if enabled[0].get('context')!='all':raise ValueError('Stack capture was not enabled')
 results=[replay(events,max_entries=saved[0]['configured_max_entries'],started_before_cuda=enabled[0]['cuda_initialized_before_enable'] is False)for events in snapshot['device_traces']]
 with open(a.out,'w')as f:json.dump(results,f,indent=2)
