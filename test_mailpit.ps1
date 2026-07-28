$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$Host.UI.RawUI.WindowTitle = "PulseDeck Mailpit Test"
$CondaEnv = "pulsedeck"

# --- Mailpit (kontener na LAN) — zawsze wymuszane przez --mailpit ---
$MailpitHost = "192.168.50.50"
$MailpitPort = "1025"

Write-Host "============================================================"
Write-Host "  test_mailpit — test wysylki email przez Mailpit (PulseDeck)"
Write-Host "  SMTP: ${MailpitHost}:${MailpitPort} (nadpisuje .env)"
Write-Host "============================================================"
Write-Host ""

$Recipient = if ($args.Count -ge 1) { $args[0] } else { "test@pulsedeck.local" }

Write-Host "[CONDA] Aktywacja srodowiska $CondaEnv..."
$condaHook = & conda "shell.powershell" "hook" 2>$null
if (-not $condaHook) {
    Write-Host "[BLAD] conda nie jest w PATH"
    Read-Host "Enter"
    exit 1
}
$condaHook | Out-String | Invoke-Expression
conda activate $CondaEnv
if ($env:CONDA_DEFAULT_ENV -ne $CondaEnv) {
    Write-Host "[BLAD] conda env $CondaEnv nie istnieje"
    Read-Host "Enter"
    exit 1
}

Write-Host "[TEST] python scripts\test_smtp.py --mailpit $Recipient"
Write-Host ""
python (Join-Path $Root "scripts\test_smtp.py") --mailpit --smtp-server $MailpitHost --smtp-port $MailpitPort $Recipient
$code = $LASTEXITCODE
if ($code -ne 0) {
    Write-Host "[BLAD] Test zakonczyl sie kodem $code"
    Read-Host "Enter"
}
exit $code
