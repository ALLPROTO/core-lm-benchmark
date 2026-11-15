# Isolated generated unit controls, never model evidence.
import sys,unittest,torch
from transformers import Qwen2Config,Qwen2ForCausalLM,LlamaConfig,LlamaForCausalLM
from inplace_mlp import install
class Controls(unittest.TestCase):
 def test_exact_fixture(self):
  for cls,cfg in [(Qwen2ForCausalLM,Qwen2Config),(LlamaForCausalLM,LlamaConfig)]:
   m=cls(cfg(hidden_size=32,intermediate_size=64,num_hidden_layers=1,num_attention_heads=4,num_key_value_heads=2,vocab_size=64)).eval().to(torch.bfloat16)
   m.config._attn_implementation='sdpa'; mlp=m.model.layers[0].mlp
   x=torch.randn(1,17,32,dtype=torch.bfloat16)
   with torch.inference_mode():expected=mlp(x)
   stats=install(m)
   with torch.inference_mode():actual=mlp(x)
   self.assertTrue(torch.equal(expected,actual));self.assertEqual(stats['calls'],1)
   with self.assertRaises(RuntimeError): mlp(x)
   with torch.inference_mode():
    handle=mlp.gate_proj.register_forward_hook(lambda m,i,o: None)
    with self.assertRaises(RuntimeError):mlp(x)
    handle.remove()
 def test_reject_eager(self):
  m=Qwen2ForCausalLM(Qwen2Config(hidden_size=32,intermediate_size=64,num_hidden_layers=1,num_attention_heads=4,vocab_size=64))
  m.config._attn_implementation='eager'
  with self.assertRaises(ValueError):install(m)
if __name__=='__main__': unittest.main()
