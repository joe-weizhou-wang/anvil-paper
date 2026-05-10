import csv
import json
import os
import subprocess
import sys
import torch
import random
import time
from openai import OpenAI
from tqdm import tqdm
from transformers import LlamaForCausalLM, CodeLlamaTokenizer
from transformers import AutoTokenizer, AutoModelForCausalLM

import subprocess as sp
import os
from threading import Thread , Timer

def occumpy_mem(cuda_device=0):
    devices_info = os.popen('"/usr/bin/nvidia-smi" --query-gpu=memory.total,memory.used --format=csv,nounits,noheader').read().strip().split("\n")
    total, used = devices_info[int(cuda_device)].split(',')
    total = int(total)
    used = int(used)
    max_mem = int(total * 0.9)
    block_mem = max_mem - used
    x = torch.cuda.FloatTensor(256,1024,block_mem)
    del x
# occumpy_mem()

class RepeatTimer(Timer):
    def run(self):
        while not self.finished.wait(self.interval):
            self.function(*self.args, **self.kwargs)

class CodeLlama13B:
    def __init__(self):
        self.model_path = "codellama/CodeLlama-13b-hf"
        self.tokenizer = CodeLlamaTokenizer.from_pretrained(self.model_path, device_map="cuda")
        self.model = LlamaForCausalLM.from_pretrained(
            self.model_path,
            torch_dtype=torch.float16,
            device_map="cuda")
        # if self.tokenizer.pad_token is None:
        #     self.tokenizer.pad_token = self.tokenizer.eos_token
        self.tokenizer.add_special_tokens({'pad_token': '[PAD]'})
        self.tokenizer.padding_side = "left"
        self.model.resize_token_embeddings(len(self.tokenizer))
        self.tokenizer.pad_token_id = self.tokenizer.convert_tokens_to_ids(self.tokenizer.pad_token)
        self.model.config.pad_token_id = self.tokenizer.pad_token_id

    def infill(self, prompt, max_new_tokens, use_beam=False):
        input_ids = self.tokenizer(
            prompt,
            return_tensors="pt",
            padding=True)["input_ids"].to("cuda")
        # generated_ids = self.model.generate(
        #     input_ids,
        #     max_new_tokens=max_new_tokens,
        #     pad_token_id=self.tokenizer.pad_token_id,
        #     use_cache = True)
        if use_beam:
            outputs = self.model.generate(
                input_ids,
                max_new_tokens=max_new_tokens,
                pad_token_id=self.tokenizer.pad_token_id,
                use_cache = True,
                return_dict_in_generate=True, 
                output_scores=True,
                num_beams=3,
                num_return_sequences=3,
                )
        else:
            outputs = self.model.generate(
                input_ids,
                max_new_tokens=max_new_tokens,
                pad_token_id=self.tokenizer.pad_token_id,
                use_cache = True,
                return_dict_in_generate=True, 
                output_scores=True,
                )

        # Log Probabilities
        if use_beam:
            transition_scores = self.model.compute_transition_scores(
                outputs.sequences, 
                outputs.scores, 
                outputs.beam_indices, 
                normalize_logits=False)
            transition_scores = torch.reshape(transition_scores, [input_ids.shape[0], -1, transition_scores.shape[-1]])
        else:
            transition_scores = self.model.compute_transition_scores(
                outputs.sequences, 
                outputs.scores, 
                normalize_logits=True)
        # Generated Tokens
        generated_ids = torch.reshape(outputs.sequences, [input_ids.shape[0], -1, outputs.sequences.shape[-1]])
        if use_beam:
            filling = self.tokenizer.batch_decode(
                generated_ids[torch.arange(generated_ids.shape[0]),torch.argmax(transition_scores.sum(dim=-1), dim=-1), input_ids.shape[1]:],
                skip_special_tokens = True)
        else:
            filling = self.tokenizer.batch_decode(
                generated_ids[:, 0, input_ids.shape[1]:],
                skip_special_tokens = True)
        # First Token Top-10 Variance
        first_token_var = torch.var(torch.topk(outputs.scores[0], 10, dim=1).values, dim=-1)
        first_token_var = torch.reshape(first_token_var, [input_ids.shape[0], -1])
        
        return filling, generated_ids[:, :, input_ids.shape[1]:], transition_scores, first_token_var[:, 0]
    
    def process_label(self, masked_line: str) -> list:
        return self.tokenizer.unk_token + masked_line# + self.tokenizer.additional_special_tokens[-1] + self.tokenizer.eos_token
    
    def teaching_forcing(self, input_batch: list, label_batch: list, max_new_tokens: int, filling: str, ignore_space: bool) -> torch.Tensor:
        '''Perform teaching forcing to calculate loss'''
        self.model.eval()
        with torch.no_grad():
            input_ids = list()
            label_ids = list()

            for j in range(len(input_batch)):
                input_id = self.tokenizer(input_batch[j], return_tensors="pt", padding=False)["input_ids"].to(self.model.device)
                fill_id = self.tokenizer(label_batch[j], return_tensors="pt", padding=False)["input_ids"].to(self.model.device)
                label_id = torch.full(input_id.shape, -100).to(self.model.device)
                label_id = torch.cat((label_id, fill_id[:, 2:]), 1)
                input_id = torch.cat((input_id, fill_id[:, 2:]), 1)
                input_ids.append(input_id)
                label_ids.append(label_id)
            # torch.cuda.empty_cache()

            # input_ids = torch.nn.utils.rnn.pad_sequence([
            #     input_id.flip(dims=[1])[0] for input_id in input_ids
            # ],
            # batch_first=True, padding_value=self.tokenizer.pad_token_id).flip(dims=[1])
            input_ids = torch.nn.utils.rnn.pad_sequence([
                input_id[0] for input_id in input_ids
            ],
            batch_first=True, padding_value=self.tokenizer.pad_token_id)

            # label_ids = torch.nn.utils.rnn.pad_sequence([
            #     label_id.flip(dims=[1])[0] for label_id in label_ids
            # ],
            # batch_first=True, padding_value=-100).flip(dims=[1])
            label_ids = torch.nn.utils.rnn.pad_sequence([
                label_id[0] for label_id in label_ids
            ],
            batch_first=True, padding_value=-100)

            if ignore_space:
                for i in range(label_ids.shape[0]):
                    for j in range(label_ids.shape[1]-1, -1, -1):
                        if label_ids[i, j] == -100:
                            break
                        if self.tokenizer.decode(label_ids[i, j]).isspace():
                            label_ids[i, j] = -100

            all_logits = self.model.forward(input_ids=input_ids, labels=label_ids, return_dict=True).logits

            return all_logits, label_ids

    def calculate_loss(self, input_batch: list, all_logits: torch.Tensor, label_ids: torch.Tensor) -> list:
        # Calculate loss
        all_losses = list()
        for j in range(len(input_batch)):
            logits = all_logits[j]
            labels = label_ids[j]
            # Shift so that tokens < n predict n
            shift_logits = logits[:-1, :].contiguous()
            shift_labels = labels[1:].contiguous()
            # Flatten the tokens
            loss_fct = torch.nn.CrossEntropyLoss()
            shift_logits = shift_logits.view(-1, self.tokenizer.vocab_size + 1)
            shift_labels = shift_labels.view(-1)
            # Enable model parallelism
            shift_labels = shift_labels.to(shift_logits.device)
            loss = loss_fct(shift_logits, shift_labels)
            all_losses.append(loss.item())
            del shift_logits, shift_labels, loss
            # torch.cuda.empty_cache()
        return all_losses
    
