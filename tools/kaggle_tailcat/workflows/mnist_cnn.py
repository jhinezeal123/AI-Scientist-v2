"""MNIST CNN experiment executed inside the persistent Kaggle SSH terminal."""
import argparse
import csv
import hashlib
import json
import random
import time
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torchvision.datasets import MNIST


class CNN(nn.Module):
    def __init__(self):
        super().__init__()
        self.layers = nn.Sequential(
            nn.Conv2d(1, 32, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),
            nn.Conv2d(32, 64, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),
            nn.Flatten(), nn.Linear(64 * 7 * 7, 128), nn.ReLU(),
            nn.Dropout(0.25), nn.Linear(128, 10),
        )

    def forward(self, images):
        return self.layers(images)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--epochs', type=int, default=3)
    args = parser.parse_args()
    root = args.root.resolve()
    output = root / 'outputs'
    output.mkdir(parents=True, exist_ok=True)
    checkpoint_dir = root / 'checkpoints'
    checkpoint_dir.mkdir(exist_ok=True)
    seed = 42
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.set_num_threads(2)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    gpu_count = torch.cuda.device_count()
    gpu_names = [torch.cuda.get_device_name(i) for i in range(gpu_count)]
    if gpu_count != 2 or any('T4' not in name for name in gpu_names):
        raise RuntimeError(f'Expected two T4 GPUs, received {gpu_names}')
    print(json.dumps({'event': 'hardware', 'gpu_names': gpu_names,
                      'torch': torch.__version__, 'cuda': torch.version.cuda}), flush=True)
    started = time.monotonic()
    original_train = MNIST(root=str(root / 'data'), train=True, download=True)
    official_test = MNIST(root=str(root / 'data'), train=False, download=True)
    permutation = torch.randperm(len(original_train), generator=torch.Generator().manual_seed(seed))
    train_indices, val_indices = permutation[:50000], permutation[50000:]
    assert len(train_indices) == 50000 and len(val_indices) == 10000 and len(official_test) == 10000
    assert not set(train_indices.tolist()).intersection(val_indices.tolist())
    device = torch.device('cuda:0')

    def tensors(dataset, indices=None):
        images, labels = dataset.data, dataset.targets
        if indices is not None:
            images, labels = images[indices], labels[indices]
        images = images.to(device=device, dtype=torch.float32).unsqueeze(1) / 255.0
        return (images - 0.1307) / 0.3081, labels.to(device)

    train_x, train_y = tensors(original_train, train_indices)
    val_x, val_y = tensors(original_train, val_indices)
    model = nn.DataParallel(CNN().to(device), device_ids=[0, 1])
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    criterion = nn.CrossEntropyLoss()
    scaler = torch.amp.GradScaler('cuda')
    batch_size = 512
    history = []
    best_validation = -1.0
    best_epoch = None

    def evaluate(images, labels, predictions=False):
        model.eval()
        loss_sum, correct, probabilities = 0.0, 0, []
        with torch.inference_mode():
            for offset in range(0, len(labels), batch_size):
                x, y = images[offset:offset + batch_size], labels[offset:offset + batch_size]
                with torch.autocast(device_type='cuda', dtype=torch.float16):
                    logits = model(x)
                    loss = criterion(logits, y)
                loss_sum += loss.item() * len(y)
                correct += (logits.argmax(1) == y).sum().item()
                if predictions:
                    probabilities.append(logits.float().softmax(1).cpu())
        return loss_sum / len(labels), correct / len(labels), probabilities

    training_started = time.monotonic()
    for epoch in range(1, args.epochs + 1):
        if time.monotonic() - training_started > 600:
            raise TimeoutError('Training exceeded the 600-second experiment budget')
        epoch_started = time.monotonic()
        model.train()
        order = torch.randperm(len(train_y), device=device)
        loss_sum, correct = 0.0, 0
        for offset in range(0, len(order), batch_size):
            if time.monotonic() - training_started > 600:
                raise TimeoutError('Training exceeded the 600-second experiment budget')
            indices = order[offset:offset + batch_size]
            x, y = train_x[indices], train_y[indices]
            optimizer.zero_grad(set_to_none=True)
            with torch.autocast(device_type='cuda', dtype=torch.float16):
                logits = model(x)
                loss = criterion(logits, y)
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
            loss_sum += loss.item() * len(y)
            correct += (logits.argmax(1) == y).sum().item()
        val_loss, val_accuracy, _ = evaluate(val_x, val_y)
        row = {'epoch': epoch, 'train_loss': loss_sum / len(train_y),
               'train_accuracy': correct / len(train_y), 'val_loss': val_loss,
               'val_accuracy': val_accuracy, 'elapsed_seconds': time.monotonic() - epoch_started}
        history.append(row)
        print(json.dumps({'event': 'epoch', **row}), flush=True)
        if val_accuracy > best_validation:
            best_validation, best_epoch = val_accuracy, epoch
            torch.save(model.module.state_dict(), checkpoint_dir / 'best.pt')

    # Test data is evaluated only after checkpoint selection using validation.
    model.module.load_state_dict(torch.load(checkpoint_dir / 'best.pt', map_location=device, weights_only=True))
    test_x, test_y = tensors(official_test)
    test_loss, test_accuracy, probability_batches = evaluate(test_x, test_y, predictions=True)
    probabilities = torch.cat(probability_batches).numpy()
    labels = official_test.targets.numpy()
    predictions = probabilities.argmax(axis=1)
    csv_path = output / 'test_predictions.csv'
    with csv_path.open('w', encoding='utf-8', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['sample_id', 'true_label', 'predicted_label', 'correct', 'confidence',
                         *[f'probability_{i}' for i in range(10)]])
        for sample_id in range(len(labels)):
            writer.writerow([sample_id, int(labels[sample_id]), int(predictions[sample_id]),
                             int(labels[sample_id] == predictions[sample_id]),
                             float(probabilities[sample_id].max()),
                             *[float(value) for value in probabilities[sample_id]]])
    with (output / 'training_history.csv').open('w', encoding='utf-8', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=list(history[0]))
        writer.writeheader()
        writer.writerows(history)
    gpu_peak_memory = [torch.cuda.max_memory_allocated(i) for i in range(2)]
    if any(value == 0 for value in gpu_peak_memory):
        raise RuntimeError('Both GPUs must have been used during training')
    metrics = {'dataset': 'MNIST', 'seed': seed, 'train_samples': len(train_indices),
               'validation_samples': len(val_indices), 'test_samples': len(labels),
               'epochs': args.epochs, 'selected_epoch': best_epoch,
               'best_validation_accuracy': best_validation, 'test_accuracy': test_accuracy,
               'test_cross_entropy': test_loss, 'test_correct': int((predictions == labels).sum()),
               'batch_size': batch_size, 'optimizer': 'Adam', 'learning_rate': 0.001,
               'model': 'Conv32/Conv64/FC128/FC10', 'parallelism': 'DataParallel[0,1]',
               'gpu_names': gpu_names, 'gpu_peak_memory_bytes': gpu_peak_memory,
               'torch_version': torch.__version__, 'cuda_version': torch.version.cuda,
               'elapsed_seconds': time.monotonic() - started,
               'test_csv_sha256': hashlib.sha256(csv_path.read_bytes()).hexdigest(),
               'train_indices_sha256': hashlib.sha256(train_indices.numpy().tobytes()).hexdigest(),
               'validation_indices_sha256': hashlib.sha256(val_indices.numpy().tobytes()).hexdigest()}
    (output / 'metrics.json').write_text(json.dumps(metrics, indent=2), encoding='utf-8')
    (output / 'README.md').write_text(
        '# MNIST CNN test predictions on two NVIDIA T4 GPUs\n\n'
        'Official MNIST training split: 50,000 training and 10,000 validation samples, seed 42.\n'
        'Official MNIST test split: 10,000 samples. Three training epochs.\n'
        'The checkpoint is selected using validation accuracy before test evaluation.\n\n'
        'test_predictions.csv contains sample index, true/predicted labels, correctness,\n'
        'confidence and probabilities for digits 0 through 9. No image data is included.\n'
        'metrics.json records the experiment settings and observed metrics.\n'
        'training_history.csv records training and validation metrics per epoch.\n', encoding='utf-8')
    print(json.dumps({'event': 'completed', **metrics}), flush=True)


if __name__ == '__main__':
    main()
