import shutil
import os

src = r"d:\AboutUniversity\114 NSTC_and_SeniorProject\2025-NSTC-undergraduate-research-proposal\RA-LLMs_ancientChinese_knowledgeQA_System\scripts\rag\qwen3_Encoder_rag_pipeline\chunking\run_hybrid_batch_temp.py"
dst = r"d:\AboutUniversity\114 NSTC_and_SeniorProject\2025-NSTC-undergraduate-research-proposal\RA-LLMs_ancientChinese_knowledgeQA_System\scripts\rag\qwen3_Encoder_rag_pipeline\chunking\run_hybrid_batch.py"

shutil.copy2(src, dst)
os.remove(src)
print("File copied and removed successfully.")