class CodeLlama7B(CodeLlama13B):
    def __init__(self):
        self.model_path = "codellama/CodeLlama-7b-hf"
        self.tokenizer = CodeLlamaTokenizer.from_pretrained(self.model_path, device_map="cuda")
        self.model = LlamaForCausalLM.from_pretrained(
            self.model_path,
            torch_dtype=torch.float16,
            device_map="cuda")
        # if self.tokenizer.pad_token is None:
        #     self.tokenizer.pad_token = self.tokenizer.eos_token
        self.tokenizer.add_special_tokens({'pad_token': '[PAD]'})
        self.tokenizer.padding_side = "left"
        self.model.resize_token_embeddings(len(self.tokenizer))
        self.tokenizer.pad_token_id = self.tokenizer.convert_tokens_to_ids(self.tokenizer.pad_token)
        self.model.config.pad_token_id = self.tokenizer.pad_token_id

class Qwen25Coder:
    def __init__(self, size):
        self.model_path = f"Qwen/Qwen2.5-Coder-{size}B"
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_path, 
                                                       device_map="auto", 
                                                       padding_side='left')
        self.model = AutoModelForCausalLM.from_pretrained(
            self.model_path,
            device_map="auto",
            torch_dtype="auto",
            pad_token_id=self.tokenizer.eos_token_id)
        
        add_special_tokens = [
            "<|file_sep|>", "<|fim_prefix|>", "<|fim_middle|>", "<|fim_suffix|>", "<|fim_pad|>",
            "<|repo_name|>", "<|endoftext|>"
        ]
        self.eos_token_ids = [151664, 151662, 151659, 151661, 151660, 151663, 151643, 151645]
        self.tokenizer.add_special_tokens({
            "additional_special_tokens": add_special_tokens
        }, replace_additional_special_tokens=False)

        self.tokenizer.add_special_tokens({'pad_token': '[PAD]'})
        self.model.resize_token_embeddings(len(self.tokenizer))
        self.tokenizer.pad_token_id = self.tokenizer.convert_tokens_to_ids(self.tokenizer.pad_token)
        self.model.config.pad_token_id = self.tokenizer.pad_token_id

        # self.tokenizer.padding_side = "left"
        # self.tokenizer.pad_token_id = 151662
        # self.model.config.pad_token_id = self.tokenizer.pad_token_id
        # self.tokenizer.additional_special_tokens += ["<|fim_prefix|>", "<|fim_middle|>", "<|fim_suffix|>", "<|fim_pad|>"]
    def infill(self, prompt, max_new_tokens, use_beam=False):
        processed_prompt = ['<|fim_prefix|>' + prompt.split("<FILL_ME>")[0] +
                           '<|fim_suffix|>' + prompt.split("<FILL_ME>")[1] +
                           '<|fim_middle|>'
                           for i, prompt in enumerate(prompt)]
        
        input_ids = self.tokenizer(
            processed_prompt,
            return_tensors="pt",
            padding=True)["input_ids"].to("cuda")
        outputs = self.model.generate(
            input_ids,
            max_new_tokens=max_new_tokens,
            pad_token_id=self.tokenizer.pad_token_id,
            do_sample=False,
            top_p=1.0,
            return_dict_in_generate=True, 
            output_scores=True,
            eos_token_id=self.eos_token_ids)
        
        # Log Probabilities
        transition_scores = self.model.compute_transition_scores(
            outputs.sequences, 
            outputs.scores, 
            normalize_logits=True)
        # Generated Tokens
        generated_ids = torch.reshape(outputs.sequences, [input_ids.shape[0], -1, outputs.sequences.shape[-1]])
        filling = [i.split("<|file_sep|>")[0] for i in self.tokenizer.batch_decode(
                generated_ids[:, 0, input_ids.shape[1]:],
                skip_special_tokens = True)]
        # First Token Top-10 Variance
        first_token_var = torch.var(torch.topk(outputs.scores[0], 10, dim=1).values, dim=-1)
        first_token_var = torch.reshape(first_token_var, [input_ids.shape[0], -1])
        return filling, generated_ids[:, :, input_ids.shape[1]:], transition_scores, first_token_var[:, 0]
    
    def process_label(self, masked_line: str) -> list:
        return masked_line
    
    def teaching_forcing(self, input_batch: list, label_batch: list, max_new_tokens: int, fillings: list, ignore_space: bool) -> torch.Tensor:
        '''Perform teaching forcing to calculate loss'''
        self.model.eval()
        with torch.no_grad():     
            processed_input_batch = []
            for i, prompt in enumerate(input_batch):
                processed_input_batch.append(
                        '<|fim_prefix|>' + prompt.split("<FILL_ME>")[0] +
                        '<|fim_suffix|>' + prompt.split("<FILL_ME>")[1] +
                        '<|fim_middle|>' + label_batch[i]
                        )

            input_ids = self.tokenizer(processed_input_batch,
                                        return_tensors="pt",
                                        padding=True)["input_ids"].to("cuda")
            label_ids = input_ids.clone()
            for i in range(label_ids.shape[0]):
                label_ids[i][:(label_ids[i] == 151660).nonzero()[0][0]+1] = -100

            attention_mask = (input_ids != self.tokenizer.pad_token_id)

            if ignore_space:
                for i in range(label_ids.shape[0]):
                    for j in range(label_ids.shape[1]):
                        if label_ids[i, j] != -100 and self.tokenizer.decode(label_ids[i, j]).isspace():
                            label_ids[i, j] = -100

            all_logits = self.model.forward(input_ids=input_ids, labels=label_ids, attention_mask=attention_mask, return_dict=True).logits

            return all_logits, label_ids
        
    def calculate_loss(self, input_batch: list, all_logits: torch.Tensor, label_ids: torch.Tensor) -> list:
        # Calculate loss
        all_losses = list()
        for j in range(len(input_batch)):
            logits = all_logits[j]
            labels = label_ids[j]
            # Shift so that tokens < n predict n
            shift_logits = logits[:-1, :].contiguous()
            shift_labels = labels[1:].contiguous()
            # Flatten the tokens
            loss_fct = torch.nn.CrossEntropyLoss()
            shift_logits = shift_logits.view(-1, shift_logits.shape[1])
            shift_labels = shift_labels.view(-1)
            # Enable model parallelism
            shift_labels = shift_labels.to(shift_logits.device)
            loss = loss_fct(shift_logits, shift_labels)
            all_losses.append(loss.item())
            del shift_logits, shift_labels, loss
            # torch.cuda.empty_cache()
        return all_losses
    
