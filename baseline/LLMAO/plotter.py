import itertools
from sklearn.metrics import roc_curve
from sklearn.metrics import roc_auc_score, average_precision_score
from matplotlib import pyplot as plt
import os
import json
import argparse
import torch
import sklearn
import numpy as np


def roc_plotter(label_name, labels, probabilities):
    ignore_comments = False
    labels = np.array(labels)
    probabilities = np.array(probabilities)
    if ignore_comments:
        probabilities = np.delete(probabilities, np.where(labels == 2)).tolist()
        labels = np.delete(labels, np.where(labels == 2)).tolist()
    else:
        labels[np.where(labels == 2)] = 0
        probabilities = probabilities.tolist()
        labels = labels.tolist()

    func_lengths = itertools.groupby(labels, lambda x: x == -1)
    func_lengths = [list(y) for _, y in func_lengths]
    func_lengths = [len(e) for e in func_lengths if -1 not in e]

    labels = torch.tensor(labels)
    probabilities = torch.tensor(probabilities)
    considered_indices = torch.where((labels != -1))
    labels = labels[considered_indices]
    probabilities = probabilities[considered_indices]
    labels = labels.tolist()
    probabilities = probabilities.tolist()

    fpr, tpr, thresholds  = roc_curve(labels, probabilities)
    print(f'{label_name} AUC: {round(roc_auc_score(labels, probabilities), 3)}')

    splitted_labels = np.array_split(labels, np.cumsum(func_lengths))[:-1]
    splitted_probabilities = np.array_split(probabilities, np.cumsum(func_lengths))[:-1]

    sz = 0
    cnt = 0
    for e in splitted_labels:
        if 1 in e:
            sz += e.shape[0]
            cnt += 1
    print(f"Average length of vulnerable functions: {sz/cnt}")


    total_roc = []
    new_probs = []
    new_labels = []
    for prob, label in zip(splitted_probabilities, splitted_labels):
        if max(label) == 0 or min(label) == 1:
            continue
        total_roc.append(roc_auc_score(label, prob))
        new_probs += prob.tolist()
        new_labels += label.tolist()
    print(f'{label_name} Filtered AUC on Vul Func: {round(roc_auc_score(new_labels, new_probs), 3)}')
    print(f'{label_name} Avg AUC per Vul Func: {round(np.mean(total_roc), 3)}')

    MFRs = []
    for prob, label in zip(splitted_probabilities, splitted_labels):
        ranked = [i for _, i in sorted(zip(prob, label), reverse=True)]
        for idx, i in enumerate(ranked):
            if i == 1:
                MFRs.append(idx)
                break
    print(f'{label_name} MFR: {round(np.mean(MFRs), 3)}')
    print(f'{label_name} Median-FR: {round(np.median(MFRs), 3)}')
    
    top_1 = len([e for e in MFRs if e <= 0]) / len(MFRs)
    top_3 = len([e for e in MFRs if e <= 2]) / len(MFRs)
    top_5 = len([e for e in MFRs if e <= 4]) / len(MFRs)
    print(f'{label_name} Top-1: {round(top_1, 5)}')
    print(f'{label_name} Top-3: {round(top_3, 5)}')
    print(f'{label_name} Top-5: {round(top_5, 5)}')

    for num_bug in [1, 2, 3, 4, 5]:
        # total_roc = []
        total_logits = []
        total_labels = []
        for prob, label in zip(splitted_probabilities, splitted_labels):
            if sum(label) > num_bug or (min(label) == 1 or max(label) == 0):
                continue
            # total_roc.append(roc_auc_score(label, prob))
            total_logits += prob.tolist()
            total_labels += label.tolist()
        print(f'{label_name} AUC: {num_bug} bugs {round(roc_auc_score(total_labels, total_logits), 3)}')

    # roc_auc = sklearn.metrics.auc(fpr, tpr)
    # display = sklearn.metrics.RocCurveDisplay(fpr=fpr, tpr=tpr, roc_auc=roc_auc,
    #                               estimator_name='example estimator')
    # display.plot()

    true_oh = torch.nn.functional.one_hot(torch.tensor([int(e) for e in labels]), num_classes=2)
    score = torch.tensor(probabilities).unsqueeze(1)
    score = torch.cat((score, score), 1)
    pr_auc = average_precision_score(true_oh, score)
    print(f'{label_name} PR-AUC: {round(pr_auc, 3)}')

    for i, threshold in enumerate(thresholds):
        if round(threshold,3) == 0.01 and 'Devign-16B' in label_name:
            print('false positive ', round(fpr[i],2))
            print('true positive ', round(tpr[i],2))
            print('threshold ', threshold)
            break

    if '16B' in label_name:
        plt.plot(fpr, tpr, linestyle='--',
                 label=label_name, color='red')
    elif '6B' in label_name:
        plt.plot(fpr, tpr, linestyle='--',
                 label=label_name, color='orange')
    elif '350M' in label_name:
        plt.plot(fpr, tpr, linestyle='--',
                 label=label_name, color='blue')
    elif 'scratch' in label_name:
        label_here = label_name.replace('scratch', 'from-scratch')
        plt.plot(fpr, tpr, linestyle='--',
                 label=label_here, color='green')
    else:
        plt.plot(fpr, tpr, linestyle='-',
                 label=label_name)
    plt.xlabel('False Positive Rate')
    plt.ylabel('True Positive Rate')

    plt.show()

    plt.scatter(thresholds, tpr, label='TPR', s=0.1)
    plt.scatter(thresholds, fpr, label='FPR', s=0.1)
    plt.legend()
    plt.show()

