$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

[Console]::OutputEncoding = [Text.Encoding]::UTF8
$OutputEncoding = [Text.Encoding]::UTF8

$Log = Join-Path $Root "report\lint_check.log"
$env:NO_COLOR = "1"
$env:FORCE_COLOR = "0"
$env:TERM = "dumb"
$env:CI = "1"
$CondaEnv = "pulsedeck"
$Total = 10

Write-Host ""
Write-Host "============ LINT CHECK (PulseDeck) ============"
Write-Host ""

$reportDir = Join-Path $Root "report"
if (-not (Test-Path $reportDir)) {
    New-Item -ItemType Directory -Path $reportDir | Out-Null
}

if (-not (Get-Command conda -ErrorAction SilentlyContinue)) {
    Write-Host "[BLAD] conda nie znalezione w PATH"
    exit 1
}

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Host "[BLAD] Brak npm - zainstaluj Node.js"
    exit 1
}
if (-not (Test-Path (Join-Path $Root "node_modules\prettier"))) {
    Write-Host "[NPM] Instalowanie zaleznosci frontend..."
    npm ci
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[BLAD] npm ci failed"
        exit 1
    }
}

Set-Content -LiteralPath $Log -Encoding UTF8 -Value @(
    "========================================",
    " LINT CHECK - $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')",
    "========================================",
    ""
)

function Invoke-LintStep {
    param(
        [int]$StepNo,
        [string]$Title,
        [string]$Command
    )

    Write-Host "[Krok $StepNo/$Total] $Title..."

    Add-Content -LiteralPath $Log -Encoding UTF8 -Value @(
        "--- Krok $StepNo/${Total}: $Title ---",
        (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'),
        ""
    )

    $stdout = Join-Path $env:TEMP "lint_stdout_$PID.log"
    $stderr = Join-Path $env:TEMP "lint_stderr_$PID.log"

    $process = Start-Process -FilePath "cmd.exe" -ArgumentList @("/d", "/s", "/c", $Command) `
        -NoNewWindow -Wait -PassThru `
        -RedirectStandardOutput $stdout -RedirectStandardError $stderr

    $esc = [char]27
    $csi = [regex]::new("$([regex]::Escape($esc.ToString()))\[[0-?]*[ -/]*[@-~]")
    $osc = [regex]::new("$([regex]::Escape($esc.ToString()))\][^\x07$([regex]::Escape($esc.ToString()))]*(?:\x07|$([regex]::Escape($esc.ToString()))\\)")
    $oscOrphan = [regex]::new('\]8;[^\s]*?\\([^\\]+?)\\]8;;\\')

    $lines = @()
    foreach ($path in @($stdout, $stderr)) {
        if (Test-Path -LiteralPath $path) {
            $lines += Get-Content -LiteralPath $path -Encoding UTF8 -ErrorAction SilentlyContinue
        }
    }

    $lines | ForEach-Object {
        $text = [string]$_
        $text = $csi.Replace($text, "")
        $text = $osc.Replace($text, "")
        $text = $oscOrphan.Replace($text, '${1}')
        $text = $text -replace [string][char]0xFFFD, ""
        $text
    } | Where-Object {
        $_ -and
        $_ -notmatch '^System\.Management\.Automation\.RemoteException$' -and
        $_ -notmatch '^Reformatting \d+/\d+ files'
    } | Add-Content -LiteralPath $Log -Encoding UTF8

    Add-Content -LiteralPath $Log -Encoding UTF8 -Value @("", "========================================", "")
    Remove-Item -LiteralPath $stdout, $stderr -Force -ErrorAction SilentlyContinue

    return $process.ExitCode
}

function Invoke-CondaLint {
    param([string]$ToolArgs)
    return "conda run -n $CondaEnv --no-capture-output $ToolArgs"
}

$results = @(
    (Invoke-LintStep 1 "ruff format" (Invoke-CondaLint "ruff format . --color=never"))
    (Invoke-LintStep 2 "djlint --reformat" (Invoke-CondaLint "djlint frontend/templates/ app/templates/ --reformat >nul 2>&1 & exit /b 0"))
    (Invoke-LintStep 3 "npm run format" "npm run format")
    (Invoke-LintStep 4 "ruff check --fix-only --show-fixes" (Invoke-CondaLint "ruff check . --fix-only --show-fixes --color=never"))
    (Invoke-LintStep 5 "ruff check --output-format=concise" (Invoke-CondaLint "ruff check . --output-format=concise --color=never"))
    (Invoke-LintStep 6 "basedpyright" (Invoke-CondaLint "basedpyright"))
    (Invoke-LintStep 7 "djlint --lint" (Invoke-CondaLint "djlint frontend/templates/ app/templates/ --lint"))
    (Invoke-LintStep 8 "npm run format:check" "npm run format:check")
    (Invoke-LintStep 9 "npm run lint:css" "npm run lint:css")
    (Invoke-LintStep 10 "npm run lint:dup" "npm run lint:dup")
)

Write-Host ""
Write-Host "============ PODSUMOWANIE ============"
Write-Host ""

$anyFail = $false
for ($i = 0; $i -lt $Total; $i++) {
    $stepNo = $i + 1
    if ($results[$i] -eq 0) {
        Write-Host "  [$stepNo] PASS"
    } else {
        Write-Host "  [$stepNo] FAIL"
        $anyFail = $true
    }
}

Write-Host ""
Write-Host "  Log: $Log"
Write-Host ""

Add-Content -LiteralPath $Log -Encoding UTF8 -Value @(
    "",
    "========================================",
    " PODSUMOWANIE",
    "========================================",
    ""
)
for ($i = 0; $i -lt $Total; $i++) {
    $stepNo = $i + 1
    if ($results[$i] -eq 0) {
        Add-Content -LiteralPath $Log -Encoding UTF8 -Value "  [$stepNo] PASS"
    } else {
        Add-Content -LiteralPath $Log -Encoding UTF8 -Value "  [$stepNo] FAIL"
    }
}
Add-Content -LiteralPath $Log -Encoding UTF8 -Value ""

if ($anyFail) {
    Write-Host "[BLAD] Niektore kroki zakonczone bledem - sprawdz log."
    exit 1
}

Write-Host "[OK] Wszystkie kroki zakonczone pomyslnie."
exit 0