class Qwen25InstructQ4(Qwen25Coder):
    def __init__(self, size):
        self.model_path = f"Qwen/Qwen2.5-{size}B-Instruct-GPTQ-Int4"
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_path, 
                                                        device_map="auto", 
                                                        padding_side='left')
        self.model = AutoModelForCausalLM.from_pretrained(
            self.model_path,
            device_map="auto",
            torch_dtype=torch.float16)
        
        add_special_tokens = [
            "<|file_sep|>", "<|fim_prefix|>", "<|fim_middle|>", "<|fim_suffix|>", "<|fim_pad|>",
            "<|repo_name|>", "<|endoftext|>"
        ]
        self.eos_token_ids = [151664, 151662, 151659, 151661, 151660, 151663, 151643, 151645]
        self.tokenizer.add_special_tokens({
            "additional_special_tokens": add_special_tokens
        }, replace_additional_special_tokens=False)

        self.tokenizer.add_special_tokens({'pad_token': '[PAD]'})
        self.model.resize_token_embeddings(len(self.tokenizer))
        self.tokenizer.pad_token_id = self.tokenizer.convert_tokens_to_ids(self.tokenizer.pad_token)
        self.model.config.pad_token_id = self.tokenizer.pad_token_id

        self.model.generation_config.temperature=None
        self.model.generation_config.top_p=None
        self.model.generation_config.top_k=None

    def infill(self, prompt, max_new_tokens, use_beam=False):
        processed_prompt = ["<|im_start|>system\n请帮我补全以下代码。只用输出补全行，请勿输出其他内容。<|im_end|>\n<|im_start|>user\n" + 
                           '<|fim_prefix|>' + prompt.split("<FILL_ME>")[0] +
                           '<|fim_suffix|>' + prompt.split("<FILL_ME>")[1] +
                           '<|fim_middle|>' +
                           "<|im_end|>\n<|im_start|>assistant\n"
                           for i, prompt in enumerate(prompt)]
        
        input_ids = self.tokenizer(
            processed_prompt,
            return_tensors="pt",
            padding=True)["input_ids"].to("cuda")
        outputs = self.model.generate(
            input_ids,
            max_new_tokens=max_new_tokens,
            pad_token_id=self.tokenizer.pad_token_id,
            do_sample=False,
            return_dict_in_generate=True, 
            output_scores=True,
            eos_token_id=self.eos_token_ids)
        
        # Log Probabilities
        transition_scores = self.model.compute_transition_scores(
            outputs.sequences, 
            outputs.scores, 
            normalize_logits=True)
        # Generated Tokens
        generated_ids = torch.reshape(outputs.sequences, [input_ids.shape[0], -1, outputs.sequences.shape[-1]])
        filling = [i.split("<|file_sep|>")[0] for i in self.tokenizer.batch_decode(
                generated_ids[:, 0, input_ids.shape[1]:],
                skip_special_tokens = True)]
        # First Token Top-10 Variance
        first_token_var = torch.var(torch.topk(outputs.scores[0], 10, dim=1).values, dim=-1)
        first_token_var = torch.reshape(first_token_var, [input_ids.shape[0], -1])
        return filling, generated_ids[:, :, input_ids.shape[1]:], transition_scores, first_token_var[:, 0]
    
    def teaching_forcing(self, input_batch: list, label_batch: list, max_new_tokens: int, fillings: list, ignore_space: bool) -> torch.Tensor:
        '''Perform teaching forcing to calculate loss'''
        self.model.eval()
        with torch.no_grad():     
            processed_input_batch = []
            for i, prompt in enumerate(input_batch):
                processed_input_batch.append(
                        "<|im_start|>system\n请帮我补全以下代码。只用输出补全行，请勿输出其他内容。<|im_end|>\n<|im_start|>user\n" + 
                        '<|fim_prefix|>' + prompt.split("<FILL_ME>")[0] +
                        '<|fim_suffix|>' + prompt.split("<FILL_ME>")[1] +
                        '<|fim_middle|>' + "<|im_end|>\n<|im_start|>assistant\n" + label_batch[i]
                        )

            input_ids = self.tokenizer(processed_input_batch,
                                        return_tensors="pt",
                                        padding=True)["input_ids"].to("cuda")
            label_ids = input_ids.clone()
            for i in range(label_ids.shape[0]):
                label_ids[i][:(label_ids[i] == 151644).nonzero()[-1][0]+3] = -100

            attention_mask = (input_ids != self.tokenizer.pad_token_id)

            if ignore_space:
                for i in range(label_ids.shape[0]):
                    for j in range(label_ids.shape[1]):
                        if label_ids[i, j] != -100 and self.tokenizer.decode(label_ids[i, j]).isspace():
                            label_ids[i, j] = -100

            all_logits = self.model.forward(input_ids=input_ids, labels=label_ids, attention_mask=attention_mask, return_dict=True).logits

            return all_logits, label_ids

