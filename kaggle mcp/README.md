# Kaggle core bundled with AI Scientist

The folder name is retained from the packaging request; the runtime is native
Python/CLI, with no MCP server.

This is a selected source snapshot of `jhinezeal123/kaggle_token` at
`9bf4c85c8e060ebe022f285c1667a0edf5d4635f`, not a clone/submodule of the old MCP.
See `SOURCE.json` for source hashes and extraction notes.

## Included

- Private SDK bootstrap, Tailcat Tokyo relay, one persistent SSH terminal,
  file transfer/hash checks, status and STOP confirmation.
- Token profile resolution and the original account proxy connection pool.
- Account-wide idle verification and cookie recovery/login support, needed
  when an older ambiguous notebook cannot be reconciled by its reference.
- Native backend operations: `bootstrap_service.start` and `account_runtime.account_idle`.
  The backend calls CLI actions `start`/`idle` through its existing SSH adapter.

The old notebook builder/preflight, browser log/output download, cancel tools,
quota/account administration UI, datasets tool suite and agent_platform are
not included. Working owns execution, logs, artifact collection and shutdown.

## Local configuration

Install `requirements.txt` into the Workbench Python environment. Configure
`donor_root` as this directory and `donor_python` as that environment's Python.
Credentials never ship in Git. Copy `accounts.example.json` to
`profiles/accounts.json` and add one entry per account to the registry. Save
each token in its own `profiles/<alias>/token.txt`; only that account's
`web-session.json` is needed for account-wide idle verification. The local
MVP3 workspace has seven configured profiles. This folder remains ignored by
Git, so another checkout must import its own credentials.

```text
profiles/
  accounts.json                  # username, alias and relative profile paths
  credentials.json               # optional local auto-login configuration
  <alias>/token.txt               # Kaggle KGAT token
  <alias>/web-session.json        # cookie for account-wide idle verification
```

Each registry entry must use `token_file: profiles/<alias>/token.txt`.
Cookie/login support uses the same profile folder. Browser profile databases
are created locally on demand, not copied or versioned. New transient SSH keys,
Tailcat binaries and session state are under `.runtime/`; logs are in `logs/`.
All three folders are Git-ignored. SSH/Tailcat keys are hardened with the
original ACL logic, and no Codex credentials are transferred to Kaggle.

The bundle uses its own localhost token proxy on **8013**, with a health/root
identity check. It never borrows the old donor proxy on port 80. For a port
conflict set `AI_SCIENTIST_KAGGLE_PROXY_PORT` for the backend process; the SDK
and proxy use the same value. The backend stops a proxy it created on shutdown.
Tailcat downloads its pinned release and verifies SHA256 on first use.

From the repository root:

```powershell
.\.venv-mvp0\Scripts\python.exe -m pip install -r "kaggle mcp/requirements.txt"
```

The backend loads the proxy manager and calls the Kaggle CLI directly.
There is no MCP server, tool registration or MCP connection for normal GUI use.
The external `D:/Documents/kaggle_token` checkout is not
required after configuring this bundle. Saved stopped runs remain readable;
live sessions created by the external checkout retain its private state there.

MVP3 adds account selection in the Workbench Run panel. Readiness checks verify
idle status before a new account submits. Expired cookies require renewal in
that profile; a token file alone does not prove Kaggle readiness. Each run
persists its selected account so stop and recovery use the same identity.

To renew a cookie manually in this bundle, run from the repository root (replace
the account key with the desired profile):

```powershell
Push-Location "kaggle mcp"
..\.venv-mvp0\Scripts\python.exe web_session.py --account iyppxm.txt --login --headed
Pop-Location
```

Complete sign-in in the opened browser. It saves the cookie in the bundled
profile. Readiness only observes state and never opens that browser on its own.
Aggregate API counters are ignored at `.runtime/provider-metrics.sqlite3`;
credentials and response contents are not stored there.
