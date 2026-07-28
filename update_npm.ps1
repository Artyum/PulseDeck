$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$Host.UI.RawUI.WindowTitle = "PulseDeck npm update"

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Host "[BLAD] Brak npm - zainstaluj Node.js"
    Read-Host "Enter"
    exit 1
}

Write-Host "[NPM] Stan przed aktualizacja (npm outdated)..."
npm outdated
# exit 1 gdy sa outdated - to OK

Write-Host ""
Write-Host "[NPM] Aktualizacja w ramach zakresow z package.json (npm update)..."
npm update
if (-not $?) {
    Write-Host "[BLAD] npm update failed"
    Read-Host "Enter"
    exit 1
}

Write-Host ""
Write-Host "[NPM] Bezpieczne poprawki podatnosci (npm audit fix)..."
npm audit fix
if (-not $?) {
    Write-Host "[BLAD] npm audit fix failed"
    Read-Host "Enter"
    exit 1
}

Write-Host ""
Write-Host "[NPM] Usuwanie pozostalosci (npm prune)..."
npm prune
if (-not $?) {
    Write-Host "[BLAD] npm prune failed"
    Read-Host "Enter"
    exit 1
}

Write-Host ""
Write-Host "[NPM] Audyt po aktualizacji..."
npm audit
# exit != 0 gdy zostaly podatnosci - informacyjnie

Write-Host ""
Write-Host "[CSS] Budowanie Tailwind (css:build:dev)..."
npm run css:build:dev
if (-not $?) {
    Write-Host "[BLAD] npm run css:build:dev failed"
    Read-Host "Enter"
    exit 1
}

Write-Host ""
Write-Host "[OK] Gotowe. Jesli zmienil sie package-lock.json - zacommituj go."
Write-Host "     Major bump (poza ^/~) rob recznie w package.json."
exit 0
