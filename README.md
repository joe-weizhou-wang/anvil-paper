# ANVIL

Supervised-learning-based vulnerability detectors often fall short due to limited labelled training data. In contrast, Large Language Models (LLMs) are trained on vast unlabelled code corpora, yet perform only marginally better than coin flips when directly prompted to detect vulnerabilities. In this paper, we reframe vulnerability detection as anomaly detection, based on the premise that vulnerable code is rare and thus anomalous relative to patterns learned by LLMs. We introduce ANVIL, which performs a masked code reconstruction task: The LLM reconstructs a masked line of code, and deviations from the original are scored as anomalies. We propose a hybrid anomaly score that combines exact match, cross-entropy loss, prediction confidence, and structural complexity. We evaluate our approach across multiple LLM families, scoring methods, and context sizes, and against vulnerabilities after the LLM's training cut-off. On the PrimeVul dataset, ANVIL outperforms state-of-the-art supervised detectors – LineVul, LineVD, and LLMAO – achieving up to 2× higher Top-3 accuracy, 75% better Normalized MFR, and a significant improvement on ROC-AUC. Finally, by integrating ANVIL with fuzzers, we uncover two previously unknown vulnerabilities, demonstrating the practical utility of anomaly-guided detection.

Link to paper: https://arxiv.org/abs/2408.16028

<img width="929" height="267" alt="Screenshot 2026-07-01 at 22 03 36" src="https://github.com/user-attachments/assets/e538495f-cf2c-4a7d-88b5-71424ddf8af2" />


## Codebase Structure
```
data/
  - cve-targets                                         # All vulnerable versions of source files in Magma
  - fixed-targets                                       # All fixed versions of source files
  - magma                                               # All Magma dataset and line numbers used in LLM code generation
  - PrimeVul_v0.1                                       # PrimeVul dataset used in LLM code generation
  - 2024CVE_c_cpp                                       # 2024CVE line numbers used in LLM code generation
eval/                                                   # Evaluation script for RQs, Discussions and zero-day case studies
llm_code_gen/
  - different_cntx_size_experiment.py                   # Script to run different fixed context size experiments
  - max_cmp_stmt_experiment.py                          # Script to run Adaptive Context (AC) experiments
  - process_raw_results.py                              # Script to process raw LLM reconstruction results and compute anomaly scores
  - helpers.py                                          # Helper functions, including LLM configurations
result/                                                 # Results for reconstruction anomaly scores
scripts/
  - clean_repos.h & init_repos.h                        # Scripts to setup/cleanup environments for the Python script below to run
  - process_patched_files.py                            # Script to generate labels
  - static.tar.gz                                       # Scripts to extract compound statements
```

## To Reproduce

### Code Generation 
**This process can be time-consuming. Alternatively, you may choose to bypass it and proceed directly to the Evaluation section.**
```
cd llm_code_gen

# RQ1
python3 different_cntx_size_experiment.py --model <LLM_name> --ignore_space

# RQ2 and RQ3
python3 max_cmp_stmt_experiment.py --model <LLM_name> --ignore_space --input_file magma_buggy_and_nonbuggy_samples.json

# RQ4
CUDA_VISIBLE_DEVICES=0 python3 max_cmp_stmt_experiment.py --model codellama-13B --bsz 4 --ignore_space --input_file PrimeVul_v0.1/primevul_anvil_valid_test_total_mcs.json

# RQ5
CUDA_VISIBLE_DEVICES=0 python3 max_cmp_stmt_experiment.py --model codellama-13B --bsz 4 --ignore_space --input_file 2024_CVE_c_cpp/2024_CVE_bugs_and_sampled_lines_per_function_mcs.json
```

### Evaluation
```
cd eval

# Run .ipynb files under each folder
```

### Baselines
We fixed some bugs and also made some modifications for the baselines to accommodate the comparison as described in the paper.

#### LLMAO
```
cd baseline/LLMAO

python3 plotter.py model_logs/primevul_valid_test_all_comment_mask/devign_16B_512_9/
```

