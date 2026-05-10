from torch.utils.tensorboard import SummaryWriter
import random
import os
import argparse
import glob
import json
import torch
import torch.utils.checkpoint
from torch import nn
from torch import optim
from torch.utils.data import DataLoader
from transformer import (
    PreloadedDataset,
    NaiveDataset,
    VoltronTransformerPretrained,
    VoltronTransformer,
    Utilities,
)


def train_one_epoch(
    model_utils,
    tb_writer,
    tb_checkpoint,
    train_dl,
    optimizer,
    model,
    max_lr,
    min_lr,
    warmup_iters,
    e_batch_iter,
    lr_decay_iters,
):
    """Training loop for an entire epoch

    Args:
        epoch_index (int): epoch index number
        tb_writer (torch.utils.tensorboard): tensorboard logger

        train_dl (torch.dataloader): train data
            Per batch variable dimensions:
                1. input: [batch_size=batch_size, seq_len=256, num_dimensions=1024)
                2. label: [batch_size=batch_size, seq_len=256]
                3. attention_mask: [batch_size=batch_size, seq_len=256]
                4. predictions: [batch_size=batch_size, seq_len=256]

        optimizer (torch.optim): optimizer
        model (transformer model): model
        loss_fn (torch.loss): loss function

    Returns:
        float: average training loss, accuracy, and precision per epoch
    """

    running_loss = 0.0
    last_loss = 0.0
    last_batch_iter = 0
    for batch_iter, (input, label, mask) in enumerate(train_dl):
        # Set up loss function
        loss_fn = nn.BCEWithLogitsLoss(reduction="none")
        # Determine the learning rate for this iteration
        current_batch_iter = e_batch_iter + batch_iter
        lr = model_utils.get_lr(
            current_batch_iter, lr_decay_iters, max_lr, min_lr, warmup_iters
        )
        for param_group in optimizer.param_groups:
            param_group["lr"] = lr
        # Forward pass
        predictions = model(input, mask)
        # Loss calculation
        loss = loss_fn(predictions, label)
        loss *= mask
        loss = torch.mean(torch.sum(loss, -1) / (1e-6 + torch.sum(mask, -1)))
        # Calculate gradients
        loss.backward()
        if batch_iter % 4 == 0:
            # Update weights
            optimizer.step()
            # Clear gradient
            optimizer.zero_grad(set_to_none=True)
        # Add to running results
        running_loss += loss.item()
        if batch_iter % tb_checkpoint == (tb_checkpoint - 1):
            last_loss = running_loss / tb_checkpoint
            tb_x = e_batch_iter + batch_iter + 1
            tb_writer.add_scalar("Train loss", last_loss, tb_x)
            tb_writer.add_scalar("Learning rate", optimizer.param_groups[0]["lr"], tb_x)
            running_loss = 0.0
        if batch_iter > 800:
            break
    last_batch_iter = batch_iter
    return last_loss, last_batch_iter


