# Kaggle Tailcat experiment launcher

Kaggle implementation now lives in
[interface_ai_scientist](D:/Documents/kaggle_token/interface_ai_scientist/README.md).
poc.py is only a compatibility launcher that reads the donor paths and delegates
there. It contains no account token handling, SDK or SSH implementation.

Use the donor CLI for new sessions:

```powershell
Set-Location D:\Documents\kaggle_token
& .\.venv\Scripts\python.exe -m interface_ai_scientist prepare --account jhin_access_token.txt --competition-source soil-grain-size-from-photos
& .\.venv\Scripts\python.exe -m interface_ai_scientist push
& .\.venv\Scripts\python.exe -m interface_ai_scientist connect
& .\.venv\Scripts\python.exe -m interface_ai_scientist shell
```

[Original experiment](D:/Documents/AI-Scientist-v2/docs/customization/KAGGLE_TAILCAT_EXPERIMENT.md)
records the pre-refactor run. The GUI still uses the legacy MCP tools.