**Please first download the two baseline codebases from https://zenodo.org/records/15555391**
#### LineVul
```
cd LineVul
# Top-5 (modify "top_k_constant" for other Top-N results)
python linevul_main.py   --model_name=12heads_linevul_model.bin   --output_dir=./saved_models   --model_type=roberta   --tokenizer_name=microsoft/codebert-base   --model_name_or_path=microsoft/codebert-base   --do_test   --do_local_explanation   --top_k_constant=5   --reasoning_method=all   --train_data_file=../data/big-vul_dataset/train.csv   --eval_data_file=../data/big-vul_dataset/val.csv   --test_data_file=../data/big-vul_dataset/primevul_per_function_valid_test_vul.csv   --block_size 512 &> linevul_on_all_primevul_top5.log
grep "codebert_attention_top10_accuracy" linevul_on_all_primevul_top5.log  # Note: although we search for "top10", but it is actualy top5

# MFR
python linevul_main.py   --model_name=12heads_linevul_model.bin   --output_dir=./saved_models   --model_type=roberta   --tokenizer_name=microsoft/codebert-base   --model_name_or_path=microsoft/codebert-base   --do_test   --do_sorting_by_line_scores   --effort_at_top_k=0.2   --top_k_recall_by_lines=0.01   --top_k_recall_by_pred_prob=0.2   --reasoning_method=all   --train_data_file=../data/big-vul_dataset/train.csv --eval_data_file=../data/big-vul_dataset/val.csv   --test_data_file=../data/big-vul_dataset/primevul_per_function_valid_test_vul.csv   --block_size 512 --eval_batch_size 512 &> linevul_on_all_primevul_mfr.log
grep -A 20 "Reasoning Method: attention" linevul_on_all_primevul_mfr.log | grep "Mean First Rank"

# ROC-AUC
python linevul_main.py   --model_name=12heads_linevul_model.bin   --output_dir=./saved_models   --model_type=roberta   --tokenizer_name=microsoft/codebert-base   --model_name_or_path=microsoft/codebert-base   --do_test   --do_sorting_by_line_scores   --effort_at_top_k=0.2   --top_k_recall_by_lines=0.01   --top_k_recall_by_pred_prob=0.2   --reasoning_method=all   --train_data_file=../data/big-vul_dataset/train.csv --eval_data_file=../data/big-vul_dataset/val.csv   --test_data_file=../data/big-vul_dataset/primevul_per_function_valid_test_all.csv   --block_size 512 --eval_batch_size 512 &> linevul_on_all_primevul_roc.log
grep -A 20 "Reasoning Method: attention" linevul_on_all_primevul_roc.log | grep "ROC AUC"
```
#### LineVD
We adopted the modified version from the VGX paper
```
cd linevd-vgx
singularity exec --nv main2.sif bash
python3 sastvd/scripts/mytest_ori.py
# Top-5
grep "5:" checkpoint/lightning_logs/version_9/checkpoints/res.csv
# ROC-AUC
grep "roc_auc" checkpoint/lightning_logs/version_9/checkpoints/res.csv | tail -1
```

### Integration with Fuzzers
We directly used the Magma benchmark from (https://hexhive.epfl.ch/magma/)

To reproduce, please replace Magma's "targets" folder with "eval/discussion_fuzzing/targets_base" and "eval/discussion_fuzzing/targets_refined"

## SFML Zero-Day Case Studies

The bug reports and proof-of-concept inputs for the two SFML vulnerabilities discussed in the paper are available under `eval/sfml_zero_days/`.

- `sfml_music_heap_use_after_free.md`: heap-use-after-free in `sf::Music` caused by unsynchronized audio thread teardown. This bug was reported to SFML and patched, as described in https://github.com/SFML/SFML/issues/3503.
- `sfml_minimp3_heap_buffer_overflow.md`: heap-buffer-overflow in SFML's bundled `minimp3`, triggered through `sf::Music::openFromMemory()`. We reported this issue privately to the SFML maintainers through a GitHub Security Advisory thread (`GHSA-hq2x-cpx5-hmcm`; https://github.com/SFML/SFML/security/advisories/GHSA-hq2x-cpx5-hmcm, which may not be publicly accessible). Separately, we applied for and received the reserved CVE identifier `CVE-2025-50940`.

The corresponding proof-of-concept archives are:

- `poc_sfml_music_heap_use_after_free.zip`
- `poc_sfml_minimp3_heap_buffer_overflow.zip`