class StarCoder2:
    def __init__(self):
        self.model_path = "bigcode/starcoder2-15b"
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_path, device_map="auto")
        self.model = AutoModelForCausalLM.from_pretrained(
            self.model_path,
            torch_dtype=torch.bfloat16,
            device_map="auto")
        self.model.generation_config.pad_token_id = self.model.generation_config.eos_token_id
        self.model.config.pad_token_id = self.tokenizer.eos_token_id
        
    def infill(self, prompt, max_new_tokens):
        prefix_code = prompt.split("<FILL_ME>")[0]
        suffix_code = prompt.split("<FILL_ME>")[1]
        prompt = '<fim_prefix>' + prefix_code + '<fim_suffix>' + suffix_code + '<fim_middle>'

        input_ids = self.tokenizer(
            prompt,
            return_tensors="pt")["input_ids"].to("cuda")
        generated_ids = self.model.generate(
            input_ids,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            top_p=1.0,)
        filling = self.tokenizer.batch_decode(
            generated_ids[:, input_ids.shape[1]:],
            skip_special_tokens = True)[0]
        return filling
    
    def process_label(self, masked_line: str) -> list:
        return masked_line
    
    def teaching_forcing(self, input_batch: list, label_batch: list, max_new_tokens: int, filling: str, ignore_space: bool) -> torch.Tensor:
        '''Perform teaching forcing to calculate loss'''
        self.model.eval()
        with torch.no_grad():
            input_batch = ['<fim_prefix>' + prompt.split("<FILL_ME>")[0] + 
                           '<fim_suffix>' + prompt.split("<FILL_ME>")[1] + 
                           '<fim_middle>'
                           for i, prompt in enumerate(input_batch)]
            input_ids = self.tokenizer(
            input_batch,
            return_tensors="pt")["input_ids"].to("cuda")
            fill_ids = self.tokenizer(
            label_batch,
            return_tensors="pt")["input_ids"].to("cuda")

            label_ids = torch.full(input_ids.shape, -100).to("cuda")
            label_ids = torch.cat((label_ids, fill_ids), 1)
            input_ids = torch.cat((input_ids, fill_ids), 1)

            if ignore_space:
                for i in range(label_ids.shape[0]):
                    for j in range(label_ids.shape[1]-1, -1, -1):
                        if label_ids[i, j] == -100:
                            break
                        if self.tokenizer.decode(label_ids[i, j]).isspace():
                            label_ids[i, j] = -100

            loss = self.model.forward(input_ids=input_ids, labels=label_ids, return_dict=True).loss

            return loss, label_ids
        
    def calculate_loss(self, input_batch: list, all_logits: torch.Tensor, label_ids: torch.Tensor) -> list:
        return [all_logits.item()] # FIXME: Implement this

