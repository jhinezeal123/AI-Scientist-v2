"""Standalone experiment: SDK push through the account proxy, then SSH/SFTP.

Runtime state and generated notebook contain ephemeral keys. Keep state under
.workbench; the Kaggle notebook is private. No Codex credential goes to Kaggle.
"""

import argparse
from datetime import datetime, timezone
import functools
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import socket
import subprocess
import time
import urllib.request
import urllib.parse
import uuid
import zipfile

BASE = Path(__file__).resolve().parents[2]
DEFAULT_STATE = BASE / ".workbench/tailcat-poc"
WIN_URL = "https://github.com/tailscale/tailcat/releases/download/v0.7.0/tailcat_0.7.0_windows_amd64.zip"
WIN_SHA256 = "f04cac07e3bf6c700b0b543df0d3315a3b312cd5a05ee76714e1cc848e9b2dff"


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def tailcat(state_root):
    binary = state_root / "bin/tailcat.exe"
    if not binary.exists():
        binary.parent.mkdir(parents=True, exist_ok=True)
        archive = binary.parent / "tailcat_0.7.0_windows_amd64.zip"
        with urllib.request.urlopen(WIN_URL, timeout=60) as response:
            data = response.read(20_000_001)
        if hashlib.sha256(data).hexdigest() != WIN_SHA256:
            raise RuntimeError("Tailcat Windows release checksum mismatch")
        archive.write_bytes(data)
        with zipfile.ZipFile(archive) as package:
            binary.write_bytes(package.read("tailcat.exe"))
    return binary


def prepare(args):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    config = load(args.config)
    run_id = uuid.uuid4().hex
    root = args.state_root / run_id
    root.mkdir(parents=True)
    binary = tailcat(args.state_root)
    server_key = root / "server.private.json"
    generated = subprocess.run(
        [str(binary), "genkey", "--key", str(server_key), "--fixed-region", "--embed-derp-map"],
        capture_output=True, text=True, timeout=45, check=True,
    )
    addresses = re.findall(r"\btc[A-Za-z0-9_-]{40,}", generated.stdout + generated.stderr)
    if len(addresses) != 1:
        raise RuntimeError("Expected exactly one fixed Tailcat address")
    ssh_key = Ed25519PrivateKey.generate()
    private = root / "id_ed25519"
    private.write_bytes(ssh_key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.OpenSSH, serialization.NoEncryption()))
    if os.name == "nt":
        owner = subprocess.run(["whoami"], capture_output=True, text=True, check=True, timeout=5).stdout.strip()
        subprocess.run(["icacls", str(private), "/inheritance:r", "/grant:r", owner + ":(R,W)"],
                       capture_output=True, check=True, timeout=5)
    else:
        private.chmod(0o600)
    public = ssh_key.public_key().public_bytes(
        serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH).decode("ascii")
    (root / "id_ed25519.pub").write_text(public + "\n", encoding="ascii")
    remote_config = {"run_id": run_id, "server_key": load(server_key),
                     "authorized_key": public, "ttl_seconds": args.ttl}
    source = (Path(__file__).with_name("bootstrap.py")).read_text(encoding="utf-8")
    source += "\nrun(" + repr(remote_config) + ")\n"
    compile(source, "bootstrap", "exec")
    bundle = root / "bundle"
    bundle.mkdir()
    notebook = {"nbformat": 4, "nbformat_minor": 5,
                "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}},
                "cells": [{"cell_type": "code", "id": "bootstrap", "metadata": {},
                           "execution_count": None, "outputs": [], "source": source}]}
    save(bundle / "notebook.ipynb", notebook)
    kernel_ref = config["kaggle_username"] + "/tailcat-ssh-poc-" + run_id[:12]
    meta = {"id": kernel_ref, "title": kernel_ref.split("/", 1)[1],
            "code_file": "notebook.ipynb", "language": "python", "kernel_type": "notebook",
            "is_private": True, "enable_gpu": False, "enable_tpu": False, "enable_internet": True,
            "competition_sources": ["soil-grain-size-from-photos"],
            "dataset_sources": [], "kernel_sources": []}
    save(bundle / "kernel-metadata.json", meta)
    state = {"run_id": run_id, "root": str(root), "config": str(args.config.resolve()),
             "tailcat": str(binary), "address": addresses[0], "kernel_ref": kernel_ref,
             "remote_root": "/kaggle/working/tailcat-poc/" + run_id, "ttl_seconds": args.ttl}
    save(root / "state.json", state)
    save(args.state_root / "latest.json", {"state": str(root / "state.json")})
    print(json.dumps({"state": str(root / "state.json"), "kernel_ref": kernel_ref, "cpu": True}))


