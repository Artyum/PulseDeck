param(
  [string]$EnvFile = "deploy/.env.dev"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$CondaEnv = "pulsedeck"

if (-not (Test-Path $EnvFile)) {
  Write-Error "Missing $EnvFile"
}

Write-Host "[ENV] Ladowanie zmiennych srodowiskowych..."
$json = python -c "import json,sys; from pathlib import Path; sys.path.insert(0, r'$Root'); from scripts.load_env import parse_env_file; print(json.dumps(parse_env_file(sys.argv[1])))" "$EnvFile"
if ($LASTEXITCODE -ne 0) {
  Write-Error "Nie udalo sie odczytac env"
}
$pairs = $json | ConvertFrom-Json
foreach ($pair in $pairs) {
  Set-Item -Path "Env:$($pair[0])" -Value $pair[1]
}

Write-Host "[CONDA] Aktywacja srodowiska $CondaEnv..."
$condaHook = & conda "shell.powershell" "hook" 2>$null
if (-not $condaHook) {
  Write-Error "conda nie jest w PATH"
}
$condaHook | Out-String | Invoke-Expression
conda activate $CondaEnv
if ($env:CONDA_DEFAULT_ENV -ne $CondaEnv) {
  Write-Error "conda env `"$CondaEnv`" nie istnieje"
}

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
  Write-Error "Brak npm - zainstaluj Node.js"
}
if (-not (Test-Path (Join-Path $Root "node_modules\prettier"))) {
  Write-Host "[NPM] Instalowanie zaleznosci frontend..."
  npm ci
  if ($LASTEXITCODE -ne 0) {
    Write-Error "npm ci failed"
  }
}

& (Join-Path $Root "scripts\vendor-static.ps1")

if (-not (Test-Path "frontend/static/css/app.css")) {
  npm run css:build:dev
}

if (-not (Test-Path "frontend/static/js/editor.bundle.js")) {
  Write-Host "[JS] Budowanie edytora (js:build)..."
  npm run js:build
  if ($LASTEXITCODE -ne 0) {
    Write-Error "npm run js:build failed"
  }
}


$hostAddr = if ($env:UVICORN_HOST) { $env:UVICORN_HOST } else { "127.0.0.1" }
$port = if ($env:UVICORN_PORT) { $env:UVICORN_PORT } else { "8000" }

Remove-Item Env:\NO_COLOR -ErrorAction SilentlyContinue
$env:FORCE_COLOR = "1"
if ($env:TERM -eq "dumb") {
  Remove-Item Env:\TERM -ErrorAction SilentlyContinue
}

$cssRunning = & (Join-Path $Root "scripts\check_css_watch.ps1")
if ($cssRunning -eq "1") {
  Write-Host "[CSS] Tailwind watch juz dziala - pomijam nowe okno"
} else {
  Write-Host "[CSS] Otwieranie okna Tailwind watch"
  $cli = Join-Path $Root "node_modules\@tailwindcss\cli\dist\index.mjs"
  $cmdLine = "title PulseDeck CSS Watcher && node `"$cli`" -i frontend/static/css/tailwind.css -o frontend/static/css/app.css --watch"
  Start-Process -FilePath 'cmd.exe' -ArgumentList @('/k', $cmdLine) -WorkingDirectory $Root
}

Write-Host "[API] Serwer: http://${hostAddr}:${port}"
python -m alembic upgrade head
python -m app.bootstrap
python -m uvicorn app.main:fastapi_app --host $hostAddr --port $port --reload