def validation_one_epoch(model_utils, validation_loader, model, pretraining):
    """Validation loop

    Args:
        validation_loader (torch.datapipe): validation data
        model (transformer model): model
        loss_fn (torch.loss): loss function

    Returns:
        float: average validation loss
    """
    loss_fn = nn.BCEWithLogitsLoss(reduction="none")
    running_vloss = 0.0
    running_vrec = 0.0
    running_vprec = 0.0
    running_vacc = 0.0

    all_probabilities = []
    all_labels = []

    with torch.no_grad():
        for batch_iter, (input, label, mask) in enumerate(validation_loader):
            predictions = model(input, mask)
            vloss = loss_fn(predictions, label)

            # Logging tensors
            flattened_input = torch.flatten(input)
            flattened_labels = torch.flatten(label)
            flattened_probabilities = torch.flatten(torch.sigmoid(predictions))

            real_indices = torch.flatten(mask == 1)
            flattened_probabilities = flattened_probabilities[real_indices]
            flattened_labels = flattened_labels[real_indices]

            nl_indices = torch.where(
                (flattened_input == 198) | (flattened_input == 628)
            )
            if len(nl_indices) > 1:
                nl_index = nl_indices[1]
            else:
                nl_index = nl_indices[0]
            if not pretraining:
                # Remove non nl tokens
                flattened_probabilities = flattened_probabilities[nl_index]
                flattened_labels = flattened_labels[nl_index]

            # Appending batch logging tensors to return list
            all_probabilities.append(flattened_probabilities)
            all_labels.append(flattened_labels)
            vloss *= mask
            vloss = torch.mean(torch.sum(vloss, -1) / (1e-6 + torch.sum(mask, -1)))
            running_vloss += vloss.item()

            vrecall, vprec, vaccuracy = model_utils.recall_prec_function(
                predictions, label, mask
            )
            running_vrec += vrecall
            running_vprec += vprec
            running_vacc += vaccuracy

            # break for testing
            if batch_iter > 200:
                break
    avg_vloss = running_vloss / (batch_iter + 1)
    avg_vrec = running_vrec / (batch_iter + 1)
    avg_vprec = running_vprec / (batch_iter + 1)
    avg_vacc = running_vacc / (batch_iter + 1)

    cat_probabilities = torch.cat(all_probabilities, dim=-1)
    cat_labels = torch.cat(all_labels, dim=-1)
    return avg_vloss, avg_vrec, avg_vprec, avg_vacc, cat_probabilities, cat_labels


def model_pipe(
    data_name,
    pretraining,
    pretrain_type,
    datapipe,
    dim_model=1024,
    num_head=16,
    num_layer=2,
    target_dim=256,
    batch_size=8,
    num_epochs=1,
    max_lr=1e-4,
    min_lr=1e-6,
    warmup_iters=500,
    tb_checkpoint=10,
    load_checkpoint=False,
    first_tb=True,
    lr_decay_iters=10000,
    tenfold_iteration=9,
):
    """Entire model pipeline

    Args:
        datapipe (torch.datapipe): Input data
        dim_model (int, optional): dimension of model. Defaults to 1024.
        batch_size (int, optional): batch size. Defaults to 8.
        num_epochs (int, optional): total number of epochs to run. Defaults to 1.
    """
    # Load data into batches

    # Shuffle indices before splitting into training and validation set.
    all_indices = list(range(len(datapipe)))
    # random.seed(42)  # Seed to ensure shuffling deterministically.
    # random.shuffle(all_indices)

    if pretraining:
        valid_indices = all_indices[0:len(datapipe)]
        print(
            f"Validation size={len(valid_indices)},\n\
        Total size={len(datapipe)}"
        )
    else:
        assert False, "This should not happen..."

    valid_dp = torch.utils.data.Subset(datapipe, valid_indices)
    validation_loader = DataLoader(
        dataset=valid_dp, batch_size=batch_size, shuffle=False
    )

    model = VoltronTransformerPretrained(
        num_layer=num_layer,
        dim_model=dim_model,
        num_head=num_head,
        target_dim=target_dim,
    )

    model = model.to("cuda:0")
    model_utils = Utilities()

    # Loading checkpoint and setting up tensorboard logging
    model_path = f"devign_{pretrain_type}"
    model_checkpoint_path = f"model_checkpoints/{model_path}"
    if load_checkpoint and os.path.exists(model_checkpoint_path):
        print(f"Loading checkpoint: {model_checkpoint_path}")
        model.load_state_dict(torch.load(model_checkpoint_path))
    else:
        assert False, "This should not happen..."

    log_folder = (
        f"model_logs/{data_name}/{model_path}_{target_dim}_{tenfold_iteration}"
    )

    # Optimizing
    optimizer = optim.Adam(model.parameters(), max_lr)

    best_vloss = 1_000_000.0
    best_vrec = 0
    best_vprec = 0
    best_vacc = 0
    best_prec_rec = 0
    best_epoch = 0
    e_batch_iter = 0
    current_path = os.getcwd()
    try:
        os.mkdir(f"{current_path}/model_checkpoints")
    except OSError:
        pass
    try:
        os.mkdir(f"{current_path}/model_logs/")
    except OSError:
        pass
    try:
        os.mkdir(f"{current_path}/model_logs/{data_name}")
    except OSError:
        pass
    try:
        os.mkdir(log_folder)
    except OSError:
        pass

    for _ in range(num_epochs):
        # Validation loop
        model.eval()
        (
            avg_vloss,
            avg_vrec,
            avg_vprec,
            avg_vacc,
            cat_probabilities,
            cat_labels,
        ) = validation_one_epoch(model_utils, validation_loader, model, pretraining)

        # Save the model's state
        log_dict = {
            "prob": cat_probabilities.tolist(),
            "label": cat_labels.tolist(),
        }
        log_files = glob.glob(f"{log_folder}/*")
        for f in log_files:
            os.remove(f)
        logging_file = f"{log_folder}/step_{str(e_batch_iter+1)}.json"
        with open(logging_file, "w+", encoding="utf-8") as file:
            to_write = json.dumps(log_dict, indent=3)
            file.write(to_write + "\n")

    model_str = (
        "Finished training {} epochs for {} dimensions & {} heads on {} {}".format(
            str(num_epochs), str(target_dim), str(num_head), data_name, pretrain_type
        )
    )
    epoch_str = "best epoch: " + str(best_epoch)
    vloss_str = "best vloss: " + str(round(best_vloss, 4))
    recall_str = "best rec: " + str(round(best_vrec, 7))
    precision_str = "best prec: " + str(round(best_vprec, 7))
    acc_str = "best acc: " + str(round(best_vacc, 7))

    logging = True
    if logging:
        f = open("log.txt", "a")
        f.write(
            model_str
            + "\n"
            + epoch_str
            + "\n"
            + vloss_str
            + "\n"
            + recall_str
            + "\n"
            + precision_str
            + "\n"
            + acc_str
            + "\n\n"
        )
        f.close()


