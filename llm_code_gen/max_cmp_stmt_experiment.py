import torch
from helpers import *
import argparse
import os
print(torch.cuda.get_device_name(0))

parser = argparse.ArgumentParser(description= "LLM code anomaly alanysis")
parser.add_argument("--model", type=str, default="codellama", help="Model name: ['codellama-13B', 'codellama-7B', 'codeqwen1.5-7B', 'starcoder2-15B', 'starcoderbase', 'codegen2-1B', 'codegen2-3_7B', 'codegen2-7B', 'codegen2-16B', 'deepseek-coder-xb-base', 'gpt-xx']")
parser.add_argument("--ignore_space", action="store_true", help="Ignore white space tokens during loss calculation")
parser.add_argument("--input_file", type=str, default="magma_buggy_and_nonbuggy_samples.json", help="Input json file")
parser.add_argument("--bsz", type=int, default=1, help="Batch size")
parser.add_argument("--use_beam", action="store_true", help="Use beam search for infilling")
args = parser.parse_args()

bugs_json = load_magma_bugs_json(args.input_file)

root_dir = get_git_root_dir() + '/result/llm_code_gen'
if args.ignore_space:
    root_dir += "/ignore_whitespace"

CL = None
if args.model == "codellama-13B":
    root_dir += '/codellama-13B'
    CL = CodeLlama13B()
elif args.model == "codellama-7B":
    root_dir += '/codellama-7B'
    CL = CodeLlama7B()
elif args.model == "codeqwen1.5-7B":
    root_dir += '/codeqwen'
    CL = CodeQwen7B()
elif args.model == "starcoder2-15B":
    root_dir += '/starcoder'
    CL = StarCoder2()
elif args.model == "starcoderbase":
    root_dir += '/starcoderbase'
    CL = StarCoderBase()
elif args.model in ['codegen2-1B', 'codegen2-3_7B', 'codegen2-7B', 'codegen2-16B']:
    root_dir += '/' + args.model
    model_size = args.model.split('-')[1].split('B')[0]
    CL = CodeGen2(model_size)
elif 'deepseek-coder-' in args.model:
    root_dir += '/' + args.model
    model_size = args.model.split('deepseek-coder-')[1].split('b')[0]
    CL = DeepseekCoder(model_size)
elif 'gpt' in args.model:
    root_dir += '/' + args.model
    CL = OpenAIGPT(args.model)
elif 'qwen2.5-coder-' in args.model:
    root_dir += '/' + args.model
    model_size = args.model.split('qwen2.5-coder-')[1].split('b')[0]
    CL = Qwen25Coder(model_size)
elif 'qwen2.5' in args.model and 'instruct-int4' in args.model:
    root_dir += '/' + args.model
    model_size = args.model.split('qwen2.5-')[1].split('b')[0]
    CL = Qwen25InstructQ4(model_size)
else:
    assert False, "Invalid model name"

root_dir += '_gpu' + str(os.environ["CUDA_VISIBLE_DEVICES"])

bsz = args.bsz
unfinished_examples = {}

def extract_compound_statement_no(compound_statement_no: list, line_no: int):
    # import json
    # extracted_comp_stat = []
    # tmp_file_components  = file.split('repo/')
    # project_name = tmp_file_components[0].split('targets/')[1]
    # tmp_name = tmp_file_components[1]
    # target_dir = root_dir + '/data/' +  project_name
    # file_name = tmp_name.replace('/', '_').replace('.', '_')
    # target_file = target_dir + '_' + file_name + '.json'
    # with open(target_file) as json_file:
    #     contents = json_file.read()
    # compound_statement_no = json.loads(contents)['CompoundStmt']
    extracted_comp_stat = []
    for interval in compound_statement_no:
        if line_no >= interval[0] and line_no <= interval[1]:
            extracted_comp_stat.append(interval)
    return sort_by_difference(extracted_comp_stat)

def sort_by_difference(lst):
    return sorted(lst, reverse=True, key=lambda x: x[1] - x[0])

###########################################################
# Experiment with lines masked with varying context sizes #
###########################################################

cve_lines_cntx_csv = f"{root_dir}/masked_cve_lines_max_comp_stmt_cntx.csv"
patch_lines_cntx_csv = f"{root_dir}/masked_patch_lines_max_comp_stmt_cntx.csv"
sampled_lines_cntx_csv = f"{root_dir}/masked_sampled_lines_max_comp_stmt_cntx.csv"
# cntx_szs = [ 250, 200, 150, 100, 50, 30, 20, 10, 5, 1 ]
# max_tokens = 100

