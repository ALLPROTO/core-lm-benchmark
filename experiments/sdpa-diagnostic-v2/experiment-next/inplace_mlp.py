"""Experimental SDPA-preserving MLP buffer reuse, inference only.
No performance/quality claim until registered real-model GPU validation.
"""
import hashlib
import inspect
import types

EXPECTED_SOURCE = '''    def forward(self, x):
        down_proj = self.down_proj(self.act_fn(self.gate_proj(x)) * self.up_proj(x))
        return down_proj
'''

def install(model):
    import torch
    import transformers
    if transformers.__version__ != '5.14.1':
        raise RuntimeError('Pinned Transformers required')
    if model.config.model_type not in ('qwen2','llama') or model.config.hidden_act != 'silu':
        raise ValueError('Registered Qwen2/Llama SiLU models only')
    if model.config._attn_implementation != 'sdpa':
        raise ValueError('Unmodified SDPA is required')
    stats={'calls':0,'layers':0,'source_sha256':hashlib.sha256(EXPECTED_SOURCE.encode()).hexdigest(),
           'candidate':'sdpa_inplace_mlp','attention_changed':False}
    for layer in model.model.layers:
        mlp=layer.mlp
        if inspect.getsource(type(mlp).forward)!=EXPECTED_SOURCE:
            raise RuntimeError('MLP source changed')
        if hasattr(mlp,'_corelm_original_forward'):
            raise RuntimeError('Already patched')
        mlp._corelm_original_forward=mlp.forward
        def forward(self,x):
            if torch.is_grad_enabled() or self.training:
                raise RuntimeError('Inference-only adapter')
            if any(m._forward_hooks or m._forward_pre_hooks for m in self.modules()):
                raise RuntimeError('Observers/hooks may retain aliased intermediate tensors')
            gate=self.gate_proj(x)
            torch.nn.functional.silu(gate,inplace=True)
            up=self.up_proj(x)
            gate.mul_(up)
            del up
            stats['calls']+=1
            return self.down_proj(gate)
        mlp.forward=types.MethodType(forward,mlp)
        stats['layers']+=1
    return stats
