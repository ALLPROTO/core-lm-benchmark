"""Inference-only RMSNorm scratch reuse. Independent ablation, not codec."""
import inspect,types,hashlib
EXPECTED = '''    def forward(self, hidden_states: torch.Tensor) -> torch.Tensor:
        input_dtype = hidden_states.dtype
        hidden_states = hidden_states.to(torch.float32)
        variance = hidden_states.pow(2).mean(-1, keepdim=True)
        hidden_states = hidden_states * torch.rsqrt(variance + self.variance_epsilon)
        return self.weight * hidden_states.to(input_dtype)
'''
def install(model):
 import torch,transformers
 if transformers.__version__!='5.14.1':raise RuntimeError('Pinned Transformers required')
 if model.config.model_type not in ('qwen2','llama'):raise ValueError('Unregistered model')
 stats={'calls':0,'modules':0,'source_sha256':hashlib.sha256(EXPECTED.encode()).hexdigest()}
 for norm in model.modules():
  if type(norm).__name__ not in ('Qwen2RMSNorm','LlamaRMSNorm'):continue
  if inspect.getsource(type(norm).forward)!=EXPECTED:raise RuntimeError('Norm source changed')
  if hasattr(norm,'_corelm_original_forward'):raise RuntimeError('Already patched')
  norm._corelm_original_forward=norm.forward
  def forward(self,x):
   if torch.is_grad_enabled() or self.training or x.dtype!=torch.bfloat16 or self.weight.dtype!=torch.bfloat16:
    raise RuntimeError('BF16 no-grad inference only')
   if self._forward_hooks or self._forward_pre_hooks:
    raise RuntimeError('Observers/hooks may retain aliased intermediate tensors')
   # New FP32 allocation, never alias caller's residual BF16 tensor.
   work=x.to(torch.float32)
   variance=work.pow(2).mean(-1,keepdim=True)
   work.mul_(torch.rsqrt(variance+self.variance_epsilon))
   out=work.to(x.dtype)
   out.mul_(self.weight)
   stats['calls']+=1
   return out
  norm.forward=types.MethodType(forward,norm);stats['modules']+=1
 return stats