class StarCoderBase(StarCoder2):
    def __init__(self):
        self.model_path = "bigcode/starcoderbase"
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_path, device_map="auto", token='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')
        self.model = AutoModelForCausalLM.from_pretrained(
            self.model_path,
            torch_dtype=torch.bfloat16,
            device_map="auto", token='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')
        self.model.generation_config.pad_token_id = self.model.generation_config.eos_token_id
        self.model.config.pad_token_id = self.tokenizer.eos_token_id

    def infill(self, prompt, max_new_tokens):
        prefix_code = prompt.split("<FILL_ME>")[0]
        suffix_code = prompt.split("<FILL_ME>")[1]
        prompt = '<fim_prefix>' + prefix_code + '<fim_suffix>' + suffix_code + '<fim_middle>'

        input_ids = self.tokenizer(
            prompt,
            return_tensors="pt")["input_ids"].to("cuda")

        while input_ids.shape[1] + max_new_tokens > 8192: # This model only support up to 8192 tokens
            prefix_code = prefix_code[10:]
            suffix_code = suffix_code[:-10]
            prompt = '<fim_prefix>' + prefix_code + '<fim_suffix>' + suffix_code + '<fim_middle>'

            input_ids = self.tokenizer(
                prompt,
                return_tensors="pt")["input_ids"].to("cuda")


        generated_ids = self.model.generate(
            input_ids,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            top_p=1.0,)
        filling = self.tokenizer.batch_decode(
            generated_ids[:, input_ids.shape[1]:],
            skip_special_tokens = True)[0]
        return filling

    def teaching_forcing(self, input_batch: list, label_batch: list, max_new_tokens: int, filling: str, ignore_space: bool) -> torch.Tensor:
        '''Perform teaching forcing to calculate loss'''
        self.model.eval()
        with torch.no_grad():
            for i, prompt in enumerate(input_batch):
                prefix_code = prompt.split("<FILL_ME>")[0]
                suffix_code = prompt.split("<FILL_ME>")[1]
                prompt = '<fim_prefix>' + prefix_code + '<fim_suffix>' + suffix_code + '<fim_middle>'

                while self.tokenizer(prompt, return_tensors="pt")["input_ids"].shape[1] + \
                      max_new_tokens > 8192: # This model only support up to 8192 tokens
                    prefix_code = prefix_code[10:]
                    suffix_code = suffix_code[:-10]
                    prompt = '<fim_prefix>' + prefix_code + '<fim_suffix>' + suffix_code + '<fim_middle>'

                input_batch[i] = prompt

            input_ids = self.tokenizer(
            input_batch,
            return_tensors="pt")["input_ids"].to("cuda")
            fill_ids = self.tokenizer(
            label_batch,
            return_tensors="pt")["input_ids"].to("cuda")

            label_ids = torch.full(input_ids.shape, -100).to("cuda")
            label_ids = torch.cat((label_ids, fill_ids), 1)
            input_ids = torch.cat((input_ids, fill_ids), 1)

            if ignore_space:
                for i in range(label_ids.shape[0]):
                    for j in range(label_ids.shape[1]-1, -1, -1):
                        if label_ids[i, j] == -100:
                            break
                        if self.tokenizer.decode(label_ids[i, j]).isspace():
                            label_ids[i, j] = -100

            loss = self.model.forward(input_ids=input_ids, labels=label_ids, return_dict=True).loss

            return loss, label_ids