def selected_state(args):
    path = args.state or Path(load(args.state_root / "latest.json")["state"])
    state = load(path)
    if not re.fullmatch(r"tc[A-Za-z0-9_-]{40,}", state["address"]):
        raise ValueError("Invalid Tailcat address")
    return state


def ensure_proxy(config, root):
    def listening():
        try:
            with socket.create_connection(("127.0.0.1", 80), timeout=0.5):
                return True
        except OSError:
            return False

    if listening():
        return
    with (root / "proxy.log").open("ab") as log:
        process = subprocess.Popen(
            [config["donor_python"], str(Path(config["donor_root"]) / "proxy.py"), "80"],
            cwd=config["donor_root"], stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    save(root / "owned-proxy.json", {"pid": process.pid})
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if listening():
            return
        if process.poll() is not None:
            raise RuntimeError("Account proxy exited; read proxy.log")
        time.sleep(0.1)
    raise RuntimeError("Account proxy did not start on port 80; read proxy.log")


def client(state):
    from kagglesdk.kaggle_client import KaggleClient
    from kagglesdk.kaggle_env import KaggleEnv

    config = load(Path(state["config"]))
    ensure_proxy(config, Path(state["root"]))
    alias = config["kaggle_account_alias"]
    if Path(alias).name != alias or Path(alias).suffix != ".txt":
        raise ValueError("Expected selected account token filename")
    token = (Path(config["donor_root"]) / alias).read_text(encoding="utf-8").strip()
    api = KaggleClient(env=KaggleEnv.LOCAL, api_token=token)
    http = api.http_client()
    http._init_session()  # SDK 0.1.37 exposes no public per-call timeout setting.
    http._session.send = functools.partial(http._session.send, timeout=(10, 90))
    return api


def push(state):
    from kagglesdk.kernels.types.kernels_api_service import ApiSaveKernelRequest
    from kagglesdk.kernels.types.kernels_enums import KernelExecutionType

    root = Path(state["root"])
    intent_path = root / "submit-intent.json"
    if intent_path.exists():
        raise RuntimeError("This execution already has a submit intent; do not push it again")
    meta = load(root / "bundle/kernel-metadata.json")
    source = (root / "bundle/notebook.ipynb").read_text(encoding="utf-8")
    request = ApiSaveKernelRequest()
    for field, value in {"slug": meta["id"], "new_title": meta["title"], "text": source,
                         "language": "python", "kernel_type": "notebook", "is_private": True,
                         "enable_gpu": False, "enable_tpu": False, "enable_internet": True,
                         "competition_data_sources": meta["competition_sources"],
                         "session_timeout_seconds": state["ttl_seconds"] + 90,
                         "kernel_execution_type": KernelExecutionType.SAVE_AND_RUN_ALL}.items():
        setattr(request, field, value)
    api = client(state)
    save(intent_path, {"kernel_ref": state["kernel_ref"], "status": "SUBMITTING",
                       "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
                       "created_at": datetime.now(timezone.utc).isoformat()})
    try:
        with api:
            response = api.kernels.kernels_api_client.save_kernel(request)
        result = json.loads(response.to_json())
        save(root / "push-response.json", result)
        if response.error:
            raise RuntimeError("Kaggle rejected bootstrap: " + response.error)
        resolved_ref = urllib.parse.urlsplit(response.url).path.removeprefix("/code/").strip("/")
        if resolved_ref.split("/", 1)[0] != state["kernel_ref"].split("/", 1)[0]:
            raise RuntimeError("Kaggle response owner mismatch")
        state["kernel_ref"] = resolved_ref
        save(root / "state.json", state)
        print(json.dumps(result))
    except Exception:
        # A lost response does not prove Kaggle rejected the request.
        print("SDK push failed or response unresolved; saved intent prevents replay", flush=True)
        raise


def ssh_options(state):
    root = Path(state["root"])
    return ["-i", str(root / "id_ed25519"), "-o", "IdentitiesOnly=yes",
            "-o", "BatchMode=yes", "-o", "ConnectTimeout=12", "-o", "ConnectionAttempts=1",
            "-o", "StrictHostKeyChecking=accept-new", "-o", "UserKnownHostsFile=" + str(root / "known_hosts"),
            "-o", 'ProxyCommand="' + state["tailcat"].replace("\\", "/") + '" ' + state["address"] + " 22"]


def remote(state, command, *, wait=30, data=None, record=None):
    started = time.monotonic()
    result = subprocess.run([shutil.which("ssh") or "ssh", *ssh_options(state), "-T",
                             state["address"], command], input=data, capture_output=True, timeout=wait)
    elapsed = time.monotonic() - started
    if record:
        save(Path(state["root"]) / record, {"returncode": result.returncode, "elapsed_sec": elapsed,
            "stdout": result.stdout.decode("utf-8", "replace"),
            "stderr": result.stderr.decode("utf-8", "replace").replace(state["address"], "<tailcat-address>")})
    return result, elapsed


def connect(state):
    deadline = time.monotonic() + 240
    print("Waiting for Kaggle bootstrap SSH (bounded to 240s)...", flush=True)
    while time.monotonic() < deadline:
        try:
            result, elapsed = remote(state, "python3 -c 'import json,os,platform; print(json.dumps({\"platform\":platform.system(),\"cwd\":os.getcwd(),\"uid\":os.getuid()}))'", record="connect.json")
            if result.returncode == 0:
                print(result.stdout.decode("utf-8", "replace").strip())
                print(json.dumps({"ssh_connected": True, "command_elapsed_sec": elapsed}))
                return
        except subprocess.TimeoutExpired:
            pass
        time.sleep(3)
    raise RuntimeError("SSH bootstrap unavailable; check exact Kaggle version, do not repush same execution")


def copy(state, source, destination):
    result = subprocess.run([shutil.which("scp") or "scp", *ssh_options(state), source, destination],
                            cwd=state["root"], capture_output=True, timeout=45)
    if result.returncode:
        raise RuntimeError("SFTP copy failed: " + result.stderr.decode("utf-8", "replace").replace(state["address"], "<tailcat-address>"))


def probe(state):
    root = Path(state["root"])
    remote_root = state["remote_root"]
    script = '''import csv, hashlib, json, os, platform
from pathlib import Path
root = Path(__file__).parent
inputs = Path("/kaggle/input")
competition = inputs / "competitions/soil-grain-size-from-photos"
csv_files = sorted(competition.rglob("*.csv")) if competition.is_dir() else []
result = {"platform": platform.system(), "uid": os.getuid(), "input_mount_exists": competition.is_dir(),
          "input_entries": sorted(p.name for p in inputs.iterdir()), "csv_files": [str(p) for p in csv_files]}
if csv_files:
    with csv_files[0].open(newline="") as handle:
        reader = csv.DictReader(handle)
        result.update(csv_columns=reader.fieldnames, csv_rows=sum(1 for _ in reader))
with (root / "synthetic.csv").open("w", newline="") as handle:
    writer = csv.writer(handle)
    writer.writerow(["x", "x_squared"])
    writer.writerows((i, i*i) for i in range(50))
result["source_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
(root / "result.json").write_text(json.dumps(result, indent=2))
row_count = len((root / "synthetic.csv").read_text().splitlines()) - 1
(root / "probe.log").write_text(f"REMOTE_PYTHON_START\\nDATA_INSPECTED\\nSYNTHETIC_ROWS={row_count}\\nREMOTE_PYTHON_DONE\\n")
print(json.dumps(result))
'''
    compile(script, "probe.py", "exec")
    (root / "probe.py").write_text(script, encoding="utf-8", newline="\n")
    copy(state, "probe.py", state["address"] + ":" + remote_root + "/probe.py")
    result, elapsed = remote(state, "python3 " + shlex.quote(remote_root + "/probe.py"), record="probe-exec.json")
    if result.returncode:
        raise RuntimeError("Remote Python probe failed; see probe-exec.json")
    for filename in ("result.json", "probe.log", "synthetic.csv"):
        copy(state, state["address"] + ":" + remote_root + "/" + filename, filename)
    evidence = load(root / "result.json")
    evidence["file_roundtrip_verified"] = evidence["source_sha256"] == hashlib.sha256((root / "probe.py").read_bytes()).hexdigest()
    if not evidence["file_roundtrip_verified"]:
        raise RuntimeError("Uploaded source hash does not match the executed remote file")
    evidence["exec_elapsed_sec"] = elapsed
    save(root / "probe-evidence.json", evidence)
    print(json.dumps(evidence))
    print((root / "probe.log").read_text(encoding="utf-8"))


def stop(state):
    result, elapsed = remote(state, "touch " + shlex.quote(state["remote_root"] + "/STOP"), record="stop.json")
    if result.returncode:
        raise RuntimeError("SSH stop failed; notebook still has bounded TTL")
    print(json.dumps({"stop_requested_over_ssh": True, "elapsed_sec": elapsed}))


def shell(state):
    command = "cd " + shlex.quote(state["remote_root"]) + " && exec bash --noprofile --norc"
    result = subprocess.run([shutil.which("ssh") or "ssh", *ssh_options(state), "-q", "-tt", state["address"], command])
    raise SystemExit(result.returncode)


def network(state):
    result = subprocess.run([state["tailcat"], "ping", "--until-direct", "--timeout=10s", state["address"]],
                            capture_output=True, text=True, timeout=20)
    evidence = {"direct_path_established": result.returncode == 0,
                "stdout": result.stdout, "stderr": result.stderr.replace(state["address"], "<tailcat-address>")}
    save(Path(state["root"]) / "network.json", evidence)
    print(json.dumps(evidence))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "push", "connect", "probe", "ssh", "shell", "stop", "network"))
    parser.add_argument("--config", type=Path, default=BASE / ".workbench/config.local.json")
    parser.add_argument("--state-root", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--state", type=Path)
    parser.add_argument("--ttl", type=int, default=480)
    parser.add_argument("--command", default="pwd")
    args = parser.parse_args()
    args.state_root = args.state_root.resolve()
    if not args.state_root.is_relative_to((BASE / ".workbench").resolve()):
        parser.error("Store ephemeral keys under this workspace's ignored .workbench directory")
    if not 60 <= args.ttl <= 510:
        parser.error("This CPU experiment permits a 60–510 second bootstrap TTL")
    if args.action == "prepare":
        prepare(args)
    else:
        state = selected_state(args)
        if args.action == "ssh":
            result, _ = remote(state, args.command, wait=60)
            print(result.stdout.decode("utf-8", "replace"), end="")
            print(result.stderr.decode("utf-8", "replace").replace(state["address"], "<tailcat-address>"), end="")
            raise SystemExit(result.returncode)
        globals()[args.action](state)


if __name__ == "__main__":
    main()
