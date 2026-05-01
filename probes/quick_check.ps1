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
Write-Host "=== VMware Processes ===" -ForegroundColor Yellow
$vmp = Get-Process -Name *vmware* -ErrorAction SilentlyContinue
if ($vmp) {
    foreach ($p in $vmp) {
        Write-Host ("  " + $p.Name + " PID=" + $p.Id) -ForegroundColor Red
    }
} else {
    Write-Host "  No VMware processes running" -ForegroundColor Green
}