def results_plot(log_path):
    data_list = ['bugsinpy', 'defects4j', 'devign']
    data_list = ['bigvul', 'devign']

    total_prob = []
    total_labels = []
    for data_name in data_list:
        plt.axline((0, 0), slope=1, color='black', label='Random', linestyle='--')
        for subdir, _, files in os.walk(log_path):
            for file in files:
                if '.json' in file:
                    if data_name not in subdir:
                        continue
                    if '_6B' not in subdir and '_16B' not in subdir:
                        continue
                    f = open(os.path.join(subdir, file))
                    split_dir = subdir.split('_')
                    data_name = split_dir[-4]
                    data_name = data_name.split('/')[-1]
                    params = split_dir[-3]
                    if params == '256' or params == '1024':
                        params = 'from_scratch'
                    data = json.load(f)
                    probabilities = data['prob']
                    labels = data["label"]
                    f.close()
                    filtered_prob = []
                    filtered_label = []
                    for i, prob in enumerate(probabilities):
                        if prob != 0:
                            filtered_prob.append(prob)
                            filtered_label.append(labels[i])
                    total_prob += filtered_prob
                    total_labels += filtered_label
                    label_name = f'{data_name}-{params}'.replace('--', '-').replace(
                        'bugsinpy', 'BugsInPy').replace('defects4j', 'Defects4J').replace('devign', 'Devign')
        #             roc_plotter(label_name, filtered_label, filtered_prob)

        # handles, labels = plt.gca().get_legend_handles_labels()
        # if 'Devign' in label_name:
        #     order = [0, 1, 2, 4, 3]
        # elif 'Defects4J' in label_name:
        #     order = [0, 1, 3, 2, 4]
        # elif 'BugsInPy' in label_name:
        #     order = [0, 3, 2, 1, 4]
        # plt.legend([handles[idx] for idx in order], [labels[idx]
        #         for idx in order], loc='lower right')
        # plt.savefig(os.path.join('plots/', f'{data_name}_roc.pdf'))
        # plt.clf()

    label_name = 'primevul_valid_test_vul'
    roc_plotter(label_name, total_labels, total_prob)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("log_path", help="Path to data root")
    args = ap.parse_args()
    log_path = args.log_path
    results_plot(log_path)
