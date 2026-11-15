# Isolated synthetic unit controls only, never benchmark evidence.
import unittest,torch
from transformers import Qwen2Config,Qwen2ForCausalLM,LlamaConfig,LlamaForCausalLM
from inplace_norm import install
class Controls(unittest.TestCase):
 def test_exact_no_alias(self):
  for cls,cfg in [(Qwen2ForCausalLM,Qwen2Config),(LlamaForCausalLM,LlamaConfig)]:
   m=cls(cfg(hidden_size=32,intermediate_size=64,num_hidden_layers=1,num_attention_heads=4,num_key_value_heads=2,vocab_size=64)).eval().to(torch.bfloat16)
   x=torch.randn(1,17,32,dtype=torch.bfloat16);original=x.clone()
   with torch.inference_mode():expected=m.model.norm(x)
   st=install(m)
   with torch.inference_mode():actual=m.model.norm(x)
   self.assertTrue(torch.equal(expected,actual));self.assertTrue(torch.equal(x,original));self.assertEqual(st['calls'],1)
   with self.assertRaises(RuntimeError):m.model.norm(x)
if __name__=='__main__':unittest.main()
