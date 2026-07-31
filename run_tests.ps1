param(
    [Parameter(Position = 0)]
    [string]$TestTarget,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PytestArgs
)

$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
Set-Location $Root
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
} catch {}

$CondaEnv = 'pulsedeck'

function Write-Step([string]$Message, [string]$Color = 'Cyan') {
    Write-Host $Message -ForegroundColor $Color
}

function Fail([string]$Message) {
    Write-Host "[BLAD] $Message" -ForegroundColor Red
    exit 1
}

function Import-EnvFile {
    param([string]$Path)
    Write-Step "[ENV] Ladowanie $Path ..." 'DarkGray'
    $json = python -c "import json,sys; from pathlib import Path; sys.path.insert(0, r'$Root'); from scripts.load_env import parse_env_file; print(json.dumps(parse_env_file(sys.argv[1])))" "$Path"
    if ($LASTEXITCODE -ne 0) { return $false }
    $pairs = $json | ConvertFrom-Json
    foreach ($pair in $pairs) {
        Set-Item -Path "Env:$($pair[0])" -Value $pair[1]
    }
    return $true
}

function Resolve-TestFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$TestArg,
        [Parameter(Mandatory = $true)]
        [string]$TestRoot
    )

    $normalized = $TestArg -replace '/', '\'
    if (Test-Path -LiteralPath $normalized) {
        return (Resolve-Path -LiteralPath $normalized).Path
    }

    $underRoot = Join-Path $TestRoot $normalized
    if (Test-Path -LiteralPath $underRoot) {
        return (Resolve-Path -LiteralPath $underRoot).Path
    }

    if ([System.IO.Path]::GetExtension($TestArg) -ieq '.py') {
        $filter = [System.IO.Path]::GetFileName($TestArg)
    } else {
        $filter = "$normalized.py"
        if ($filter -match '[\\/]') {
            $filter = [System.IO.Path]::GetFileName($filter)
        }
    }

    $found = Get-ChildItem -Path $TestRoot -Recurse -Filter $filter -File -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($found) {
        return $found.FullName
    }
    return $null
}

$envDev = Join-Path $Root 'deploy\.env.dev'
$envLegacy = Join-Path $Root '.env'
if (Test-Path $envDev) {
    if (-not (Import-EnvFile $envDev)) { exit 1 }
} elseif (Test-Path $envLegacy) {
    if (-not (Import-EnvFile $envLegacy)) { exit 1 }
}

Write-Step "[CONDA] Aktywacja srodowiska $CondaEnv..."
if (-not (Get-Command conda -ErrorAction SilentlyContinue)) {
    Fail 'conda nie znalezione w PATH'
}
try {
    Invoke-Expression (& conda 'shell.powershell' 'hook' | Out-String)
    conda activate $CondaEnv
} catch {
    Fail "conda env `"$CondaEnv`" nie istnieje"
}
if ($env:CONDA_DEFAULT_ENV -ne $CondaEnv) {
    Fail "conda env `"$CondaEnv`" nie istnieje"
}

Write-Step 'Instalowanie zaleznosci deweloperskich...' 'Yellow'
& pip install -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$env:PY_COLORS = '1'
$env:FORCE_COLOR = '1'
$TestRoot = Join-Path $Root 'tests'
$runCoverage = $true

Write-Host ''
if ($TestTarget) {
    $testFile = Resolve-TestFile -TestArg $TestTarget -TestRoot $TestRoot
    if (-not $testFile) {
        Fail "Nie znaleziono pliku testow: $TestTarget`n       Szukano w: $TestRoot"
    }
    if (-not (Test-Path -LiteralPath $testFile)) {
        Fail "Plik testow nie istnieje: $testFile"
    }
    Write-Step "===== Uruchamianie: $testFile =====" 'Magenta'
    $runCoverage = $false
    & python -m pytest $testFile -v --tb=line --color=yes @PytestArgs
} else {
    Write-Step '===== Uruchamianie wszystkich testow =====' 'Magenta'
    & python -m pytest tests/ -v --tb=line --color=yes --cov=app --cov-report=term-missing @PytestArgs
}

$pytestExit = $LASTEXITCODE

Write-Host ''
if ($runCoverage) {
    Write-Step '[SPRZATANIE] Usuwanie pliku .coverage...' 'Yellow'
    $coverageFile = Join-Path $Root '.coverage'
    if (Test-Path -LiteralPath $coverageFile) {
        Remove-Item -LiteralPath $coverageFile -Force
        Write-Step '[OK] .coverage usuniety.' 'Green'
    } else {
        Write-Step '[INFO] .coverage nie istnieje - pomijam.' 'DarkGray'
    }
}

exit $pytestExit
