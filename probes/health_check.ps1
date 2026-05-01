Write-Host "=============================" -ForegroundColor Cyan
Write-Host "  System Health Check" -ForegroundColor Cyan
Write-Host "=============================" -ForegroundColor Cyan

Write-Host "`n=== 1. Disk Health (SMART) ===" -ForegroundColor Yellow
Get-PhysicalDisk | Select-Object DeviceId, Model, MediaType, OperationalStatus, HealthStatus | Format-Table -AutoSize | Out-String | Write-Host

Write-Host "=== 2. Device Manager Issues ===" -ForegroundColor Yellow
$badDevices = Get-WmiObject Win32_PnPEntity | Where-Object { $_.ConfigManagerErrorCode -ne 0 }
if ($badDevices) {
    foreach ($dev in $badDevices) {
         Write-Host "  Device: $($dev.Name), ErrorCode: $($dev.ConfigManagerErrorCode)" -ForegroundColor Red
    }
} else {
    Write-Host "  No devices with errors found." -ForegroundColor Green
}

Write-Host "`n=== 3. Potential Conflicting Software (Running) ===" -ForegroundColor Yellow
$searchList = @("vgc", "vgk", "EasyAntiCheat", "BattlEye", "XTU", "ThrottleStop", "Afterburner", "RivaTuner", "iCUE", "ArmouryCrate", "DragonCenter", "wallpaper", "huorong", "360")
$runningProcs = Get-Process
$foundConflicts = $false
foreach ($s in $searchList) {
    $found = $runningProcs | Where-Object { $_.Name -match $s }
    if ($found) {
        Write-Host "  Found running: $($found[0].Name)" -ForegroundColor Red
        $foundConflicts = $true
    }
}
if (-not $foundConflicts) { Write-Host "  No common conflicting software running." -ForegroundColor Green }


Write-Host "`n=== 4. Registered Antivirus ===" -ForegroundColor Yellow
try {
    $av = Get-WmiObject -Namespace "root\SecurityCenter2" -Class AntiVirusProduct -ErrorAction Stop
    foreach ($a in $av) { Write-Host ("  " + $a.displayName) -ForegroundColor White }
} catch { Write-Host "  Could not query SecurityCenter2." -ForegroundColor Gray }

Write-Host "`n=== 5. OS Image Health (DISM Quick Check) ===" -ForegroundColor Yellow
$dism = dism /Online /Cleanup-Image /CheckHealth 2>&1
foreach ($line in $dism) {
    Write-Host "  $line" -ForegroundColor White
}

Write-Host "`n=== 6. Recent Application Errors (Event Viewer) ===" -ForegroundColor Yellow
try {
    $appErrors = Get-WinEvent -FilterHashtable @{LogName='Application'; Level=2; StartTime=(Get-Date).AddDays(-1)} -MaxEvents 5 -ErrorAction Stop
    foreach ($e in $appErrors) {
        $msg = $e.Message -replace "`n", " " -replace "`r", " "
        if ($msg.Length -gt 120) { $msg = $msg.Substring(0, 120) + "..." }
        Write-Host "  $($e.TimeCreated) - Source: $($e.ProviderName) - $msg" -ForegroundColor White
    }
} catch { Write-Host "  No recent app errors." -ForegroundColor Green }


Write-Host "`n===== DONE =====" -ForegroundColor Cyan
