"""Public-validation CPU regression only. Not GPU performance evidence."""
import os,sys,json,hashlib,time
from pathlib import Path
import torch
from transformers import AutoModelForCausalLM
from inplace_mlp import install as mlp_install
from inplace_norm import install as norm_install
root=Path(__file__).resolve().parent.parent
reg=json.loads((root/'experiment/registry-qwen-only.json').read_text()); spec=reg['models']['qwen05']
snapshot=(root/'experiment'/spec['snapshot_path']).resolve()
for asset in spec['assets']:
 p=snapshot/asset['path']
 with p.open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==asset['sha256']
tokenpath=root/'experiment/inputs/qwen05-tokens.json'
assert hashlib.sha256(tokenpath.read_bytes()).hexdigest()==spec['token_file_sha256']
ids=json.loads(tokenpath.read_text())['token_ids'][-4096:]
torch.set_num_threads(4);torch.use_deterministic_algorithms(True)
model=AutoModelForCausalLM.from_pretrained(snapshot,local_files_only=True,trust_remote_code=False,use_safetensors=True,dtype=torch.bfloat16,attn_implementation='sdpa').eval();model.requires_grad_(False)
def run():
 with torch.inference_mode():
  x=torch.tensor([ids]);p=model(x[:,:3967],use_cache=True,logits_to_keep=1);cache=p.past_key_values;del p
  y=model(x[:,3967:4095],past_key_values=cache,attention_mask=torch.ones(1,4095,dtype=torch.long),position_ids=torch.arange(3967,4095).unsqueeze(0),cache_position=torch.arange(3967,4095),use_cache=False)
  logits=y.logits.detach().clone()
 return logits
reference=run(); print('BASELINE_COMPLETE',flush=True)
mlp=mlp_install(model);candidate=run();print('MLP_COMPLETE',flush=True)
norm=norm_install(model);combined=run();print('COMBINED_COMPLETE',flush=True)
def cmp(y):
 return {'byte_exact':torch.equal(reference.view(torch.uint8),y.view(torch.uint8)),'max_abs':(reference.float()-y.float()).abs().max().item(),'shape':list(y.shape)}
r={'classification':'PUBLIC_VALIDATION_CPU_REGRESSION_ONLY_NOT_GPU_EVIDENCE','model_revision':spec['revision'],'tokens_sha256':hashlib.sha256(tokenpath.read_bytes()).hexdigest(),'torch':torch.__version__,'model':'qwen05','length':4096,'stock_sdpa_vs_mlp':cmp(candidate),'stock_sdpa_vs_mlp_norm':cmp(combined),'mlp_calls':mlp,'norm_calls':norm}
(root/'experiment-next/real-cpu-regression-4096.json').write_text(json.dumps(r,indent=2));print(json.dumps(r,indent=2))
