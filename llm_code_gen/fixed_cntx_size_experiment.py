###########################################################
# Experiment with lines masked with varying context sizes #
###########################################################

from helpers import *
import argparse
random.seed(0)

parser = argparse.ArgumentParser(description= "LLM code anomaly alanysis")
parser.add_argument("--model", type=str, default="codellama", help="Model name: ['codellama-13B', 'codeqwen1.5-7B', 'starcoder2-15B', 'starcoderbase', 'deepseek-coder-xb-base', 'gpt-xx']")
parser.add_argument("--ignore_space", action="store_true", help="Ignore white space tokens during loss calculation")
args = parser.parse_args()

bugs_json = load_magma_bugs_json()

root_dir = get_git_root_dir() + '/result/llm_code_gen'
if args.ignore_space:
    root_dir += "/ignore_whitespace"

CL = None
if args.model == "codellama-13B":
    root_dir += '/codellama'
    CL = CodeLlama13B()
elif args.model == "codeqwen1.5-7B":
    root_dir += '/codeqwen'
    CL = CodeQwen7B()
elif args.model == "starcoder2-15B":
    root_dir += '/starcoder'
    CL = StarCoder2()
elif args.model == "starcoderbase":
    root_dir += '/starcoderbase'
    CL = StarCoderBase()
elif 'deepseek-coder-' in args.model:
    root_dir += '/' + args.model
    model_size = args.model.split('deepseek-coder-')[1].split('b')[0]
    CL = DeepseekCoder(model_size)
elif 'gpt' in args.model:
    root_dir += '/' + args.model
    CL = OpenAIGPT(args.model)
else:
    assert False, "Invalid model name"

cve_lines_cntx_csv = f"{root_dir}/masked_cve_lines_varying_ctx.csv"
patch_lines_cntx_csv = f"{root_dir}/masked_patch_lines_varying_ctx.csv"
sampled_lines_cntx_csv = f"{root_dir}/masked_sampled_lines_varying_ctx.csv"
timer_file = f"{root_dir}/timer_cntx.txt"
cntx_szs = [ 250, 200, 150, 100, 50, 30, 20, 10, 5, 1 ]
max_tokens = 183

