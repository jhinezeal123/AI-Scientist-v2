param(
    [ValidateSet('setup','start','stop','status')][string]$Action = 'start',
    [switch]$ResetTemplates
)
$ErrorActionPreference = 'Stop'
$workspace = Split-Path -Parent $PSScriptRoot
$n8nRoot = Join-Path $workspace '.workbench/n8n'
$tools = Join-Path $workspace '.workbench/tools/n8n'
$entry = Join-Path $tools 'node_modules/n8n/bin/n8n'
$pidFile = Join-Path $n8nRoot 'process-id.txt'
$node = (Get-Command node -ErrorAction Stop).Source
New-Item -ItemType Directory -Path $n8nRoot -Force | Out-Null
$env:N8N_USER_FOLDER = Join-Path $n8nRoot 'profile'
$env:N8N_LISTEN_ADDRESS = '127.0.0.1'
$env:N8N_HOST = '127.0.0.1'
$env:N8N_PORT = '5678'
$env:N8N_PROTOCOL = 'http'
$env:N8N_EDITOR_BASE_URL = 'http://127.0.0.1:5678'
$env:N8N_WEBHOOK_URL = 'http://127.0.0.1:5678/'
$env:N8N_SECURE_COOKIE = 'false'
$env:N8N_DIAGNOSTICS_ENABLED = 'false'
$env:N8N_PERSONALIZATION_ENABLED = 'false'
$env:GENERIC_TIMEZONE = 'Asia/Ho_Chi_Minh'

function ManagedProcess {
    if (Test-Path -LiteralPath $pidFile) {
        $savedProcessId = [int](Get-Content -LiteralPath $pidFile)
        $process = Get-CimInstance Win32_Process -Filter "ProcessId=$savedProcessId" -ErrorAction SilentlyContinue
        if ($process -and $process.CommandLine.Contains($entry)) { return $process }
    }
    return $null
}

if ($Action -eq 'status') {
    if (ManagedProcess) { Write-Output 'n8n: http://127.0.0.1:5678' } else { Write-Output 'n8n is stopped' }
    exit
}
if ($Action -eq 'stop') {
    $process = ManagedProcess
    if ($process) { Stop-Process -Id $process.ProcessId -ErrorAction Stop }
    Write-Output 'n8n stopped; saved workflows and executions are retained'
    exit
}
if (!(Test-Path -LiteralPath $entry)) {
    $nodeMajor = [int]((& $node --version).TrimStart('v').Split('.')[0])
    if ($nodeMajor -lt 24) { throw 'Install Node.js 24 or later before setting up n8n' }
    & npm install --prefix $tools --save-exact n8n@2.42.6 --omit=dev --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw 'n8n installation failed' }
}
$marker = Join-Path $n8nRoot 'templates-installed.txt'
if (!(Test-Path -LiteralPath $marker) -or $ResetTemplates) {
    if (ManagedProcess) { throw 'Stop n8n before importing templates' }
    & python (Join-Path $workspace 'n8n/prepare_credentials.py')
    if ($LASTEXITCODE -ne 0) { throw 'Bridge credential preparation failed' }
    $credentialFile = Join-Path $n8nRoot 'credentials-import.json'
    & $node $entry import:credentials "--input=$credentialFile"
    if ($LASTEXITCODE -ne 0) { throw 'n8n credential import failed' }
    # This exact task-owned file contains the temporary unencrypted import.
    Remove-Item -LiteralPath $credentialFile -Force
    foreach ($workflowId in @('workbenchResearch','workbenchAgent')) {
        & $node $entry import:workflow "--input=$(Join-Path $workspace "n8n/$workflowId.json")"
        if ($LASTEXITCODE -ne 0) { throw 'n8n workflow import failed' }
        & $node $entry publish:workflow "--id=$workflowId"
        if ($LASTEXITCODE -ne 0) { throw 'n8n workflow publish failed' }
    }
    Set-Content -LiteralPath $marker -Value '2.42.6'
}
if ($Action -eq 'setup') { Write-Output 'n8n workflows are prepared'; exit }
if (!(ManagedProcess)) {
    $process = Start-Process -FilePath $node -ArgumentList @("`"$entry`"",'start') -WindowStyle Hidden -PassThru -WorkingDirectory $workspace -RedirectStandardOutput (Join-Path $n8nRoot 'server.out.log') -RedirectStandardError (Join-Path $n8nRoot 'server.err.log')
    Set-Content -LiteralPath $pidFile -Value $process.Id
}
Write-Output 'Open n8n: http://127.0.0.1:5678'
