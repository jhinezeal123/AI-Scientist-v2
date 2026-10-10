# Kaggle proxy Settings

Open Workbench and click the gear at the top right. Direct local URL:
`http://127.0.0.1:8011/?page=settings&tab=kaggle-proxy`.
Settings currently has one tab, **Kaggle proxy**, shared by all local projects.

## Account management

- **Thêm account** requires the Kaggle username, its `KGAT_...` token and its
  password. The token owner is verified with Kaggle before storing the profile.
  Saving starts the bundled auto-login helper and reports its progress.
- **Xóa** opens an inline confirmation requiring the exact username. It
  permanently removes the token, cookie, browser profile, password entry and
  registry entry from this bundled proxy. There is no archive or restore copy.
  Existing run history remains readable. Delete is blocked while that account
  has queued/running/unconfirmed local work or cannot be verified idle on Kaggle.
- All private data stays in ignored `kaggle mcp/profiles/` with restricted local
  file permissions. Neither passwords nor tokens are returned to the GUI.
- The local proxy notices account changes without restarting. A proxy with no
  accounts can still start so the Settings page can add its first account.

## Quota and sessions

The account list reads remaining GPU/TPU hours from Kaggle. Unknown data appears
as unavailable rather than zero. **Làm mới quota / session** requests new data;
ordinary reads share a cache lasting up to 60 seconds.

Select an account to inspect its active sessions, accelerator, provider session
ID, notebook version and status. A session associated with an active Workbench
run shows the project, run and **Mở run trong Workbench** link. Matching requires
the same account and notebook reference/current attempt; ambiguous or external
sessions are labeled as unassociated. Notebook reference enrichment failures do
not hide the provider's active sessions.

## Check cookie

**Check cookie** checks each account and identifies expired, rejected or
incorrect-identity cookies. Only those accounts invoke the bundled auto-login
helper, once per check. Successful login verifies the new cookie's identity and
refreshes quota/session data. Valid cookies and network errors do not trigger
login. The page polls the job and shows each account's result.

If Kaggle requires additional verification, complete sign-in manually using the
bundled login command documented in `kaggle mcp/README.md`, then check again.
Opening Settings or refreshing quota does not start a browser login.

### Run start gate

Starting Working in the Run tab checks the selected account again. An expired,
rejected or incorrect-identity cookie invokes the same auto-login helper, then
rechecks the account identity and available capacity before submitting the
notebook. Success continues the original run with its selected account. Failure,
missing credentials or additional verification stops before submission and shows
an actionable error. A busy account or network failure alone does not start login.

Batch Working runs concurrently, with independent workers and SSH terminals.
Each account allows at most two sessions, including provider sessions started
outside Workbench and local starts not yet visible at Kaggle. Extra runs wait
automatically; a full account does not block another account. An unconfirmed
stop retains its slot. The same gate applies to individual Working requests.

Queued runs repeat this gate when dispatched, so cookies expiring while waiting
are renewed before that run begins. The queue shows login progress; cancellation
during login prevents notebook submission. Interrupted queued login resumes as
unsubmitted work after a backend restart. Run and Settings share a login lock to
avoid overlapping browser recovery.

## Implementation and verification

The Workbench page/API uses the existing account catalog, run history and native
CLI boundary. Selected donor quota/session functions were adapted into the local
bundle; runtime access to `D:/Documents/kaggle_token` is unnecessary.

Verification on 2026-10-10:

- Production frontend build succeeded; focused Workbench tests passed.
- Real Settings data verified all seven configured accounts: GPU 30/30 hours,
  TPU 20/20 hours and zero active sessions at observation time.
- Browser checks covered gear navigation, required secret fields, account
  selection and permanent-delete confirmation without deleting a real account.
- The GUI cookie job detected a deliberately expired local expiry timestamp for
  `iyppmx`, performed real auto-login, verified the renewed identity and completed
  all seven accounts (one renewed, six already valid). Its temporary QA backup
  was removed after success. No provider cookie revocation was simulated.
- Permanent deletion and session-to-run matching were verified with isolated
  test profiles; live session mapping was not exercised because all accounts
  were idle. No new Kaggle notebook run was submitted for GUI verification.
- Run start gate: 38 focused Working/account/Settings tests passed, including
  success, login failure, valid-cookie/no-login, busy/network failures, queued
  expiry, cancellation during login and interrupted queue recovery. The frontend
  production build passed.
- A live `iyppmx` cookie with a deliberately expired local timestamp exercised
  `WorkingService.start`: `needs_login → renewed → verified_idle → submission`.
  Login and idle verification used real Kaggle; the notebook submission, terminal
  and agent were isolated local fixtures and completed the local run. This check
  submitted zero real Kaggle notebooks and stored no cookie backup on disk.