with open(cve_lines_cntx_csv, 'w') as cve_csv, \
    open(patch_lines_cntx_csv, 'w') as patch_csv, \
    open(sampled_lines_cntx_csv, 'w') as sampled_csv, \
    open(timer_file, 'w') as timer_txt:
    cve_writer = csv.writer(cve_csv)
    fix_writer = csv.writer(patch_csv)
    sampled_writer = csv.writer(sampled_csv)
    cve_writer.writerow(['file', 'masked_line_no', 'cntx_start', 'cntx_end', 'masked_line', 'prediction', 'whole_prediction', 'loss'])
    fix_writer.writerow(['file', 'masked_line_no', 'cntx_start', 'cntx_end', 'masked_line', 'prediction', 'whole_prediction', 'loss'])
    sampled_writer.writerow(['file', 'masked_line_no', 'cntx_start', 'cntx_end', 'masked_line', 'prediction', 'whole_prediction', 'loss'])

    for cntx_size in tqdm(cntx_szs, desc= "Context", position=0):
        # Set timer
        print("=====================================================", file=timer_txt)
        print("Running Context size: " + str(cntx_size), file=timer_txt)
        start_time = time.time()
        # Set GPU monitor
        gpu_stats_file = f"{root_dir}/gpu_stats_cntx_{cntx_size}.csv"
        gpu_monitor = RepeatTimer(2.5, get_gpu_memory, args=[gpu_stats_file])
        gpu_monitor.start()

        for file in tqdm(bugs_json, desc= "Files", position=1):
            cve_file    = bugs_json[file]["file_with_cve"]
            fix_file    = bugs_json[file]["file_with_fix"]
            cve_lines   = bugs_json[file]["cve_lines"]
            sampled_lines = bugs_json[file]["sampled_lines"]
            patch_lines = bugs_json[file]["patch_lines"]

            # Sampled non-vulnerable lines
            mask_lines = [ int(x) for x in flatten(sampled_lines) ]
            for line_no in mask_lines:
                try:
                    masked_line, prompt = get_lines(
                        cve_file,
                        int(line_no),
                        cntx_size,
                        cntx_size
                        )
                    filling = CL.infill(prompt, max_tokens)
                    prediction = filling.strip().split("\n")[0].strip()
                    start = max(line_no - cntx_size, 0)
                    end = line_no + cntx_size
                    torch.cuda.empty_cache()

                    loss = None
                    try:
                        label = CL.process_label(masked_line)
                        all_logits, label_ids = CL.teaching_forcing([prompt], [label], max_tokens, filling, args.ignore_space)
                        all_losses = CL.calculate_loss([prompt], all_logits, label_ids)
                        loss = all_losses[0]
                        del all_logits, label_ids, all_losses
                        torch.cuda.empty_cache()
                    except torch.cuda.OutOfMemoryError as e:
                        sampled_writer.writerow([cve_file, line_no, start, end, masked_line.strip(), prediction, filling, -1])
                        continue

                    sampled_writer.writerow([cve_file, line_no, start, end, masked_line.strip(), prediction, filling, loss])
                except Exception as e:
                    print(f"Error: {e}: {cve_file} + {line_no} + {cntx_size}")
                    continue


            # CVE lines
            mask_lines = [ int(x) for x in flatten(cve_lines) ]
            for line_no in mask_lines:
                masked_line, prompt = get_lines(
                    cve_file,
                    int(line_no),
                    cntx_size,
                    cntx_size
                    )
                filling = CL.infill(prompt, max_tokens)
                prediction = filling.strip().split("\n")[0].strip()
                start = max(line_no - cntx_size, 0)
                end = line_no + cntx_size
                torch.cuda.empty_cache()

                loss = None
                try:
                    label = CL.process_label(masked_line)
                    all_logits, label_ids = CL.teaching_forcing([prompt], [label], max_tokens, filling, args.ignore_space)
                    all_losses = CL.calculate_loss([prompt], all_logits, label_ids)
                    loss = all_losses[0]
                    del all_logits, label_ids, all_losses
                    torch.cuda.empty_cache()
                except torch.cuda.OutOfMemoryError as e:
                    cve_writer.writerow([cve_file, line_no, start, end, masked_line.strip(), prediction, filling, -1])
                    continue

                cve_writer.writerow([cve_file, line_no, start, end, masked_line.strip(), prediction, filling, loss])

            # patched lines
            mask_lines = [ int(x) for x in flatten(patch_lines) ]
            for line_no in mask_lines:
                masked_line, prompt = get_lines(
                    fix_file,
                    int(line_no),
                    cntx_size,
                    cntx_size)
                filling = CL.infill(prompt, max_tokens)
                prediction = filling.strip().split("\n")[0].strip()
                start = max(line_no - cntx_size, 0)
                end = line_no + cntx_size
                torch.cuda.empty_cache()
                
                loss = None
                try:
                    label = CL.process_label(masked_line)
                    all_logits, label_ids = CL.teaching_forcing([prompt], [label], max_tokens, filling, args.ignore_space)
                    all_losses = CL.calculate_loss([prompt], all_logits, label_ids)
                    loss = all_losses[0]
                    del all_logits, label_ids, all_losses
                    torch.cuda.empty_cache()
                except torch.cuda.OutOfMemoryError as e:
                    fix_writer.writerow([fix_file, line_no, start, end, masked_line.strip(), prediction, filling, -1])
                    continue

                fix_writer.writerow([fix_file, line_no, start, end, masked_line.strip(), prediction, filling, loss])

        end_time = time.time()
        print("Time taken: " + str(end_time - start_time), file=timer_txt)
        gpu_monitor.cancel()
        time.sleep(2)