class CodeGen2:
    def __init__(self, size):
        self.model_path = "Salesforce/codegen2-{}B".format(size)
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_path, device_map="auto")
        self.model = AutoModelForCausalLM.from_pretrained(
            self.model_path,
            trust_remote_code=True, revision="main",
            torch_dtype=torch.bfloat16,
            device_map="auto")
        self.model.generation_config.pad_token_id = self.model.generation_config.eos_token_id
        self.model.config.pad_token_id = self.tokenizer.eos_token_id

    def infill(self, prompt, max_new_tokens):
        prefix_code = prompt.split("<FILL_ME>")[0]
        suffix_code = prompt.split("<FILL_ME>")[1]
        prompt = prefix_code + "<mask_1>" + suffix_code + "<|endoftext|>" + "<sep>" + "<mask_1>"

        input_ids = self.tokenizer(
            prompt,
            return_tensors="pt")["input_ids"].to("cuda")

        while input_ids.shape[1] + max_new_tokens > 2048: # This model only support up to 2048 tokens
            prefix_code = prefix_code[10:]
            suffix_code = suffix_code[:-10]
            prompt = prefix_code + "<mask_1>" + suffix_code + "<|endoftext|>" + "<sep>" + "<mask_1>"

            input_ids = self.tokenizer(
                prompt,
                return_tensors="pt")["input_ids"].to("cuda")


        generated_ids = self.model.generate(
            input_ids,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            top_p=1.0,)
        filling = self.tokenizer.batch_decode(
            generated_ids[:, input_ids.shape[1]:],
            skip_special_tokens = True)[0]
        return filling.split("<eom>")[0]

    def process_label(self, masked_line: str) -> list:
        return masked_line

    def teaching_forcing(self, input_batch: list, label_batch: list, max_new_tokens: int, filling: str, ignore_space: bool) -> torch.Tensor:
        '''Perform teaching forcing to calculate loss'''
        self.model.eval()
        with torch.no_grad():
            for i, prompt in enumerate(input_batch):
                prefix_code = prompt.split("<FILL_ME>")[0]
                suffix_code = prompt.split("<FILL_ME>")[1]
                prompt = prefix_code + "<mask_1>" + suffix_code + "<|endoftext|>" + "<sep>" + "<mask_1>"

                while self.tokenizer(prompt, return_tensors="pt")["input_ids"].shape[1] + \
                      max_new_tokens > 2048: # This model only support up to 2048 tokens
                    prefix_code = prefix_code[10:]
                    suffix_code = suffix_code[:-10]
                    prompt = prefix_code + "<mask_1>" + suffix_code + "<|endoftext|>" + "<sep>" + "<mask_1>"

                input_batch[i] = prompt

            input_ids = self.tokenizer(
            input_batch,
            return_tensors="pt")["input_ids"].to("cuda")
            fill_ids = self.tokenizer(
            label_batch,
            return_tensors="pt")["input_ids"].to("cuda")

            label_ids = torch.full(input_ids.shape, -100).to("cuda")
            label_ids = torch.cat((label_ids, fill_ids), 1)
            input_ids = torch.cat((input_ids, fill_ids), 1)

            if ignore_space:
                for i in range(label_ids.shape[0]):
                    for j in range(label_ids.shape[1]-1, -1, -1):
                        if label_ids[i, j] == -100:
                            break
                        if self.tokenizer.decode(label_ids[i, j]).isspace():
                            label_ids[i, j] = -100

            loss = self.model.forward(input_ids=input_ids, labels=label_ids, return_dict=True).loss

            return loss, label_ids

    def calculate_loss(self, input_batch: list, all_logits: torch.Tensor, label_ids: torch.Tensor) -> list:
        return [all_logits.item()] # FIXME: Implement this

