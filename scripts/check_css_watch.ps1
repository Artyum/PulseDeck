$root = (Get-Location).Path
$byTitle = @(Get-Process -ErrorAction SilentlyContinue | Where-Object {
    $_.MainWindowTitle -like '*PulseDeck CSS Watch*'
})
$byCmd = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -and $_.CommandLine.Contains($root) -and (
        $_.CommandLine -like '*css:watch*' -or $_.CommandLine -like '*tailwind*.css*--watch*'
    )
})
if (($byTitle + $byCmd).Count -gt 0) { '1' } else { '0' }
