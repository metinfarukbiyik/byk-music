# Windows dosyalarını Authenticode ile imzalar.
# Sertifika GitHub Secrets üzerinden verilir:
#   WINDOWS_CERT_PFX       -> .pfx dosyasının base64 hali
#   WINDOWS_CERT_PASSWORD  -> .pfx parolası
# Sertifika tanımlı değilse imzalama atlanır ve derleme imzasız devam eder.
param([Parameter(Mandatory = $true, ValueFromRemainingArguments = $true)][string[]]$Files)

if (-not $env:CERT_PFX) {
    Write-Host "İmza sertifikası tanımlı değil, imzalama atlandı: $Files"
    exit 0
}
$pfx = Join-Path $env:RUNNER_TEMP "cert.pfx"
[IO.File]::WriteAllBytes($pfx, [Convert]::FromBase64String($env:CERT_PFX))
$signtool = Get-ChildItem "C:\Program Files (x86)\Windows Kits\10\bin\*\x64\signtool.exe" |
    Sort-Object FullName | Select-Object -Last 1
& $signtool.FullName sign /f $pfx /p $env:CERT_PASSWORD /fd SHA256 `
    /tr http://timestamp.digicert.com /td SHA256 /d "BYK Music" /du "https://biyik.dev" $Files
$code = $LASTEXITCODE
Remove-Item $pfx -Force
if ($code -ne 0) { throw "İmzalama başarısız ($code)" }