class DeepseekCoder:
    def __init__(self, size):
        self.model_path = "deepseek-ai/deepseek-coder-" + size + "b-base"

        self.tokenizer = AutoTokenizer.from_pretrained(self.model_path, trust_remote_code=True, device_map="cuda")
        self.model = AutoModelForCausalLM.from_pretrained(self.model_path, trust_remote_code=True, device_map="cuda",
                                                          torch_dtype="auto")
        self.model.generation_config.pad_token_id = self.model.generation_config.eos_token_id
        self.model.config.pad_token_id = self.tokenizer.eos_token_id

    def infill(self, prompt, max_new_tokens, use_beam=False):
        processed_prompt = ['<｜fim▁begin｜>' + prompt.split("<FILL_ME>")[0] +
                            '<｜fim▁hole｜>' + prompt.split("<FILL_ME>")[1] +
                           '<｜fim▁end｜>'
                           for i, prompt in enumerate(prompt)]

        # assert len(prompt) == 1
        # prompt = prompt[0]
        # prefix_code = prompt.split("<FILL_ME>")[0]
        # suffix_code = prompt.split("<FILL_ME>")[1]
        # prompt = '<｜fim▁begin｜>' + prefix_code + '<｜fim▁hole｜>' + suffix_code + '<｜fim▁end｜>'

        input_ids = self.tokenizer(
            processed_prompt,
            return_tensors="pt")["input_ids"].to("cuda")
        outputs = self.model.generate(
            input_ids,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            top_p=1.0,
            return_dict_in_generate=True, 
            output_scores=True)
        
        # Log Probabilities
        transition_scores = self.model.compute_transition_scores(
            outputs.sequences, 
            outputs.scores, 
            normalize_logits=True)
        # Generated Tokens
        generated_ids = torch.reshape(outputs.sequences, [input_ids.shape[0], -1, outputs.sequences.shape[-1]])
        filling = self.tokenizer.batch_decode(
                generated_ids[:, 0, input_ids.shape[1]:],
                skip_special_tokens = True)
        # First Token Top-10 Variance
        first_token_var = torch.var(torch.topk(outputs.scores[0], 10, dim=1).values, dim=-1)
        first_token_var = torch.reshape(first_token_var, [input_ids.shape[0], -1])
        return filling, generated_ids[:, :, input_ids.shape[1]:], transition_scores, first_token_var[:, 0]
    
    def process_label(self, masked_line: str) -> list:
        return masked_line
    
    def teaching_forcing(self, input_batch: list, label_batch: list, max_new_tokens: int, filling: str, ignore_space: bool) -> torch.Tensor:
        '''Perform teaching forcing to calculate loss'''
        self.model.eval()
        with torch.no_grad():
            prefix_batch = ['<｜fim▁begin｜>' + prompt.split("<FILL_ME>")[0] +
                            '<｜fim▁hole｜>' + prompt.split("<FILL_ME>")[1] +
                           '<｜fim▁end｜>'
                           for i, prompt in enumerate(input_batch)]
            input_batch = ['<｜fim▁begin｜>' + prompt.split("<FILL_ME>")[0] +
                        '<｜fim▁hole｜>' + prompt.split("<FILL_ME>")[1] +
                        '<｜fim▁end｜>' + label_batch[i]
                        for i, prompt in enumerate(input_batch)]


            input_ids = self.tokenizer(
            input_batch,
            return_tensors="pt")["input_ids"].to("cuda")
            prefix_ids = self.tokenizer(
            prefix_batch,
            return_tensors="pt")["input_ids"].to("cuda")
            label_ids = input_ids.clone()
            label_ids[0, :prefix_ids.shape[1]] = -100

            if ignore_space:
                for i in range(prefix_ids.shape[1], label_ids.shape[1]):
                    if self.tokenizer.decode(label_ids[0, i]).isspace():
                        label_ids[0, i] = -100

            loss = self.model.forward(input_ids=input_ids, labels=label_ids, return_dict=True).loss

            return loss, label_ids
        
    def calculate_loss(self, input_batch: list, all_logits: torch.Tensor, label_ids: torch.Tensor) -> list:
        return [all_logits.item()] # FIXME: Implement this

