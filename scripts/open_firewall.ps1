# Mo cong 8000 cho DIEN THOAI trong cung WiFi truy cap vao.
#
# VI SAO CAN: Windows Firewall mac dinh CHAN ket noi tu may khac vao (BlockInbound).
# Tren may nay da co 1 rule cho cong 8000 nhung ten "WazuhLab HTTP 8000" va CHI mo
# cho subnet 192.168.254.0/24 -> dien thoai trong WiFi 192.168.1.x KHONG vao duoc.
#
# Script nay them 1 rule dung: moi profile, moi IP nguon.
# Lan dau se hien hop thoai UAC -> bam Yes.
#
# Chay tay: powershell -ExecutionPolicy Bypass -File scripts\open_firewall.ps1

$ruleName = "EN-VI Translator 8000"
$port = 8000

function Test-Rule {
    $out = netsh advfirewall firewall show rule name="$ruleName" 2>$null
    return [bool]($out | Select-String -Pattern "Rule Name" -Quiet)
}

if (Test-Rule) {
    Write-Host "  [OK] Cong $port da duoc mo truoc do (rule: $ruleName)." -ForegroundColor Green
    exit 0
}

Write-Host "  Can mo cong $port cho dien thoai trong WiFi." -ForegroundColor Yellow
Write-Host "  Se hien hop thoai UAC - bam Yes de cho phep." -ForegroundColor Yellow

$argLine = "advfirewall firewall add rule name=`"$ruleName`" dir=in action=allow " +
           "protocol=TCP localport=$port profile=any"

try {
    Start-Process -FilePath "netsh" -ArgumentList $argLine -Verb RunAs -Wait
} catch {
    Write-Host "  [!] Khong mo duoc bang UAC: $_" -ForegroundColor Red
    Write-Host "      Hay mo PowerShell bang quyen Administrator roi chay:" -ForegroundColor Red
    Write-Host "      netsh advfirewall firewall add rule name=`"$ruleName`" dir=in action=allow protocol=TCP localport=$port profile=any" -ForegroundColor White
    exit 1
}

Start-Sleep -Seconds 1
if (Test-Rule) {
    Write-Host "  [OK] Da mo cong $port cho MOI profile va MOI IP nguon." -ForegroundColor Green
    exit 0
} else {
    Write-Host "  [!] Chua thay rule sau khi chay. Thu lai hoac chay tay lenh tren." -ForegroundColor Red
    exit 1
}
