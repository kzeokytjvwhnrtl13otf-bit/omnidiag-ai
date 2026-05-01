Write-Host "=============================" -ForegroundColor Cyan
Write-Host "  Full BSOD Diagnostic" -ForegroundColor Cyan
Write-Host "=============================" -ForegroundColor Cyan

Write-Host ""
Write-Host "=== 1. Kernel-Power 41 (30 days) ===" -ForegroundColor Yellow
try {
    $crashes = Get-WinEvent -FilterHashtable @{LogName='System'; Id=41; ProviderName='Microsoft-Windows-Kernel-Power'; StartTime=(Get-Date).AddDays(-30)} -MaxEvents 50 -ErrorAction Stop
    Write-Host ("Total: " + $crashes.Count) -ForegroundColor Red
    foreach ($c in $crashes) {
        $code = $c.Properties[0].Value
        Write-Host ("  " + $c.TimeCreated.ToString() + " BugcheckCode=" + $code) -ForegroundColor White
    }
} catch {
    Write-Host "  None found" -ForegroundColor Green
}

Write-Host ""
Write-Host "=== 2. WHEA Errors (30 days) ===" -ForegroundColor Yellow
try {
    $whea = Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='Microsoft-Windows-WHEA-Logger'; StartTime=(Get-Date).AddDays(-30)} -MaxEvents 50 -ErrorAction Stop
    Write-Host ("Total: " + $whea.Count) -ForegroundColor Red
    $grouped = $whea | Group-Object -Property Id
    foreach ($g in $grouped) {
        Write-Host ("  EventID " + $g.Name + ": " + $g.Count + " times") -ForegroundColor White
    }
    Write-Host ""
    Write-Host "  Latest 5 details:" -ForegroundColor Cyan
    $top5 = $whea | Select-Object -First 5
    foreach ($w in $top5) {
        $msgLen = $w.Message.Length
        if ($msgLen -gt 200) { $msgLen = 200 }
        $msg = $w.Message.Substring(0, $msgLen)
        Write-Host ("  [" + $w.TimeCreated.ToString() + "] ID=" + $w.Id) -ForegroundColor Gray
        Write-Host ("    " + $msg) -ForegroundColor Gray
    }
} catch {
    Write-Host "  None found" -ForegroundColor Green
}

Write-Host ""
Write-Host "=== 3. BugCheck Reports (30 days) ===" -ForegroundColor Yellow
try {
    $bugs = Get-WinEvent -FilterHashtable @{LogName='System'; Id=1001; ProviderName='Microsoft-Windows-WER-SystemErrorReporting'; StartTime=(Get-Date).AddDays(-30)} -MaxEvents 20 -ErrorAction Stop
    Write-Host ("Total: " + $bugs.Count) -ForegroundColor Red
    foreach ($b in $bugs) {
        $p = $b.Properties
        Write-Host ("  " + $b.TimeCreated.ToString()) -ForegroundColor White
        Write-Host ("    Code: " + $p[0].Value) -ForegroundColor Yellow
        Write-Host ("    P1: " + $p[1].Value + "  P2: " + $p[2].Value) -ForegroundColor Gray
        Write-Host ("    P3: " + $p[3].Value + "  P4: " + $p[4].Value) -ForegroundColor Gray
        if ($p.Count -gt 5) {
            Write-Host ("    Module: " + $p[5].Value) -ForegroundColor Cyan
        }
    }
} catch {
    Write-Host "  None found" -ForegroundColor Green
}

Write-Host ""
Write-Host "=== 4. CPU Throttle (30 days) ===" -ForegroundColor Yellow
try {
    $throttle = Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='Microsoft-Windows-Kernel-Processor-Power'; Id=37; StartTime=(Get-Date).AddDays(-30)} -MaxEvents 10 -ErrorAction Stop
    Write-Host ("Total: " + $throttle.Count) -ForegroundColor Red
    foreach ($t in $throttle) {
        $msgLen = $t.Message.Length
        if ($msgLen -gt 150) { $msgLen = 150 }
        Write-Host ("  " + $t.TimeCreated.ToString() + " " + $t.Message.Substring(0, $msgLen)) -ForegroundColor Gray
    }
} catch {
    Write-Host "  None found" -ForegroundColor Green
}

Write-Host ""
Write-Host "=== 5. Minidump Files ===" -ForegroundColor Yellow
$dumpPath = "C:\Windows\Minidump"
if (Test-Path $dumpPath) {
    $dumps = Get-ChildItem $dumpPath -Filter "*.dmp" | Sort-Object LastWriteTime -Descending | Select-Object -First 10
    Write-Host ("Found: " + $dumps.Count + " dump files") -ForegroundColor White
    foreach ($d in $dumps) {
        $sizeKB = [math]::Round($d.Length/1KB, 1)
        Write-Host ("  " + $d.Name + " - " + $d.LastWriteTime.ToString() + " - " + $sizeKB + "KB") -ForegroundColor Gray
    }
} else {
    Write-Host "  Minidump dir not found" -ForegroundColor Red
}

Write-Host ""
Write-Host "=== 6. Dump Creation Failures ===" -ForegroundColor Yellow
try {
    $dumpfail = Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='volmgr'; Id=161; StartTime=(Get-Date).AddDays(-30)} -MaxEvents 20 -ErrorAction Stop
    Write-Host ("Total failures: " + $dumpfail.Count) -ForegroundColor Red
} catch {
    Write-Host "  None found" -ForegroundColor Green
}

Write-Host ""
Write-Host "=== 7. Today Timeline ===" -ForegroundColor Yellow
try {
    $today = Get-WinEvent -FilterHashtable @{LogName='System'; Id=41,1001,6008; StartTime=(Get-Date).Date} -MaxEvents 30 -ErrorAction Stop
    foreach ($t in $today) {
        Write-Host ("  " + $t.TimeCreated.ToString() + " ID=" + $t.Id + " " + $t.ProviderName) -ForegroundColor White
    }
} catch {
    Write-Host "  No crashes today" -ForegroundColor Green
}

Write-Host ""
Write-Host "=== 8. App Crashes (7 days) ===" -ForegroundColor Yellow
try {
    $appcrash = Get-WinEvent -FilterHashtable @{LogName='Application'; Id=1000; StartTime=(Get-Date).AddDays(-7)} -MaxEvents 10 -ErrorAction Stop
    foreach ($a in $appcrash) {
        $p = $a.Properties
        Write-Host ("  " + $a.TimeCreated.ToString() + " Process: " + $p[0].Value + " Exception: " + $p[6].Value) -ForegroundColor Gray
    }
} catch {
    Write-Host "  None found" -ForegroundColor Green
}

Write-Host ""
Write-Host "===== DONE =====" -ForegroundColor Cyan
