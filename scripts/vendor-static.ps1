param(
  [string]$Root = (Split-Path -Parent $PSScriptRoot)
)

$VendorDir = Join-Path $Root "frontend" "static" "vendor"
$Libs = @(
  @{ Source = "node_modules/alpinejs/dist/cdn.min.js"; Dest = "alpine.min.js" }
)

if (-not (Test-Path $VendorDir)) {
  New-Item -ItemType Directory -Path $VendorDir -Force | Out-Null
}

$any = $false
foreach ($lib in $Libs) {
  $src = Join-Path $Root $lib.Source
  $dst = Join-Path $VendorDir $lib.Dest
  if (Test-Path $src) {
    if ((Test-Path $dst) -and ((Get-Item $dst).LastWriteTime -ge (Get-Item $src).LastWriteTime)) {
      continue
    }
    Write-Host "[VENDOR] Kopiowanie $($lib.Dest)..."
    Copy-Item -Path $src -Destination $dst -Force
    $any = $true
  } else {
    Write-Warning "[VENDOR] Brak źródła: $($lib.Source) — uruchom npm install"
  }
}

if (-not $any) {
  Write-Host "[VENDOR] Wszystkie biblioteki aktualne."
}
