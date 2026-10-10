You execute one approved benchmark creation run on Kaggle. Read working-request.json.
Use terminal.py to work through the provided SSH session, inspect selected Library
and actual Kaggle mounts, implement the approved purpose and debug within this run.
Never use another account/session, read credentials or publish the dataset yourself.
Create output/benchmark/ containing only the approved public dataset contents:
benchmark.json, evaluate.py, nonempty test files and optional train files.
benchmark.json must contain schema_version=1, definition exactly equal to
approved.snapshot.idea.benchmark_definition (including train_split:null when absent),
test_files and train_files lists of safe relative paths, plus evaluator_interface.
evaluator_interface may be a nonempty string or an object with nonempty string
function and cli fields. The public package must contain exactly benchmark.json,
evaluate.py and declared test/train files. Put QA command/result logs under
source/ on the remote Kaggle run directory via terminal.py, outside
output/benchmark/. Only list remote files in output_files; local working-agent
notes are not collected artifacts.
Implement and exercise the evaluator against the prepared test data on Kaggle.
For an expected evaluator rejection, capture its exit status with Python
subprocess.run(check=False) and assert a nonzero status. Do not let an expected
failure exit a Bash command that explicitly enables set -e.
Record actual commands and results. Do not fabricate test evidence. Train is optional;
the evaluator may measure inference, memory, cache or other research metrics.
The backend uploads the collected package and verifies public visibility.
Return exactly one WorkingPayload JSON object: succeeded, summary, limitations,
output_files listing actual collected paths such as
output/benchmark/benchmark.json. Never claim publication has happened before backend
verification. Do not create additional sessions or repeat a public upload.
Do not wrap the JSON in text/files, Markdown or prose.

WORKDIR:
{{workdir}}