class OpenAIGPT:
    def __init__(self, model):
        self.model = model
        self.client = OpenAI()
        self.system_prompt = ""
        with open("./openai_prompt.txt", "r") as f:
            self.system_prompt = f.read()

    def infill(self, prompt, max_new_tokens):
        response = self.client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {
                            "role": "system",
                            "content": [
                                {
                                "type": "text",
                                "text": self.system_prompt
                                }
                            ]
                            },
                            {
                            "role": "user",
                            "content": [
                                {
                                "type": "text",
                                "text": prompt
                                }
                            ]
                            }
                        ],
                        temperature=0,
                        max_tokens=max_new_tokens,
                        top_p=1,
                        frequency_penalty=0,
                        presence_penalty=0,
                        response_format={
                            "type": "text"
                        }
                    )
        return response.choices[0].message.content.replace('''```c''', '').replace('''```''', '')
    
    def process_label(self, masked_line: str) -> list:
        return masked_line
    
    def teaching_forcing(self, input_batch: list, label_batch: list, max_new_tokens: int, filling: str, ignore_space: bool) -> torch.Tensor:
        return None, None
    
    def calculate_loss(self, input_batch: list, all_logits: torch.Tensor, label_ids: torch.Tensor) -> list:
        return [-1]
    
def get_git_root_dir():
    repo_dir = subprocess.Popen(
      ['git', 'rev-parse', '--show-toplevel'],
      stdout=subprocess.PIPE
    ).communicate()[0].rstrip().decode('utf-8')
    return repo_dir

def load_magma_bugs_json(file_name="magma_buggy_and_nonbuggy_samples.json"):
    repo_dir = get_git_root_dir()
    magma_bugs_file = f"{repo_dir}/data/" + file_name
    
    if not os.path.isfile(magma_bugs_file):
        print("No magma bug json found! Please run init_repos.sh and process_patched_files.py first")
        exit(0)
    
    with open(magma_bugs_file) as f:
        return json.load(f)

def get_lines(file, line_no, num_prefix, num_suffix, mask_before=0, mask_after=0):
    assert(line_no > 0)
    target      = line_no - 1
    start       = max(target - num_prefix, 0)
    end         = target + num_suffix
    cntx        = ""
    masked_line = ""

    mask_start = max(target - mask_before, 0)
    mask_end = target + mask_after

    with open(file, errors='ignore') as fp:
        for i, line in enumerate(fp):
            if start <= i and i <= end and mask_start <= i and i <= mask_end:
                masked_line += line
                if cntx.endswith("<FILL_ME>\n"):
                    continue
                else:
                    cntx += "<FILL_ME>\n"
            elif start <= i and i <= end:
                cntx += line
            elif i > end:
                break
    if masked_line.endswith("\n"): # Compensate for the extra newline character
        masked_line = masked_line[:-1]
    return masked_line, cntx

def flatten(xs): 
    flat_list = []
    for x in xs: 
        if isinstance(x, list): 
            flat_list += flatten(x)
        else: 
            flat_list.append(x) 
    return flat_list

def get_gpu_memory(file):
    output_to_list = lambda x: x.decode('ascii').split('\n')[:-1]
    COMMAND = "nvidia-smi --query-gpu=memory.used --format=csv"
    try:
        memory_use_info = output_to_list(sp.check_output(COMMAND.split(),stderr=sp.STDOUT))[1:]
    except sp.CalledProcessError as e:
        raise RuntimeError("command '{}' return with error (code {}): {}".format(e.cmd, e.returncode, e.output))
    memory_use_values = [int(x.split()[0]) for i, x in enumerate(memory_use_info)]
    # print(memory_use_values)

    gpu_stats = open(file, 'a')
    gpu_stats_writer = csv.writer(gpu_stats)
    gpu_stats_writer.writerow(memory_use_values)