with open(cve_lines_cntx_csv, 'w') as cve_csv, \
    open(patch_lines_cntx_csv, 'w') as patch_csv, \
    open(sampled_lines_cntx_csv, 'w') as sampled_csv:
    cve_writer = csv.writer(cve_csv)
    fix_writer = csv.writer(patch_csv)
    sampled_writer = csv.writer(sampled_csv)
    cve_writer.writerow(['file', 'masked_line_no', 'cntx_start', 'cntx_end', 'masked_line', 'prediction', 'whole_prediction', 'loss', 'generated_tokens', 'log_prob_scores', 'first_token_var'])
    fix_writer.writerow(['file', 'masked_line_no', 'cntx_start', 'cntx_end', 'masked_line', 'prediction', 'whole_prediction', 'loss', 'generated_tokens', 'log_prob_scores', 'first_token_var'])
    sampled_writer.writerow(['file', 'masked_line_no', 'cntx_start', 'cntx_end', 'masked_line', 'prediction', 'whole_prediction', 'loss', 'generated_tokens', 'log_prob_scores', 'first_token_var'])

    # Set timer
    start_time = time.time()
    # Set GPU monitor
    gpu_stats_file = f"{root_dir}/gpu_stats_max_comp_stmt_cntx.csv"
    gpu_monitor = RepeatTimer(2.5, get_gpu_memory, args=[gpu_stats_file])
    gpu_monitor.start()

    for file in tqdm(bugs_json, desc= "Files", position=0, leave=True):
        cve_file    = bugs_json[file]["file_with_cve"]
        fix_file    = bugs_json[file]["file_with_fix"]
        cve_lines   = bugs_json[file]["cve_lines"]
        patch_lines = bugs_json[file]["patch_lines"]
        sampled_lines = bugs_json[file]["sampled_lines"]

        masked_line_batch = []
        prompt_batch = []
        label_batch = []
        line_nos = []
        start_end_pairs = []

        # Sampled non-vulnerable lines
        mask_lines = [ int(x) for x in flatten(sampled_lines) ]
        # if file.endswith(".h") or file.endswith(".in"):
        #     continue
        for i in tqdm(range(len(mask_lines)), desc="Lines", leave=False):
            line_no = mask_lines[i]
            extracted_comp_stat = list()
            if str(line_no) in bugs_json[file]["sampled_comp_stat"]:
                extracted_comp_stat = extract_compound_statement_no(bugs_json[file]["sampled_comp_stat"][str(line_no)], line_no)
            # if len(extracted_comp_stat) == 0:
            extracted_comp_stat.append([int(line_no) - 150, int(line_no) + 150])
            # extracted_comp_stat[0][0] -= 5 # Compensate for the function definition
            for level in range(len(extracted_comp_stat)):
                start_end_pair = extracted_comp_stat[level]
                start_end_pair[0] -= 5 # Compensate for the scope begining
                masked_line, prompt = get_lines(
                    cve_file,
                    int(line_no),
                    int(line_no) - start_end_pair[0],
                    start_end_pair[1] - int(line_no)
                    )
                if start_end_pair[1] - start_end_pair[0] < 500:
                    break

            if (len(prompt_batch) < bsz):
                prompt_batch.append(prompt)
                label_batch.append(CL.process_label(masked_line))
                line_nos.append(line_no)
                start_end_pairs.append(start_end_pair)
                masked_line_batch.append(masked_line)
            
            if (len(prompt_batch) == bsz) or (i == len(mask_lines) - 1):
                max_tokens = int(len(max(CL.tokenizer(masked_line_batch)['input_ids'], key=len)) * 1.5)

                try:
                    fillings, generated_tokens, log_prob_scores, first_token_var = CL.infill(prompt_batch, max_tokens, args.use_beam)
                    predictions = [filling.strip().split("\n")[0].strip() for filling in fillings]
                    all_logits, label_ids = CL.teaching_forcing(prompt_batch, label_batch, max_tokens, fillings, args.ignore_space)
                    all_losses = CL.calculate_loss(prompt_batch, all_logits, label_ids)

                    for j in range(len(prompt_batch)):
                        loss = all_losses[j]
                        start = start_end_pairs[j][0]
                        end =  start_end_pairs[j][1]
                        masked_line = masked_line_batch[j]
                        sampled_writer.writerow([cve_file, line_nos[j], start, end, masked_line.strip(), predictions[j], fillings[j], loss, generated_tokens[j].tolist(), log_prob_scores[j].tolist(), first_token_var[j].item()])
                except Exception as e:
                    print(str(e) + "\n" + "In file: " + file + "\nAt Lines:", line_nos)
                    if file not in unfinished_examples:
                        unfinished_examples[file] = {
                            "file_with_cve" : cve_file,
                            "file_with_fix" : fix_file,
                            "cve_lines" : [],
                            "patch_lines" : [],
                            "sampled_lines" : [],
                            "cve_comp_stat": {},
                            "sampled_comp_stat": {},
                            "patch_comp_stat": {}
                        }
                    for j in range(len(prompt_batch)):
                        unfinished_examples[file]["sampled_lines"].append(str(line_nos[j]))
                        unfinished_examples[file]["sampled_comp_stat"][str(line_nos[j])] = bugs_json[file]["sampled_comp_stat"][str(line_nos[j])]


                prompt_batch = []
                label_batch = []
                line_nos = []
                start_end_pairs = []
                masked_line_batch = []

        # CVE lines
        mask_lines = [ int(x) for x in flatten(cve_lines) ]
        # if file.endswith(".h") or file.endswith(".in"):
        #     continue
        for i in tqdm(range(len(mask_lines)), desc="Lines", leave=False):
            line_no = mask_lines[i]
            extracted_comp_stat = list()
            if str(line_no) in bugs_json[file]["cve_comp_stat"]:
                extracted_comp_stat = extract_compound_statement_no(bugs_json[file]["cve_comp_stat"][str(line_no)], line_no)
            # if len(extracted_comp_stat) == 0:
            extracted_comp_stat.append([int(line_no) - 150, int(line_no) + 150])
            # extracted_comp_stat[0][0] -= 5 # Compensate for the function definition
            for level in range(len(extracted_comp_stat)):
                start_end_pair = extracted_comp_stat[level]
                start_end_pair[0] -= 5 # Compensate for the scope begining
                masked_line, prompt = get_lines(
                    cve_file,
                    int(line_no),
                    int(line_no) - start_end_pair[0],
                    start_end_pair[1] - int(line_no)
                    )
                if start_end_pair[1] - start_end_pair[0] < 500:
                    break

            if (len(prompt_batch) < bsz):
                prompt_batch.append(prompt)
                label_batch.append(CL.process_label(masked_line))
                line_nos.append(line_no)
                start_end_pairs.append(start_end_pair)
                masked_line_batch.append(masked_line)
            
            if (len(prompt_batch) == bsz) or (i == len(mask_lines) - 1):
                max_tokens = int(len(max(CL.tokenizer(masked_line_batch)['input_ids'], key=len)) * 1.5)

                try:
                    fillings, generated_tokens, log_prob_scores, first_token_var = CL.infill(prompt_batch, max_tokens, args.use_beam)
                    predictions = [filling.strip().split("\n")[0].strip() for filling in fillings]
                    all_logits, label_ids = CL.teaching_forcing(prompt_batch, label_batch, max_tokens, fillings, args.ignore_space)
                    all_losses = CL.calculate_loss(prompt_batch, all_logits, label_ids)

                    for j in range(len(prompt_batch)):
                        loss = all_losses[j]
                        start = start_end_pairs[j][0]
                        end =  start_end_pairs[j][1]
                        masked_line = masked_line_batch[j]
                        cve_writer.writerow([cve_file, line_nos[j], start, end, masked_line.strip(), predictions[j], fillings[j], loss, generated_tokens[j].tolist(), log_prob_scores[j].tolist(), first_token_var[j].item()])
                except Exception as e:
                    print(str(e) + "\n" + "In file: " + file + "\nAt Lines:", line_nos)
                    if file not in unfinished_examples:
                        unfinished_examples[file] = {
                            "file_with_cve" : cve_file,
                            "file_with_fix" : fix_file,
                            "cve_lines" : [],
                            "patch_lines" : [],
                            "sampled_lines" : [],
                            "cve_comp_stat": {},
                            "sampled_comp_stat": {},
                            "patch_comp_stat": {}
                        }
                    for j in range(len(prompt_batch)):
                        unfinished_examples[file]["cve_lines"].append(str(line_nos[j]))
                        unfinished_examples[file]["cve_comp_stat"][str(line_nos[j])] = bugs_json[file]["cve_comp_stat"][str(line_nos[j])]

                prompt_batch = []
                label_batch = []
                line_nos = []
                start_end_pairs = []
                masked_line_batch = []

        # Patched lines
        mask_lines = [ int(x) for x in flatten(patch_lines) ]
        # if file.endswith(".h") or file.endswith(".in"):
        #     continue
        for i in tqdm(range(len(mask_lines)), desc="Lines", leave=False):
            line_no = mask_lines[i]
            extracted_comp_stat = list()
            if str(line_no) in bugs_json[file]["patch_comp_stat"]:
                extracted_comp_stat = extract_compound_statement_no(bugs_json[file]["patch_comp_stat"][str(line_no)], line_no)
            # if len(extracted_comp_stat) == 0:
            extracted_comp_stat.append([int(line_no) - 150, int(line_no) + 150])
            # extracted_comp_stat[0][0] -= 5 # Compensate for the function definition
            for level in range(len(extracted_comp_stat)):
                start_end_pair = extracted_comp_stat[level]
                start_end_pair[0] -= 5 # Compensate for the scope begining
                masked_line, prompt = get_lines(
                    fix_file,
                    int(line_no),
                    int(line_no) - start_end_pair[0],
                    start_end_pair[1] - int(line_no)
                    )
                if start_end_pair[1] - start_end_pair[0] < 500:
                    break

            if (len(prompt_batch) < bsz):
                prompt_batch.append(prompt)
                label_batch.append(CL.process_label(masked_line))
                line_nos.append(line_no)
                start_end_pairs.append(start_end_pair)
                masked_line_batch.append(masked_line)

            if (len(prompt_batch) == bsz) or (i == len(mask_lines) - 1):
                max_tokens = int(len(max(CL.tokenizer(masked_line_batch)['input_ids'], key=len)) * 1.5)

                try:
                    fillings, generated_tokens, log_prob_scores, first_token_var = CL.infill(prompt_batch, max_tokens, args.use_beam)
                    predictions = [filling.strip().split("\n")[0].strip() for filling in fillings]
                    all_logits, label_ids = CL.teaching_forcing(prompt_batch, label_batch, max_tokens, fillings, args.ignore_space)
                    all_losses = CL.calculate_loss(prompt_batch, all_logits, label_ids)

                    for j in range(len(prompt_batch)):
                        loss = all_losses[j]
                        start = start_end_pairs[j][0]
                        end =  start_end_pairs[j][1]
                        masked_line = masked_line_batch[j]
                        fix_writer.writerow([fix_file, line_nos[j], start, end, masked_line.strip(), predictions[j], fillings[j], loss, generated_tokens[j].tolist(), log_prob_scores[j].tolist(), first_token_var[j].item()])
                except Exception as e:
                    print(str(e) + "\n" + "In file: " + file + "\nAt Lines:", line_nos)
                    if file not in unfinished_examples:
                        unfinished_examples[file] = {
                            "file_with_cve" : cve_file,
                            "file_with_fix" : fix_file,
                            "cve_lines" : [],
                            "patch_lines" : [],
                            "sampled_lines" : [],
                            "cve_comp_stat": {},
                            "sampled_comp_stat": {},
                            "patch_comp_stat": {}
                        }
                    for j in range(len(prompt_batch)):
                        unfinished_examples[file]["patch_lines"].append(str(line_nos[j]))
                        unfinished_examples[file]["patch_comp_stat"][str(line_nos[j])] = bugs_json[file]["patch_comp_stat"][str(line_nos[j])]

                prompt_batch = []
                label_batch = []
                line_nos = []
                start_end_pairs = []
                masked_line_batch = []

        with open("unfinished_examples_max_comp_stmt_cntx_gpu" + str(os.environ["CUDA_VISIBLE_DEVICES"]) + ".json", "w") as f:
            json.dump(unfinished_examples, f, indent=2)
    
    end_time = time.time()
    print("=====================================================")
    print("Running Max Comp Stmt Cntx")
    print("Time taken: " + str(end_time - start_time))
    gpu_monitor.cancel()
    time.sleep(2)