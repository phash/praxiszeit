# Haelt eine Datei des neuen Pakets exklusiv offen, bis der Update-Assistent
# den ersten Kopierfehler gemeldet hat - Nachbau des Windows-Server-Updates
# 2026-11-15 (robocopy FEHLER 32 auf nssm.exe). Gesperrt wird eine Datei, die
# nur im neuen Paket liegt - sonst kopiert robocopy sie nicht. Nur im update-Lauf und nur,
# wenn share\lock-test.txt existiert. Erwartung: der Assistent nennt den
# Sperrer (diesen PowerShell-Prozess), wartet und kopiert im 2. Versuch.
param(
    [string]$Path = 'C:\PZNew\lock-probe.dat',
    [string]$ResultFile = '\\host.lan\Data\install-result.txt',
    [string]$Marker = 'Ursache wird untersucht',
    [int]$TimeoutSeconds = 900
)
$fs = [System.IO.File]::Open($Path, 'Open', 'Read', 'None')
# Gegenprobe: ein zweites Oeffnen muss scheitern, sonst sperrt der Test nichts.
$probe = 'nicht gesperrt'
try { ([System.IO.File]::Open($Path, 'Open', 'Read', 'ReadWrite')).Close() } catch { $probe = 'gesperrt' }
Set-Content -Path 'C:\pz-harness\lock-holder.state' -Value "LOCKED pid=$PID $Path gegenprobe=$probe"
$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$seen = $false
while ((Get-Date) -lt $deadline) {
    try {
        $rs = [System.IO.File]::Open($ResultFile, 'Open', 'Read', 'ReadWrite')
        $sr = New-Object System.IO.StreamReader($rs)
        $text = $sr.ReadToEnd()
        $sr.Close()
        if ($text.Contains($Marker)) { $seen = $true; break }
    } catch { }
    Start-Sleep -Seconds 1
}
# Sperre noch kurz halten: der Assistent fragt gleich nach dem Marker den
# Restart Manager - der soll diesen Prozess als Sperrer sehen.
Start-Sleep -Seconds 6
$fs.Close()
Set-Content -Path 'C:\pz-harness\lock-holder.state' -Value "RELEASED pid=$PID marker_seen=$seen"
