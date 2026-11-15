from pathlib import Path
import shutil
p=Path(__file__).resolve().parent.parent/'experiment'
src=p/'implementation'/'benchmark_matrix.py'
s=src.read_text()
s=s.replace("MODES = ('eager', 'fused', 'sdpa', 'sdpa_lower_right')", "MODES = ('sdpa', 'sdpa_inplace')")
s=s.replace("    model.to('cuda')", "    if a.mode == 'sdpa_inplace':\n        from inplace_mlp import install\n        mlp_stats = install(model)\n    model.to('cuda')")
# Candidate still uses native SDPA semantic probe; its stats are recorded separately.
s=s.replace("'adapter':adapter", "'adapter':adapter")
s=s.replace("'adapter': adapter", "'mlp_adapter': mlp_stats if a.mode == 'sdpa_inplace' else None, 'adapter': adapter")
s=s.replace("'comparison': ['sdpa', 'fused']", "'comparison': ['sdpa', 'sdpa_inplace']")
s=s.replace("Fused requires exact eager outputs.", "Inplace MLP requires exact SDPA outputs.")
(p/'implementation'/'benchmark_inplace.py').write_text(s)
shutil.copyfile(Path(__file__).parent/'inplace_mlp.py',p/'implementation'/'inplace_mlp.py')
print('Generated new separate harness; original unchanged')
s=s.replace("('eager','fused')", "('sdpa','sdpa_inplace')").replace("mode=='fused'", "mode=='sdpa_inplace'")
s=s.replace("'comparison-0-eager-vs-fused.json'", "'comparison-0-sdpa-vs-sdpa_inplace.json'")
s=s.replace("f'comparison-{i}-eager-vs-fused.json'", "f'comparison-{i}-sdpa-vs-sdpa_inplace.json'")
s=s.replace("for filename in ('benchmark_matrix.py','attention_adapters.py','fused_scale_mask.py'):", "for filename in ('benchmark_inplace.py','attention_adapters.py','inplace_mlp.py'):")
s=s.replace("frozen/'benchmark_matrix.py'", "frozen/'benchmark_inplace.py'")
s=s.replace("[('eager',m) for m in MODES if m!='eager']+[('sdpa','fused'),('sdpa_lower_right','fused'),('sdpa','sdpa_lower_right')]", "[('sdpa','sdpa_inplace')]")
s=s.replace("baseline=='eager' and candidate=='fused'", "baseline=='sdpa' and candidate=='sdpa_inplace'")
s=s.replace("(ck,'fused')", "(ck,'sdpa_inplace')")
# Original eager-adapter invocation counts do not apply to unchanged SDPA attention.
s=s.replace("    if mode=='sdpa_inplace':\n        optimized=", "    if mode=='fused':\n        optimized=")
# Generic semantic probe: inplace uses native SDPA branch.
s=s.replace("if mode in ('sdpa','sdpa_inplace'):", "if mode in ('eager','fused'):")
(p/'implementation'/'benchmark_inplace.py').write_text(s)
s=s.replace("'adapter':adapter,'adapter_invocation_contract'", "'mlp_adapter':mlp_stats if a.mode=='sdpa_inplace' else None,'adapter':adapter,'adapter_invocation_contract'")
s=s.replace("    final_memory=memory()", "    if a.mode=='sdpa_inplace' and mlp_stats['calls'] != 2*layers*len(executed_lengths):\n        raise RuntimeError('MLP call-count mismatch')\n    final_memory=memory()")
s=s.replace("'reason':disabled[(ck,'sdpa_inplace')]", "'reason':disabled[(ck,'sdpa_inplace')]")
s=s.replace("'mode':'fused'", "'mode':'sdpa_inplace'")
s=s.replace('Fused exact gate failed','Inplace SDPA exact gate failed').replace('Exact eager contract failed','Exact SDPA contract failed').replace('All six memory eager/fused exact gates','All six memory SDPA/inplace exact gates')
(p/'implementation'/'benchmark_inplace.py').write_text(s)

combo=s.replace('sdpa_inplace','sdpa_inplace_combo').replace('benchmark_inplace.py','benchmark_combined.py')
combo=combo.replace('mlp_stats = install(model)','mlp_stats = install(model)\n        from inplace_norm import install as install_norm\n        norm_stats = install_norm(model)')
combo=combo.replace("'mlp_adapter':mlp_stats", "'norm_adapter':norm_stats if a.mode=='sdpa_inplace_combo' else None,'mlp_adapter':mlp_stats")
combo=combo.replace("'attention_adapters.py','inplace_mlp.py'", "'attention_adapters.py','inplace_mlp.py','inplace_norm.py'")
combo=combo.replace("    final_memory=memory()", "    if a.mode=='sdpa_inplace_combo' and (norm_stats['modules']!=2*layers+1 or norm_stats['calls']!=2*(2*layers+1)*len(executed_lengths)):\n        raise RuntimeError('Norm call-count mismatch')\n    final_memory=memory()")
(Path(__file__).parent/'benchmark_combined.py').write_text(combo)