def driver():
    # Uses a standard argument parsing library.
    ap = argparse.ArgumentParser()
    ap.add_argument("data_path", help="Path to data root")
    ap.add_argument("data_name", help="Dataset to train on")
    ap.add_argument("pretrain_type", help="codegen checkpoint type")
    args = ap.parse_args()

    # Initialize passed in variables
    data_path = args.data_path
    data_name = args.data_name
    pretrain_type = args.pretrain_type

    # Data loading
    current_path = os.getcwd()
    data_name_path = f"{current_path}/{data_path}/{data_name}"
    tensors_path = (
        f"{current_path}/{data_path}/codegen_states/{data_name}_{pretrain_type}/"
    )

    print(f"Using preloaded codegen hidden states for {data_name}_{pretrain_type}")
    datapipe = PreloadedDataset(tensors_path)

    # Hyperparameters pretraining
    tb_checkpoint = 10
    pretraining = True
    '''As per the paper, the hyperparameters are as follows:'''
    if pretrain_type == "6B":
        dim_model = 4096
        max_lr = 7e-6
        min_lr = 1e-7
        num_layer = 2
        batch_size = 32
        num_epochs = 1 # 1 For testing
    elif pretrain_type == "16B":
        dim_model = 6144
        max_lr = 4e-6
        min_lr = 1e-7
        num_layer = 2
        batch_size = 32
        num_epochs = 1 # 1 For testing

    warmup_iters = 1000
    lr_decay_iters = 20000
    target_dim = 512
    num_head = 8
    '''=================================================================='''
    load_checkpoint = True
    first_tb = False

    model_pipe(
            data_name=data_name,
            pretraining=pretraining,
            pretrain_type=pretrain_type,
            datapipe=datapipe,
            dim_model=dim_model,
            num_head=num_head,
            num_layer=num_layer,
            target_dim=target_dim,
            batch_size=batch_size,
            num_epochs=num_epochs,
            max_lr=max_lr,
            min_lr=min_lr,
            warmup_iters=warmup_iters,
            tb_checkpoint=tb_checkpoint,
            load_checkpoint=load_checkpoint,
            first_tb=first_tb,
            lr_decay_iters=lr_decay_iters,
        )


if __name__ == "__main__":
    driver()
