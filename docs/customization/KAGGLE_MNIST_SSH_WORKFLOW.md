# MNIST CNN workflow through persistent Kaggle SSH

Completed on **2026-10-07** using account **huynhtrungcuong**.

## Result

| Item | Observed result |
|---|---|
| Bootstrap | `3468d4a3a6b64d6aa4681eb087590e3d`, one SDK submit, version 1 |
| Notebook | [ai-scientist-ssh-3468d4a3a6b6](https://www.kaggle.com/code/huynhtrungcuong/ai-scientist-ssh-3468d4a3a6b6) |
| Kernel ID | `137438836` |
| Accelerator | `NvidiaTeslaT4`: two Tesla T4 GPUs, 15,360 MiB each |
| Model | Conv32 → Conv64 → FC128 → FC10, dropout 0.25, Adam lr 0.001 |
| Splits | 50,000 train / 10,000 validation from the official training split; official 10,000 test images |
| Training | 3 epochs, batch 512, seed 42, FP16 autocast, DataParallel on GPUs 0 and 1 |
| Checkpoint selection | Best validation accuracy; epoch 3, validation accuracy **98.37%** |
| Test | **98.78%**, 9,878 correct / 10,000; cross-entropy `0.04053255` |
| GPU peak allocation | GPU 0: 471,859,200 bytes; GPU 1: 71,272,960 bytes |
| Workload elapsed | 11.22 seconds, including MNIST download, training and evaluation; excludes shell setup and publishing |
| Dataset | [Public test predictions](https://www.kaggle.com/datasets/huynhtrungcuong/mnist-cnn-t4x2-test-20261007-3468d4a3), dataset ID `12417763`, version 1 |
| Publication | CLI inside the same SSH terminal; Kaggle-provided notebook authentication, no local profile token transferred |
| Final notebook state | `complete`, verified through token-authenticated REST GET at 06:09:33 UTC / 13:09:33 Asia/Saigon |

The test set was evaluated after checkpoint selection. Train and validation
indices were disjoint. Both GPUs were used; allocation was measured on both.

## Public files and verification

The dataset contains only:

- `test_predictions.csv`: 10,000 rows, sample index, true label, predicted
  label, correctness, confidence and ten class probabilities.
- `metrics.json`: settings, hardware and evaluation results.
- `training_history.csv`: metrics for the three epochs.
- `README.md`: data dictionary and split/checkpoint description.

The API was read without authentication and returned `isPrivate=false`,
version 1. Dataset status was `ready`. An anonymous archive download succeeded.
The downloaded CSV hash matched the remote result:

```text
2371f42eb6292b2acdedf61161afee0c66e1c72b4fcc4f35a21aae58ad01a471
```

Verification checked 10,000 unique sample IDs, 9,878 correct predictions and
probability sums within `1e-5`. Public CSV size: 2,500,781 bytes.
Training data, checkpoint and tunnel files were outside the published folder.

Local downloaded files and verification receipts:
[experiment directory](D:/Documents/AI-Scientist-v2/.workbench/experiments/mnist-t4x2/3468d4a3a6b64d6aa4681eb087590e3d).

## SSH and issues encountered

One interactive SSH terminal handled environment recovery, workload upload,
training, CSV verification, dataset publication and STOP. Commands were sent
into that terminal instead of starting SSH for every command. A readiness probe
preceded this terminal. STOP was sent only after dataset readiness and public
access were confirmed. The local SSH client was then closed.

1. The old account-idle check encountered an expired cookie and could not
   refresh it. The SDK bootstrap and notebook authentication still worked.
2. Tailcat's default SSH command environment omitted notebook variables:
   initial torch CUDA device count was zero, Kaggle authentication was absent,
   and the default PATH omitted `nvidia-smi`. The VM nevertheless had two GPUs.
   The notebook environment was recovered from the Tailcat parent process in
   memory; CUDA device count became two and identity resolved to huynhtrungcuong.
3. An initial heredoc environment launcher inherited EOF on stdin, so the new
   shell exited. Reattaching stdin to the same PTY kept the shell alive.
4. The pinned generated SDK status method returned HTTP 404. The established
   REST endpoint `/api/v1/kernels/status` with `user_name` and `kernel_slug`
   query parameters confirmed `complete`. Slug-in-path forms also returned 404.

The donor launcher now restores the notebook environment before shell/command
execution, without saving credentials to disk. Generated native SSH configs
include this RemoteCommand. Keepalives bound detection of an unreachable SSH
server. The fix passed source compilation and native OpenSSH config parsing;
it was applied after the live workflow and has not received another live submit.
Reconnect existing MCP clients to load the updated launcher.

## Reproduce

Workload source:
[mnist_cnn.py](D:/Documents/AI-Scientist-v2/tools/kaggle_tailcat/workflows/mnist_cnn.py).
It accepts `--root <remote experiment directory>` and `--epochs 3`.

Start a fresh SSH bootstrap with `accelerator=NvidiaT4`, open its returned
terminal command and execute the workload there. Create `dataset-metadata.json`
in the dedicated output directory, choose a fresh dataset slug, then run:

```bash
kaggle datasets create -p <experiment-root>/outputs --public -t
```

Verify readiness/public visibility before executing the returned STOP command.
STOP ends the notebook normally; it is not the platform Cancel operation.

References: [Kaggle dataset CLI](https://github.com/Kaggle/kaggle-cli/blob/main/docs/datasets.md),
[MNIST dataset loader](https://docs.pytorch.org/vision/stable/generated/torchvision.datasets.MNIST.html).
