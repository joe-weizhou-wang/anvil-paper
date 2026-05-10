from tree_sitter import Language, Parser, Tree, Node
from sklearn.preprocessing import MinMaxScaler
from typing import Generator
import tree_sitter_cpp
import pandas as pd
import numpy as np
import swifter
import argparse

args = argparse.ArgumentParser(description='Process raw results from CodeLlama.')
args.add_argument('--raw_results_vul', type=str)
args.add_argument('--raw_results_non_vul', type=str)
args.add_argument('--output_file', type=str, default='processed_results.csv',
                   help='Path to save the processed results CSV file.')
args = args.parse_args()

CPP_LANGUAGE = Language(tree_sitter_cpp.language())
parser = Parser()
parser.language = CPP_LANGUAGE

def traverse_tree(tree: Tree) -> Generator[Node, None, None]:
    cursor = tree.walk()

    visited_children = False
    while True:
        if not visited_children:
            if cursor.node.type != "ERROR":
                yield cursor.node
            if not cursor.goto_first_child():
                visited_children = True
        elif cursor.goto_next_sibling():
            visited_children = False
        elif not cursor.goto_parent():
            break


magma = pd.read_csv('../result/magma_all_mcs.csv')
magma['dataset'] = 'magma'
magma['scaled_first_token_var'] = -np.exp(np.abs(magma.first_token_var - np.percentile(magma.first_token_var, 50)) / 40)
magma["neg_exact_match"] = -magma["exact_match"]
scaler = MinMaxScaler().fit(magma[["loss", "neg_exact_match", "scaled_first_token_var", "mask_ast_complexity"]])

results_cve = pd.read_csv(args.raw_results_vul)
results_sample = pd.read_csv(args.raw_results_non_vul)

results_cve.drop_duplicates(["file", "masked_line_no"], inplace=True, keep='first')
results_sample.drop_duplicates(["file", "masked_line_no"], inplace=True, keep='first')

results_sample.loc[results_sample.masked_line != results_sample.masked_line, "prediction"] = "NULL"
results_sample.loc[results_sample.masked_line != results_sample.masked_line, "masked_line"] = "NULL"

results = pd.concat([results_cve, results_sample])

results_cve['exact_match'] = results_cve.masked_line == results_cve.prediction
results_sample['exact_match'] = results_sample.masked_line == results_sample.prediction

results_cve['vul_label'] = 1
results_sample['vul_label'] = 0
    
def calculate_ast_complexity(row):
    mask_tree = parser.parse(bytes(row.masked_line, "utf8"))
    if row.prediction != row.prediction or row.whole_prediction != row.whole_prediction:
        return len(list(traverse_tree(mask_tree))), -1, -1
    
    pred_tree = parser.parse(bytes(row.whole_prediction, "utf8"))
    first_line_pred_tree = parser.parse(bytes(row.prediction, "utf8"))
    return len(list(traverse_tree(mask_tree))), len(list(traverse_tree(pred_tree))), len(list(traverse_tree(first_line_pred_tree)))

results_cve[['mask_ast_complexity', 'pred_ast_complexity', 'first_line_pred_ast_complexity']] = results_cve.swifter.progress_bar(False).apply(calculate_ast_complexity, axis=1, result_type='expand')
results_sample[['mask_ast_complexity', 'pred_ast_complexity', 'first_line_pred_ast_complexity']] = results_sample.swifter.progress_bar(False).apply(calculate_ast_complexity, axis=1, result_type='expand')

results_cve['scaled_first_token_var'] = -np.exp(np.abs(results_cve.first_token_var - np.percentile(results.first_token_var, 50)) / 40)
results_sample['scaled_first_token_var'] = -np.exp(np.abs(results_sample.first_token_var - np.percentile(results.first_token_var, 50)) / 40)

results_cve["neg_exact_match"] = -results_cve["exact_match"]
results_sample["neg_exact_match"] = -results_sample["exact_match"]

results_sample = results_sample[results_sample.masked_line_no != results_sample.cntx_start]
results_cve = results_cve[results_cve.masked_line_no != results_cve.cntx_start]

results_sample = results_sample[~(( \
    results_sample.masked_line.str.startswith('//') | \
    results_sample.masked_line.str.startswith('/*') | \
    results_sample.masked_line.str.startswith('* ')))]
results_cve = results_cve[~(( \
    results_cve.masked_line.str.startswith('//') | \
    results_cve.masked_line.str.startswith('/*') | \
    results_cve.masked_line.str.startswith('* ')))]

results = pd.concat([results_cve, results_sample])
results.drop_duplicates(inplace=True)
results = results.sample(frac=1)

results["new_score"] = scaler.transform(results[["loss", "neg_exact_match", "scaled_first_token_var", "mask_ast_complexity"]]).sum(axis=1)

results.to_csv(args.output_file, index=False)