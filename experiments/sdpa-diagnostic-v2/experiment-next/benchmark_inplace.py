#!/usr/bin/env python3
"""Registered real-pretrained multi-model regression; no synthetic benchmark path.

Probe diagnostics, quality-only sweep, full-lifetime sampled memory, and unsampled
latency are separate processes. Never infer continuous physical maxima from NVML.
"""
import argparse
import contextlib
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import platform
import random
import shutil
import statistics
import subprocess
import sys
import time

MODES = ('sdpa', 'sdpa_inplace')
MODELS = ('qwen05', 'qwen15', 'smol17')
LENGTHS = (512, 2048, 4096)
REPEATS = 6
SEED = 20261113
RUNTIME = {'torch': '2.13.0+cu130', 'transformers': '5.14.1', 'triton': '3.7.1'}


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def read(path):
    return json.loads(Path(path).read_text())


def sha256(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def resolve(base, value):
    p = Path(value)
    return p.resolve() if p.is_absolute() else (base / p).resolve()


def load_inputs(registry_path, alias):
    import numpy as np
    registry_path = Path(registry_path).resolve()
    reg = read(registry_path)
    if reg['runtime'] != RUNTIME or tuple(reg['lengths']) != LENGTHS:
        raise ValueError('Unregistered runtime/lengths')
    m = reg['models'][alias]
    tokpath = resolve(registry_path.parent, m['token_file'])
    if sha256(tokpath) != m['token_file_sha256']:
        raise ValueError('Token file digest mismatch')
    doc = read(tokpath)
    ids = doc['token_ids']
    if len(ids) != 4096 or any(type(t) is not int or not 0 <= t < 2**32 for t in ids):
        raise ValueError('Exactly 4096 registered uint32 token ids required')
    if hashlib.sha256(np.asarray(ids, dtype='<u4').tobytes()).hexdigest() != doc['sha256']:
        raise ValueError('Token uint32-LE digest mismatch')
    snapshot = resolve(registry_path.parent, m['snapshot_path'])
    if sha256(snapshot / 'config.json') != m['config_sha256']:
        raise ValueError('Pinned config hash mismatch')
    for item in m['assets']:
        p = snapshot / item['path']
        if not p.is_file() or p.stat().st_size != item['bytes']:
            raise ValueError('Missing/wrong-size previously SHA-verified asset: ' + str(p))
    return reg, m, doc, snapshot


def workload_tokens(ids, length, purpose):
    if len(ids) != 4096 or length not in LENGTHS:
        raise ValueError('Only registered input lengths allowed')
    if purpose == 'quality':
        # Eight overlapping real windows, but 1024 DISTINCT scored positions.
        return [('quality-offset-' + str(start), ids[start:start+2048])
                for start in range(0, 1024, 128)]
    # Hold the final 128 targets constant across context-length comparisons.
    return [('suffix-' + str(length), ids[-length:])]


def balanced_orders(seed):
    rng = random.Random(seed)
    orders = []
    for _ in range(REPEATS // 2):
        order = list(MODES)
        rng.shuffle(order)
        orders.extend((order, list(reversed(order))))
    rng.shuffle(orders)
    return orders


def execution_plan(stage, models=None, lengths=None, seed=SEED):
    if stage not in ('probe', 'matrix', 'quality'):
        raise ValueError(stage)
    models = list(models or MODELS)
    lengths = list(lengths or LENGTHS)
    if any(m not in MODELS for m in models) or any(n not in LENGTHS for n in lengths):
        raise ValueError('Unknown model/length')
    if len(set(models)) != len(models) or len(set(lengths)) != len(lengths):
        raise ValueError('Duplicate model/length')
    cells = [{'model': m, 'length': n} for m in models for n in ([2048] if stage == 'quality' else lengths)]
    purposes = ['memory', 'latency'] if stage == 'matrix' else [stage]
    orders = {}
    for ci, cell in enumerate(cells):
        key = cell_key(cell['model'], cell['length'])
        orders[key] = {}
        for pi, purpose in enumerate(purposes):
            if stage == 'matrix':
                orders[key][purpose] = balanced_orders(seed + ci*100 + pi)
            else:
                order = list(MODES)
                random.Random(seed + ci*100 + pi).shuffle(order)
                orders[key][purpose] = [order]
    return {'stage': stage, 'modes': list(MODES), 'cells': cells, 'purposes': purposes,
            'repeats': REPEATS if stage == 'matrix' else 1, 'pair_orders': orders,
            'randomization_seed': seed, 'warmups': 2 if stage == 'matrix' else 0,
            'latency_rounds': 9, 'matrix_input_selection': 'suffix-L of registered4096; same final128 targets',
            'quality_input_selection': '8 real2048 windows offsets0,128,...896;1024 distinct scored positions1920..2943',
            'primary_cell': {'model': 'qwen05', 'length': 4096, 'comparison': ['sdpa', 'sdpa_inplace']},
            'peak_resets': False, 'cache_clearing': False,
            'quality_policy': 'Inplace MLP requires exact SDPA outputs. SDPA numeric compatibility failures are reported, not treated as semantic invalidity or excluded from performance.',
            'statistical_scope': 'Six fresh process blocks per cell; inner rounds correlated. Shared baseline and exploratory cells are not independent discoveries.'}


def cell_key(model, length):
    return f'{model}-L{length}'


def inventory(tensors):
    unique = {}
    for tensor in tensors:
        if tensor is None:
            continue
        s = tensor.untyped_storage()
        unique[(str(tensor.device), s.data_ptr(), s.nbytes())] = s.nbytes()
    devices = {}
    for (dev, _, _), size in unique.items():
        devices[dev] = devices.get(dev, 0) + size
    return {'bytes_by_device': devices, 'unique_storage_bytes': sum(unique.values())}


def cache_inventory(cache):
    result = inventory(t for layer in cache.layers for t in (layer.keys, layer.values))
    result['lengths'] = [cache.get_seq_length(i) for i in range(len(cache.layers))]
    result['shapes'] = [[list(layer.keys.shape), list(layer.values.shape)] for layer in cache.layers]
    return result


class SemanticProbe:
    """Actual real-model attention argument checks, diagnostic processes ONLY."""
    def __init__(self, model, mode):
        import torch
        from attention_adapters import validate_lower_right_mask
        from torch.nn.attention.bias import CausalBias, CausalVariant
        self.expected = None
        self.records = []
        self.mode = mode
        self.original = None
        self.module = None
        self.torch = torch
        self.validate = validate_lower_right_mask
        self.bias_type = CausalBias
        self.lower_right = CausalVariant.LOWER_RIGHT
        if mode in ('eager', 'fused'):
            self.module = importlib.import_module(f'transformers.models.{model.config.model_type}.modeling_{model.config.model_type}')
            self.original = self.module.eager_attention_forward
            def wrapped(module, query, key, value, attention_mask, *args, **kwargs):
                self.check(query, key, value, attention_mask, True, 'eager_actual')
                return self.original(module, query, key, value, attention_mask, *args, **kwargs)
            self.module.eager_attention_forward = wrapped
        else:
            self.original = torch.nn.functional.scaled_dot_product_attention
            def wrapped(query, key, value, attn_mask=None, dropout_p=0.0, is_causal=False, **kwargs):
                self.check(query, key, value, attn_mask, is_causal, 'sdpa_actual')
                # CausalBias dispatch checks the public function's identity.
                # Fresh diagnostic workers are single-threaded callers: restore
                # that identity during dispatch, then reinstall this observer.
                torch.nn.functional.scaled_dot_product_attention = self.original
                try:
                    return self.original(query, key, value, attn_mask=attn_mask, dropout_p=dropout_p,
                                         is_causal=is_causal, **kwargs)
                finally:
                    torch.nn.functional.scaled_dot_product_attention = wrapped
            torch.nn.functional.scaled_dot_product_attention = wrapped

    def check(self, q, k, v, mask, causal, path):
        if self.expected is None:
            raise RuntimeError('Attention outside registered diagnostic phase')
        eq, ek, phase = self.expected
        if (q.shape[-2], k.shape[-2], v.shape[-2]) != (eq, ek, ek):
            raise RuntimeError(f'Actual attention discarded prefix or changed queries: {q.shape}, {k.shape}, expected {eq}/{ek}')
        if isinstance(mask, self.bias_type):
            if mask.variant != self.lower_right or (mask.seq_len_q, mask.seq_len_kv) != (eq, ek):
                raise RuntimeError('Incorrect causal bias alignment')
            mask_kind = 'CausalBias.lower_right'
        elif mask is None:
            if not causal or eq != ek:
                raise RuntimeError('Missing/upper-left rectangular causal mask')
            mask_kind = 'implicit_square_causal'
        else:
            self.validate(mask, q, k)
            mask_kind = 'verified_explicit_lower_right'
        record = {'phase': phase, 'q': list(q.shape), 'k': list(k.shape), 'v': list(v.shape),
                  'mask_kind': mask_kind, 'mask_shape': None if mask is None or isinstance(mask, self.bias_type) else list(mask.shape),
                  'path': path, 'prefix_in_attention_verified': True, 'future_exclusion_verified': True}
        if record not in self.records:
            self.records.append(record)

    def close(self):
        if self.module is not None:
            self.module.eager_attention_forward = self.original
        else:
            self.torch.nn.functional.scaled_dot_product_attention = self.original


def validate_adapter_counts(mode, stats, layers, block_lengths, purpose):
    """Assert actual adapter execution, including warmups, before recording success."""
    total=2*layers*len(block_lengths)
    if mode=='fused':
        optimized=layers*sum(length-129>1536 for length in block_lengths)
        expected={'calls':total,'optimized_calls':optimized,'short_native_calls':total-optimized,
                  'fused_scale_mask_cast_calls':optimized,'alias_softmax_calls':optimized}
    elif mode=='sdpa_lower_right':
        validate=purpose in ('probe','quality')
        expected={'calls':total,'prefill_calls':layers*len(block_lengths),
                  'continuation_calls':layers*len(block_lengths),
                  'semantic_mask_checks':total if validate else 0,'validate_masks':validate}
    else:
        if stats is not None:raise RuntimeError('Unexpected adapter in native baseline')
        return {'pass':True,'expected':None,'blocks':len(block_lengths)}
    if stats is None or any(stats.get(k)!=v for k,v in expected.items()):
        raise RuntimeError(f'Adapter invocation contract failed: expected {expected}, actual {stats}')
    return {'pass':True,'expected':expected,'blocks':len(block_lengths)}


def worker(a):
    lifecycle = None
    if os.environ.get('PHYSICAL_PEAK_RUN_DIR'):
        import lifecycle_worker as lifecycle
        lifecycle.start()
    started = time.perf_counter()
    def phase(label, **fields):
        if lifecycle:
            lifecycle.phase(label)
        with (a.out/'phases.jsonl').open('a') as f:
            f.write(json.dumps({'phase': label, 'wall_time_ns': time.time_ns(), 'monotonic_ns': time.monotonic_ns(), **fields})+'\n')
    phase('worker_entry', pid=os.getpid(), purpose=a.purpose)
    import numpy as np
    import torch
    import transformers
    import triton
    from transformers import AutoModelForCausalLM
    if {'torch': torch.__version__, 'transformers': transformers.__version__, 'triton': triton.__version__} != RUNTIME:
        raise RuntimeError('Pinned CUDA runtime required')
    if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported():
        raise RuntimeError('CUDA BF16 required; no CPU model-evidence fallback')
    if lifecycle:
        lifecycle.enable_allocator_history()
    reg, spec, token_doc, snapshot = load_inputs(a.registry, a.model)
    torch.manual_seed(0)
    torch.cuda.manual_seed_all(0)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch.use_deterministic_algorithms(True)
    workloads = workload_tokens(token_doc['token_ids'], a.length, a.purpose)
    token_records = [{'block': name, 'tokens': ids, 'targets': ids[-128:]} for name, ids in workloads]
    write_json(a.out/'tokens.json', {'registered_token_sha256': token_doc['sha256'], 'source': token_doc['source'],
                                   'model': a.model, 'length': a.length, 'purpose': a.purpose, 'blocks': token_records})
    def memory():
        torch.cuda.synchronize()
        return {'allocated_bytes': torch.cuda.memory_allocated(), 'reserved_bytes': torch.cuda.memory_reserved(),
                'cumulative_peak_allocated_bytes': torch.cuda.max_memory_allocated(),
                'cumulative_peak_reserved_bytes': torch.cuda.max_memory_reserved()}
    prep_start = time.perf_counter()
    phase('model_preparation_begin')
    model = AutoModelForCausalLM.from_pretrained(snapshot, local_files_only=True, use_safetensors=True, trust_remote_code=False,
            dtype=torch.bfloat16, attn_implementation='sdpa' if a.mode.startswith('sdpa') else 'eager').eval()
    model.requires_grad_(False)
    adapter = None
    from attention_adapters import install_candidate, install_lower_right_sdpa
    if a.mode == 'fused':
        adapter = install_candidate(model)
    elif a.mode == 'sdpa_lower_right':
        adapter = install_lower_right_sdpa(model, validate_masks=a.purpose in ('probe', 'quality'))
    if a.mode == 'sdpa_inplace':
        from inplace_mlp import install
        mlp_stats = install(model)
    model.to('cuda')
    torch.cuda.synchronize()
    prep_seconds = time.perf_counter()-prep_start
    if any(p.dtype != torch.bfloat16 for p in model.parameters() if p.is_floating_point()):
        raise RuntimeError('Changed parameter precision')
    layers = model.config.num_hidden_layers
    heads = getattr(model.config, 'num_key_value_heads', model.config.num_attention_heads)
    head_dim = getattr(model.config, 'head_dim', None) or model.config.hidden_size//model.config.num_attention_heads
    weights = inventory([*model.parameters(), *model.buffers()])
    if any(not k.startswith('cuda') for k in weights['bytes_by_device']):
        raise RuntimeError('Nonresident model tensors')
    phase('model_preparation_end', seconds=prep_seconds, memory=memory())
    reference = read(a.reference) if a.reference else None
    reference_blocks = {}
    if reference:
        if (reference['model'],reference['mode'],reference['length'],reference['purpose']) != (a.model,a.mode,a.length,'memory'):
            raise RuntimeError('Wrong raw reference arm/cell')
        reference_blocks = {x['block']: x for x in reference['rounds'][0]['blocks']}
    if (a.purpose == 'latency' or a.purpose == 'memory' and a.repeat > 0) and not reference:
        raise RuntimeError('Repeated memory and latency require immutable repeat0 reference')
    diagnostics = SemanticProbe(model,a.mode) if a.purpose in ('probe','quality') else None
    profiler = None
    if a.purpose == 'probe':
        profiler = torch.profiler.profile(activities=[torch.profiler.ProfilerActivity.CPU,torch.profiler.ProfilerActivity.CUDA],record_shapes=True)
    def run_block(name, ids_cpu, measured=False):
        prefix = len(ids_cpu)-129
        torch.cuda.synchronize()
        t0 = time.perf_counter()
        with torch.inference_mode():
            ids = torch.tensor([ids_cpu], dtype=torch.long, device='cuda')
            if diagnostics:
                diagnostics.expected = (prefix,prefix,'prefill')
            with torch.profiler.record_function('registered_prefill') if profiler else contextlib.nullcontext():
                prefill = model(ids[:,:prefix],use_cache=True,return_dict=True,logits_to_keep=1,output_attentions=False)
            cache = prefill.past_key_values
            prefix_lengths = [cache.get_seq_length(i) for i in range(len(cache.layers))]
            del prefill
            pos = torch.arange(prefix,prefix+128,device='cuda')
            if diagnostics:
                diagnostics.expected = (128,prefix+128,'continuation')
            with torch.profiler.record_function('registered_continuation') if profiler else contextlib.nullcontext():
                output = model(ids[:,prefix:prefix+128],past_key_values=cache,
                    attention_mask=torch.ones((1,prefix+128),dtype=torch.long,device='cuda'),
                    position_ids=pos.unsqueeze(0),cache_position=pos,use_cache=False,return_dict=True,output_attentions=False)
            rows = output.logits.detach().cpu().float()[0]
            torch.cuda.synchronize()
            seconds = time.perf_counter()-t0
            state = cache_inventory(cache)
            mem = memory()
            expected_kv = layers*2*heads*(prefix+128)*head_dim*2
            if prefix_lengths != [prefix]*layers or state['lengths'] != [prefix+128]*layers:
                raise RuntimeError('Full prefix/continuation cache missing')
            if state['unique_storage_bytes'] != expected_kv or any(not x.startswith('cuda') for x in state['bytes_by_device']):
                raise RuntimeError('Changed/offloaded complete KV storage')
            if tuple(rows.shape) != (128,model.config.vocab_size) or not torch.isfinite(rows).all():
                raise RuntimeError('Invalid full vocabulary logits')
            del output,cache,ids,pos
        result = {'block':name,'seconds':seconds,'memory':mem,'prefix_cache_lengths':prefix_lengths,
                  'cache_after_continuation':state,'expected_kv_storage_bytes':expected_kv}
        if measured:
            arr = rows.numpy()
            result['raw_payload_sha256'] = hashlib.sha256(arr.view(np.uint8)).hexdigest()
            if reference:
                ref = reference_blocks[name]
                match = result['raw_payload_sha256'] == ref['raw_payload_sha256']
                result['matches_memory_run_raw_payload'] = match
                result['raw_reference_metrics'] = os.path.relpath(a.reference.resolve(), a.out)
                if not match:
                    np.save(a.out/f'unexpected-{name}.npy',arr,allow_pickle=False)
                    raise RuntimeError('Output differs from same-arm repeat0 reference; raw mismatch retained')
            else:
                dest = a.out/f'logits-{name}.npy'
                np.save(dest,arr,allow_pickle=False)
                targets = torch.tensor(ids_cpu[-128:],dtype=torch.long)
                result.update(raw_logits_file=dest.name,raw_logits_sha256=sha256(dest),
                    nll_per_token_fp32_torch=torch.nn.functional.cross_entropy(rows,targets,reduction='none').tolist(),
                    top1=rows.argmax(-1).tolist())
        return result
    warmups=[]
    if a.purpose in ('memory','latency'):
        for i in range(2):
            phase('warmup_begin',index=i)
            w=run_block(*workloads[0]);warmups.append(w)
            phase('warmup_end',index=i,seconds=w['seconds'],memory=w['memory'])
    rounds=[]
    if profiler:
        profiler.__enter__()
    for i in range(9 if a.purpose=='latency' else 1):
        phase('inference_round_begin',index=i)
        blocks=[run_block(name,ids,True) for name,ids in workloads]
        rounds.append({'round':i,'blocks':blocks,'workload_seconds':sum(b['seconds'] for b in blocks)})
        phase('inference_round_end',index=i,memory=memory())
    operators=[]
    if profiler:
        profiler.__exit__(None,None,None)
        for event in profiler.events():
            if any(x in event.name.lower() for x in ('scaled_dot_product','flash_attention','efficient_attention','cudnn_attention')):
                parent=event.cpu_parent;ancestors=[]
                while parent is not None:
                    ancestors.append(parent.name);parent=parent.cpu_parent
                operators.append({'name':event.name,'phase':next((p for p in ancestors if p.startswith('registered_')),None)})
        profiler.export_chrome_trace(str(a.out/'diagnostic-trace.json'))
    if diagnostics:
        if not diagnostics.records or not all(any(x['phase']==p for x in diagnostics.records) for p in ('prefill','continuation')):
            raise RuntimeError('Diagnostic failed to observe both actual attention phases')
        diagnostics.close()
    executed_lengths=([len(workloads[0][1])]*2 if a.purpose in ('memory','latency') else [])
    executed_lengths += [len(ids) for _,ids in workloads]*(9 if a.purpose=='latency' else 1)
    adapter_contract=validate_adapter_counts(a.mode,adapter,layers,executed_lengths,a.purpose)
    if a.mode=='sdpa_inplace' and mlp_stats['calls'] != 2*layers*len(executed_lengths):
        raise RuntimeError('MLP call-count mismatch')
    final_memory=memory()
    phase('inference_complete',memory=final_memory)
    metrics={'schema':'modern-matrix-worker-v1','model':a.model,'mode':a.mode,'length':a.length,'purpose':a.purpose,'repeat':a.repeat,
        'repository':spec['repository'],'model_revision':spec['revision'],'registry_sha256':sha256(a.registry),
        'token_ids_sha256':token_doc['sha256'],'model_type':model.config.model_type,'num_hidden_layers':layers,
        'num_key_value_heads':heads,'head_dim':head_dim,'vocab_size':model.config.vocab_size,
        'batch_size':1,'weights_dtype':'bfloat16','cache_dtype':'bfloat16','model_storage':weights,
        'runtime':RUNTIME,'python':platform.python_version(),'numpy':np.__version__,'cuda':torch.version.cuda,
        'gpu':torch.cuda.get_device_name(),'gpu_uuid':str(torch.cuda.get_device_properties(0).uuid),
        'gpu_total_bytes':torch.cuda.get_device_properties(0).total_memory,'tf32':False,'deterministic_algorithms':True,'seed':0,
        'attention_implementation':model.config._attn_implementation,'mlp_adapter':mlp_stats if a.mode=='sdpa_inplace' else None,'adapter':adapter,'adapter_invocation_contract':adapter_contract,'warmups':warmups,'rounds':rounds,
        'session_memory':final_memory,'model_preparation':{'seconds':prep_seconds},
        'latency_median_workload_seconds':statistics.median(x['workload_seconds'] for x in rounds),
        'worker_seconds_to_metrics':time.perf_counter()-started,'source_sha256':sha256(__file__),
        'diagnostic_semantics':None if diagnostics is None else {'pass':True,'records':diagnostics.records},
        'diagnostic_attention_operators':operators,
        'diagnostic_only':a.purpose in ('probe','quality'),
        'time_scope':'Input upload, full prefill, teacherforced128 continuation, retained full GPU KV, full logits CPU FP32 copy; disk/hash/NLL/inventory outside inference interval.',
        'session_peak_scope':'Lifetime CUDA allocator high-water, no resets/cache clearing. Probe/quality diagnostics are NOT memory/latency evidence.',
        'physical_memory':'External NVML samples are observed lower bounds, not continuous physical peaks.',
        'compilation_cache':os.environ.get('TRITON_CACHE_DIR'),'cold_start_warning':'Warmed medians after2 warmups; first-use compile may already be cached by probe.'}
    write_json(a.out/'metrics.json',metrics)
    phase('worker_results_complete',memory=memory())
    if lifecycle:
        lifecycle.finish()


def canonical_raw(root, block):
    root=Path(root)
    if 'raw_logits_file' in block:
        return root/block['raw_logits_file'],block
    refpath=resolve(root,block['raw_reference_metrics'])
    ref=read(refpath)
    target=next(x for x in ref['rounds'][0]['blocks'] if x['block']==block['block'])
    return canonical_raw(refpath.parent,target)


def compare_outputs(base,other,out):
    import numpy as np
    roots=[Path(base),Path(other)];runs=[read(p/'metrics.json') for p in roots]
    token_docs=[read(p/'tokens.json') for p in roots]
    if token_docs[0]!=token_docs[1]:
        raise RuntimeError('Comparison inputs differ')
    if any(r['purpose']=='latency' for r in runs):
        raise RuntimeError('Use nonlatency raw evidence for numerical comparison')
    count=agree=elements=0;maxerr=abssum=squares=0.;nll=[0.,0.];nll32=[0.,0.];identity=True;raw=[];arithmetic=[[],[]]
    for idx,t in enumerate(token_docs[0]['blocks']):
        entries=[canonical_raw(p,r['rounds'][0]['blocks'][idx]) for p,r in zip(roots,runs)]
        arrays=[];hashes=[]
        for p,b in entries:
            h=sha256(p)
            if h!=b['raw_logits_sha256']:raise RuntimeError('Raw file changed')
            arrays.append(np.load(p,mmap_mode='r',allow_pickle=False));hashes.append(h)
        if arrays[0].shape!=arrays[1].shape or arrays[0].shape[0]!=128 or any(x.dtype!=np.float32 for x in arrays):
            raise RuntimeError('Invalid logits shape/dtype')
        identity=identity and hashes[0]==hashes[1]
        for row,target in enumerate(t['targets']):
            vals=[x[row].astype(np.float64) for x in arrays]
            if not all(np.isfinite(x).all() for x in vals):raise RuntimeError('Nonfinite logits')
            d=vals[1]-vals[0];maxerr=max(maxerr,float(np.abs(d).max()));abssum+=float(np.abs(d).sum());squares+=float((d*d).sum());elements+=d.size
            count+=1;agree+=int(np.argmax(vals[0])==np.argmax(vals[1]))
            for i,v in enumerate(vals):
                mx=v.max();loss=float(mx+np.log(np.exp(v-mx).sum())-v[target]);nll[i]+=loss
                fp32=entries[i][1]['nll_per_token_fp32_torch'][row];nll32[i]+=fp32;arithmetic[i].append(abs(fp32-loss))
        raw.append({'block':t['block'],'sha256':hashes,'exact':hashes[0]==hashes[1]})
    delta=(nll[1]-nll[0])/count;delta32=(nll32[1]-nll32[0])/count
    result={'model':runs[0]['model'],'length':runs[0]['length'],'baseline_mode':runs[0]['mode'],'candidate_mode':runs[1]['mode'],
        'scored_tokens':count,'top1_agreement':agree/count,'raw_files_byte_identical':identity,'exact_quality_gate':identity,
        'max_abs_logit_difference':maxerr,'mean_abs_logit_difference':abssum/elements,'rms_logit_difference':math.sqrt(squares/elements),
        'mean_nll_fp64':[v/count for v in nll],'mean_nll_fp32':[v/count for v in nll32],'delta_nll_fp64':delta,'delta_nll_fp32':delta32,
        'legacy_compatibility_gate':agree/count>=.99 and delta<=.01 and delta32<=.01,
        'legacy_thresholds':{'top1_min':.99,'delta_nll_max':.01},
        'compatibility_not_semantic_correctness':'BF16 rounding differences/top1 agreement are not ground-truth accuracy; modern SDPA performance is not discarded solely for failing this gate.',
        'fp32_fp64_arithmetic_audit':{'tolerance':5e-5,'max_abs_error':[max(x) for x in arithmetic],'exceedances':[sum(v>5e-5 for v in x) for x in arithmetic],'pass':all(v<=5e-5 for x in arithmetic for v in x)},'raw_checks':raw}
    write_json(out,result);return result


def compare_times(base,other,out):
    runs=[read(Path(p)/'metrics.json') for p in (base,other)]
    if any(r['purpose']!='latency' for r in runs):raise ValueError('Unsampled latency required')
    if any(not b['matches_memory_run_raw_payload'] for r in runs for rnd in r['rounds'] for b in rnd['blocks']):raise ValueError('Unverified latency outputs')
    med=[statistics.median(x['workload_seconds'] for x in r['rounds']) for r in runs]
    result={'model':runs[0]['model'],'length':runs[0]['length'],'baseline_mode':runs[0]['mode'],'candidate_mode':runs[1]['mode'],
        'process_medians_seconds':med,'candidate_vs_baseline_ratio':med[1]/med[0],
        'round_seconds':[[x['workload_seconds'] for x in r['rounds']] for r in runs],
        'warning':'One process block, not9 independent samples. No no-slowdown claim without separate fixed analysis.'}
    write_json(out,result);return result


def freeze(a,plan):
    reg=read(a.registry);a.out.mkdir(parents=True,exist_ok=False)
    src=a.out/'harness';src.mkdir()
    for p in Path(__file__).parent.iterdir():
        if p.suffix in ('.py','.md','.txt'):shutil.copy2(p,src/p.name)
    inputs=a.out/'inputs';inputs.mkdir()
    for alias,m in reg['models'].items():
        m['snapshot_path']=str(resolve(a.registry.parent,m['snapshot_path']))
        tok=resolve(a.registry.parent,m['token_file']);shutil.copy2(tok,inputs/f'{alias}-tokens.json')
        m['token_file']=f'inputs/{alias}-tokens.json'
    registry=a.out/'registry.json';write_json(registry,reg)
    plan['registry_sha256']=sha256(registry)
    plan['source_sha256']={p.name:sha256(p) for p in src.iterdir()}
    monitor=None
    if a.monitor:
        dest=a.out/'instrumentation';dest.mkdir()
        for p in a.monitor.parent.iterdir():
            if p.suffix in ('.py','.txt','.md'):shutil.copy2(p,dest/p.name)
        monitor=dest/a.monitor.name
        plan['instrumentation_sha256']={p.name:sha256(p) for p in dest.iterdir()}
    plan['argv']=sys.argv;plan['runtime']=RUNTIME
    plan['requested_sampling_interval_ms']=a.interval_ms
    plan['probe_root']=str(a.probe_root) if a.probe_root else None
    plan['quality_root']=str(a.quality_root) if a.quality_root else None
    write_json(a.out/'run-plan.json',plan)
    (a.out/'pip-freeze.txt').write_text(subprocess.check_output([sys.executable,'-m','pip','freeze'],text=True))
    return src,registry,monitor


def probe_status(probe_root,model,length,mode,registry,uuid=None,stage='probe'):
    p=Path(probe_root)/stage/cell_key(model,length)/f'repeat-0-{mode}'
    if not (p/'metrics.json').exists() or not (p/'process-exit.json').exists():return False,'Missing successful probe'
    m=read(p/'metrics.json')
    if read(p/'process-exit.json')['returncode']!=0 or not (m.get('diagnostic_semantics') or {}).get('pass'):
        return False,'Probe semantic/runtime failure'
    if (m['model'],m['length'],m['mode'])!=(model,length,mode) or m.get('purpose')!=stage:return False,'Diagnostic cell/purpose mismatch'
    if m['model_revision']!=registry['models'][model]['revision']:return False,'Probe revision mismatch'
    if m.get('runtime') != RUNTIME:return False,'Probe runtime mismatch'
    if uuid and str(m.get('gpu_uuid')).removeprefix('GPU-') != str(uuid).removeprefix('GPU-'):return False,'Probe GPU UUID mismatch'
    probe_reg=read(Path(probe_root)/'registry.json')
    if probe_reg['models'][model]['token_file_sha256'] != registry['models'][model]['token_file_sha256']:return False,'Probe tokens mismatch'
    for filename in ('benchmark_inplace.py','attention_adapters.py','inplace_mlp.py'):
        old=Path(probe_root)/'harness'/filename
        if not old.exists() or sha256(old) != sha256(Path(__file__).parent/filename):return False,'Probe source mismatch: '+filename
    if mode=='sdpa_inplace':
        comparison=Path(probe_root)/stage/cell_key(model,length)/'comparison-0-sdpa-vs-sdpa_inplace.json'
        if not comparison.exists() or not read(comparison)['exact_quality_gate']:return False,'Inplace SDPA exact gate failed'
    return True,None


def quality_status(quality_root,model,registry,uuid=None):
    """Candidate-only gate; stock baselines remain measurable on failure."""
    try:
        for mode in ('sdpa','sdpa_inplace'):
            ok,why=probe_status(quality_root,model,2048,mode,registry,uuid,stage='quality')
            if not ok:return False,'Quality '+mode+': '+why
        comparison=read(Path(quality_root)/'quality'/cell_key(model,2048)/'comparison-0-sdpa-vs-sdpa_inplace.json')
        if comparison.get('scored_tokens')!=1024:return False,'Quality sweep must score1024 tokens'
        return True,None
    except (OSError,ValueError,KeyError,TypeError) as exc:
        return False,'Quality evidence unreadable/incomplete: '+str(exc)


def orchestrate(a):
    plan=execution_plan(a.command,[a.model] if a.model else None,[a.length] if a.length else None,a.randomization_seed)
    if a.command=='matrix' and (not a.monitor or not a.uuid or not a.probe_root or not a.quality_root):
        raise ValueError('Matrix requires monitor, UUID, probe root and quality root')
    reg=read(a.registry)
    for alias in {x['model'] for x in plan['cells']}:
        load_inputs(a.registry,alias)
    # Full raw arrays only first-memory/probe/quality; later runs keep hashes.
    required=500_000_000
    for c in plan['cells']:
        config=read(resolve(a.registry.parent,reg['models'][c['model']]['snapshot_path'])/'config.json')
        required+=len(MODES)*128*config['vocab_size']*4*(8 if a.command=='quality' else 1)
    parent=a.out.parent
    while not parent.exists():parent=parent.parent
    free=shutil.disk_usage(parent).free
    if free<required:raise RuntimeError(f'Need{required} free bytes, found{free}; nothing deleted')
    plan['disk_preflight']={'required_raw_plus_safety_bytes':required,'free_bytes':free}
    frozen,registry,monitor=freeze(a,plan)
    env=dict(os.environ,CUBLAS_WORKSPACE_CONFIG=':4096:8',TOKENIZERS_PARALLELISM='false',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1',PYTHONUNBUFFERED='1')
    for k in list(env):
        if k.startswith('PHYSICAL_PEAK_'):env.pop(k)
    failures=[];disabled={};comparisons=[]
    for purpose in plan['purposes']:
        for cell in plan['cells']:
            model,length=cell['model'],cell['length'];ck=cell_key(model,length)
            parent=a.out/purpose/ck;parent.mkdir(parents=True,exist_ok=True)
            for repeat,order in enumerate(plan['pair_orders'][ck][purpose]):
                completed_modes=[]
                for mode in order:
                    key=(ck,mode)
                    if key in disabled:continue
                    if a.command=='matrix' and mode=='sdpa_inplace':
                        ok,why=quality_status(a.quality_root,model,reg,a.uuid)
                        if not ok:
                            disabled[key]=why;failures.append({'cell':ck,'mode':mode,'stage':'quality_gate','reason':why})
                            continue
                    if purpose=='latency' and mode=='sdpa_inplace':
                        gates=[a.out/'memory'/ck/f'comparison-{i}-sdpa-vs-sdpa_inplace.json' for i in range(REPEATS)]
                        if not all(p.exists() and read(p).get('exact_quality_gate') for p in gates):
                            disabled[key]='All six memory SDPA/inplace exact gates required before candidate timing'
                            failures.append({'cell':ck,'mode':mode,'stage':'exact_gate','reason':disabled[key]})
                            continue
                    if a.command=='matrix':
                        ok,why=probe_status(a.probe_root,model,length,mode,reg,a.uuid)
                        if not ok:
                            disabled[key]=why;failures.append({'cell':ck,'mode':mode,'stage':'probe_gate','reason':why});continue
                    dest=parent/f'repeat-{repeat}-{mode}';dest.mkdir()
                    cmd=[sys.executable,str(frozen/'benchmark_inplace.py'),'worker','--registry',str(registry),'--out',str(dest),'--model',model,'--length',str(length),'--mode',mode,'--purpose',purpose,'--repeat',str(repeat)]
                    if purpose=='latency' or purpose=='memory' and repeat>0:
                        ref=a.out/'memory'/ck/f'repeat-0-{mode}'/'metrics.json';cmd+=['--reference',str(ref)]
                    if purpose=='memory':
                        cmd=[sys.executable,str(monitor),'--uuid',a.uuid,'--output',str(dest/'physical'),'--interval-ms',str(a.interval_ms),'--',*cmd]
                    write_json(dest/'command.json',{'argv':cmd})
                    print('START',purpose,ck,repeat,mode,flush=True)
                    with (dest/'worker.log').open('w') as log:
                        result=subprocess.run(cmd,env=env,stdout=log,stderr=subprocess.STDOUT)
                    write_json(dest/'process-exit.json',{'returncode':result.returncode})
                    if result.returncode:
                        disabled[key]='Worker runtime/semantic/output failure'
                        failures.append({'cell':ck,'mode':mode,'purpose':purpose,'repeat':repeat,'returncode':result.returncode,'path':str(dest.relative_to(a.out))})
                        print('FAILED',purpose,ck,repeat,mode,result.returncode,flush=True)
                    else:completed_modes.append(mode)
                for baseline,candidate in [('sdpa','sdpa_inplace')]:
                    if not all(m in completed_modes for m in (baseline,candidate)):continue
                    out=parent/f'comparison-{repeat}-{baseline}-vs-{candidate}.json'
                    fn=compare_times if purpose=='latency' else compare_outputs
                    result=fn(parent/f'repeat-{repeat}-{baseline}',parent/f'repeat-{repeat}-{candidate}',out)
                    comparisons.append({'purpose':purpose,'repeat':repeat,**result})
                    if purpose!='latency' and baseline=='sdpa' and candidate=='sdpa_inplace' and not result['exact_quality_gate']:
                        disabled[(ck,'sdpa_inplace')]='Exact SDPA contract failed; subsequent candidate/timing skipped'
                        failures.append({'cell':ck,'mode':'sdpa_inplace','reason':disabled[(ck,'sdpa_inplace')],'comparison':str(out.relative_to(a.out))})
                    print('COMPARE',purpose,ck,repeat,baseline,candidate,json.dumps({k:result[k] for k in ('exact_quality_gate','legacy_compatibility_gate','delta_nll_fp64','candidate_vs_baseline_ratio') if k in result}),flush=True)
            write_json(a.out/'progress.json',{'last_purpose':purpose,'last_cell':ck,'failures':failures})
    write_json(a.out/'summary.json',{'schema':'modern-matrix-summary-v1','stage':a.command,'status':'completed_with_failures' if failures else 'completed',
        'comparisons':comparisons,'failures':failures,'no_universal_claim':True,
        'physical_warning':'NVML sampled observed maxima only; probe/quality memory and timings not benchmark evidence.'})


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=('probe','matrix','quality','worker'))
    p.add_argument('--registry',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--model',choices=MODELS);p.add_argument('--length',type=int,choices=LENGTHS)
    p.add_argument('--mode',choices=MODES);p.add_argument('--purpose',choices=('probe','quality','memory','latency'))
    p.add_argument('--repeat',type=int,default=0);p.add_argument('--reference',type=Path)
    p.add_argument('--monitor',type=Path);p.add_argument('--uuid');p.add_argument('--interval-ms',type=float,default=1.)
    p.add_argument('--quality-root',type=Path);p.add_argument('--probe-root',type=Path);p.add_argument('--randomization-seed',type=int,default=SEED)
    a=p.parse_args();a.registry=a.registry.resolve();a.out=a.out.resolve()
    for name in ('reference','monitor','probe_root','quality_root'):
        if getattr(a,name):setattr(a,name,getattr(a,name).resolve())
    if a.command=='worker':
        if any(getattr(a,k) is None for k in ('model','length','mode','purpose')):p.error('worker requires model,length,mode,purpose')
        a.out.mkdir(parents=True,exist_ok=True)
        if (a.out/'metrics.json').exists() or (a.out/'phases.jsonl').exists():p.error('Never overwrite prior worker evidence')
        worker(a)
    else:orchestrate(a)


if __name__=='__main__':
    main()
