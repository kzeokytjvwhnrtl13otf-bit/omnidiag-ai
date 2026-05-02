Write-Host "=== Last 10 min System Errors ===" -ForegroundColor Yellow
try {
    $sysErr = Get-WinEvent -FilterHashtable @{LogName='System'; Level=2; StartTime=(Get-Date).AddMinutes(-10)} -MaxEvents 10 -ErrorAction Stop
    foreach ($e in $sysErr) {
        Write-Host ("  " + $e.TimeCreated.ToString() + " | " + $e.ProviderName + " | ID=" + $e.Id) -ForegroundColor Red
    }
} catch {
    Write-Host "  No system errors in last 10 min" -ForegroundColor Green
}

Write-Host ""
Write-Host "=== Last 10 min App Errors ===" -ForegroundColor Yellow
try {
    $appErr = Get-WinEvent -FilterHashtable @{LogName='Application'; Level=2; StartTime=(Get-Date).AddMinutes(-10)} -MaxEvents 10 -ErrorAction Stop
    foreach ($e in $appErr) {
        Write-Host ("  " + $e.TimeCreated.ToString() + " | " + $e.ProviderName + " | ID=" + $e.Id) -ForegroundColor Red
    }
} catch {
    Write-Host "  No app errors in last 10 min" -ForegroundColor Green
}

Write-Host ""
Write-Host "=== High Resource Processes (>200MB RAM) ===" -ForegroundColor Yellow
$highMem = Get-Process | Where-Object { $_.WorkingSet64 -gt 200MB } | Sort-Object -Property WorkingSet64 -Descending | Select-Object -First 10
if ($highMem) {
    foreach ($p in $highMem) {
        $memMB = [math]::Round($p.WorkingSet64 / 1MB, 1)
        Write-Host ("  " + $p.Name + " PID=" + $p.Id + " RAM=" + $memMB + "MB CPU=" + [math]::Round($p.CPU, 1) + "s") -ForegroundColor Red
    }
} else {
    Write-Host "  No high-resource processes detected" -ForegroundColor Green
}
