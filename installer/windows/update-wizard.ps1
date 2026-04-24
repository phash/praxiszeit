# PraxisZeit Update-Wizard
# GUI-Wizard fuer Update einer bestehenden Installation auf eine neuere Version.
# Aufruf via update-wizard.bat (erzwingt Admin + PowerShell-STA).
#
# Flow:
#   1. Welcome: Install erkennen, Versionen anzeigen
#   2. Progress:
#      a) ACL-Fix auf .db-credentials (F-037, idempotent)
#      b) Datenbank-Backup (Service laeuft noch)
#      c) Service stoppen
#      d) Dateien aktualisieren (robocopy mit Excludes)
#      e) Service starten
#      f) Scheduled Task "PraxisZeit-Backup" registrieren/aktualisieren
#   3. Done: Erfolg oder Fehler + Log-Hinweis

[CmdletBinding()]
param(
    [string]$InstallDir = "",
    [switch]$DryRun
)

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

$ErrorActionPreference = 'Stop'
$WizardDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# ------------------------------------------------------------
# Hilfsfunktionen
# ------------------------------------------------------------

function Find-InstallDir {
    $candidates = @(
        'C:\PraxisZeit',
        'C:\praxiszeit',
        'D:\PraxisZeit',
        "$env:ProgramFiles\PraxisZeit"
    )
    foreach ($c in $candidates) {
        if (Test-Path (Join-Path $c 'praxiszeit-server.py')) {
            return (Resolve-Path $c).Path
        }
    }
    return $null
}

function Get-AppVersion([string]$dir) {
    if (-not $dir -or -not (Test-Path $dir)) { return 'unbekannt' }
    $candidates = @(
        (Join-Path $dir 'app\backend\app\core\updater.py'),
        (Join-Path $dir 'backend\app\core\updater.py')
    )
    foreach ($p in $candidates) {
        if (Test-Path $p) {
            $content = Get-Content -LiteralPath $p -Raw
            if ($content -match 'APP_VERSION\s*=\s*"([^"]+)"') {
                return $Matches[1]
            }
        }
    }
    return 'unbekannt'
}

function Show-Error([string]$msg) {
    [System.Windows.Forms.MessageBox]::Show(
        $msg,
        'PraxisZeit Update-Wizard',
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Error
    ) | Out-Null
}

# ------------------------------------------------------------
# Install-Verzeichnis ermitteln
# ------------------------------------------------------------

if (-not $InstallDir) {
    $InstallDir = Find-InstallDir
}

if (-not $InstallDir -or -not (Test-Path (Join-Path $InstallDir 'praxiszeit-server.py'))) {
    $fbd = New-Object System.Windows.Forms.FolderBrowserDialog
    $fbd.Description = 'PraxisZeit Installationsverzeichnis auswaehlen (muss praxiszeit-server.py enthalten)'
    $fbd.ShowNewFolderButton = $false
    if ($fbd.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
        $InstallDir = $fbd.SelectedPath
    }
    if (-not $InstallDir -or -not (Test-Path (Join-Path $InstallDir 'praxiszeit-server.py'))) {
        Show-Error "Kein gueltiges PraxisZeit-Verzeichnis ausgewaehlt.`n`nErwartet: praxiszeit-server.py im Verzeichnis."
        exit 1
    }
}

$InstallDir = (Resolve-Path $InstallDir).Path.TrimEnd('\')
$WizardDirResolved = (Resolve-Path $WizardDir).Path.TrimEnd('\')

if ($InstallDir -ieq $WizardDirResolved) {
    Show-Error "Der Update-Wizard darf nicht aus dem Installationsverzeichnis ausgefuehrt werden.`n`nBitte das Update-ZIP in einen TEMP-Ordner extrahieren (z.B. C:\Temp\praxiszeit-update\) und den Wizard von dort starten."
    exit 1
}

$CurrentVersion = Get-AppVersion $InstallDir
$NewVersion = Get-AppVersion $WizardDirResolved

# ------------------------------------------------------------
# Form
# ------------------------------------------------------------

$form = New-Object System.Windows.Forms.Form
$form.Text = 'PraxisZeit Update-Wizard'
# ClientSize statt Size: legt die nutzbare Innenflaeche fest,
# damit die Button-Koordinaten unten nicht von Rahmen/DPI abhaengen
# (F-058: Buttons wurden rechts abgeschnitten, weil Size die
# Aussenmasse inkl. Rahmen beschreibt).
$form.ClientSize = New-Object System.Drawing.Size(720, 560)
$form.StartPosition = 'CenterScreen'
$form.FormBorderStyle = 'FixedDialog'
$form.MaximizeBox = $false
$form.MinimizeBox = $true
$form.Icon = [System.Drawing.SystemIcons]::Application

# Header
$header = New-Object System.Windows.Forms.Panel
$header.Dock = 'Top'
$header.Height = 70
$header.BackColor = [System.Drawing.Color]::FromArgb(20, 60, 120)
$form.Controls.Add($header)

$lblTitle = New-Object System.Windows.Forms.Label
$lblTitle.Text = 'PraxisZeit Update-Wizard'
$lblTitle.ForeColor = [System.Drawing.Color]::White
$lblTitle.Font = New-Object System.Drawing.Font('Segoe UI', 16, [System.Drawing.FontStyle]::Bold)
$lblTitle.Location = New-Object System.Drawing.Point(20, 10)
$lblTitle.AutoSize = $true
$header.Controls.Add($lblTitle)

$lblSubtitle = New-Object System.Windows.Forms.Label
$lblSubtitle.Text = 'Aktualisierung einer bestehenden Installation'
$lblSubtitle.ForeColor = [System.Drawing.Color]::LightGray
$lblSubtitle.Font = New-Object System.Drawing.Font('Segoe UI', 9)
$lblSubtitle.Location = New-Object System.Drawing.Point(22, 42)
$lblSubtitle.AutoSize = $true
$header.Controls.Add($lblSubtitle)

# Footer mit Buttons
$footer = New-Object System.Windows.Forms.Panel
$footer.Dock = 'Bottom'
$footer.Height = 50
$footer.BackColor = [System.Drawing.Color]::FromArgb(240, 240, 240)
$form.Controls.Add($footer)

$btnNext = New-Object System.Windows.Forms.Button
$btnNext.Text = 'Update starten'
$btnNext.Size = New-Object System.Drawing.Size(140, 32)
# Rechts-buendig zum Footer: Footer-Width - Button-Width - Rand(15)
$btnNext.Location = New-Object System.Drawing.Point(($form.ClientSize.Width - 140 - 15), 9)
$btnNext.Anchor = [System.Windows.Forms.AnchorStyles]::Bottom -bor [System.Windows.Forms.AnchorStyles]::Right
$btnNext.Font = New-Object System.Drawing.Font('Segoe UI', 9, [System.Drawing.FontStyle]::Bold)
$footer.Controls.Add($btnNext)

$btnCancel = New-Object System.Windows.Forms.Button
$btnCancel.Text = 'Abbrechen'
$btnCancel.Size = New-Object System.Drawing.Size(110, 32)
# Links neben btnNext: Next.X - Cancel.Width - Abstand(10)
$btnCancel.Location = New-Object System.Drawing.Point(($btnNext.Location.X - 110 - 10), 9)
$btnCancel.Anchor = [System.Windows.Forms.AnchorStyles]::Bottom -bor [System.Windows.Forms.AnchorStyles]::Right
$btnCancel.Font = New-Object System.Drawing.Font('Segoe UI', 9)
$footer.Controls.Add($btnCancel)

# Body (wird von Show-*-Page gefuellt)
$body = New-Object System.Windows.Forms.Panel
$body.Dock = 'Fill'
$body.BackColor = [System.Drawing.Color]::White
$form.Controls.Add($body)
$body.BringToFront()

# ------------------------------------------------------------
# Pages
# ------------------------------------------------------------

$script:stepLabels = @{}
$script:logBox = $null
$script:progressBar = $null
$script:currentPage = 'welcome'

function Show-WelcomePage {
    $script:currentPage = 'welcome'
    $body.Controls.Clear()

    $lbl1 = New-Object System.Windows.Forms.Label
    $lbl1.Text = 'Willkommen'
    $lbl1.Font = New-Object System.Drawing.Font('Segoe UI', 14, [System.Drawing.FontStyle]::Bold)
    $lbl1.Location = New-Object System.Drawing.Point(20, 20)
    $lbl1.AutoSize = $true
    $body.Controls.Add($lbl1)

    $lbl2 = New-Object System.Windows.Forms.Label
    $lbl2.Text = "Dieser Assistent aktualisiert PraxisZeit auf eine neuere Version.`r`nFolgende Schritte werden ausgefuehrt:`r`n`r`n" +
        "   1. ACL-Fix fuer .db-credentials (F-037)`r`n" +
        "   2. Datenbank-Backup (Service laeuft noch)`r`n" +
        "   3. PraxisZeit-Service stoppen`r`n" +
        "   4. Neue Dateien ueber die bestehenden kopieren`r`n" +
        "   5. PraxisZeit-Service starten`r`n" +
        "   6. Taegliche Backup-Task registrieren / aktualisieren"
    $lbl2.Font = New-Object System.Drawing.Font('Segoe UI', 10)
    $lbl2.Location = New-Object System.Drawing.Point(20, 55)
    $lbl2.Size = New-Object System.Drawing.Size(660, 170)
    $body.Controls.Add($lbl2)

    $grp = New-Object System.Windows.Forms.GroupBox
    $grp.Text = ' Erkannte Umgebung '
    $grp.Location = New-Object System.Drawing.Point(20, 235)
    $grp.Size = New-Object System.Drawing.Size(660, 145)
    $grp.Font = New-Object System.Drawing.Font('Segoe UI', 9, [System.Drawing.FontStyle]::Bold)
    $body.Controls.Add($grp)

    $info = @(
        @{ Key = 'Installationsverzeichnis:'; Val = $InstallDir },
        @{ Key = 'Aktuelle Version:';         Val = $CurrentVersion },
        @{ Key = 'Neue Version:';             Val = $NewVersion },
        @{ Key = 'Update-Quelle:';            Val = $WizardDirResolved }
    )
    $y = 25
    foreach ($pair in $info) {
        $k = New-Object System.Windows.Forms.Label
        $k.Text = $pair.Key
        $k.Font = New-Object System.Drawing.Font('Segoe UI', 9)
        $k.Location = New-Object System.Drawing.Point(15, $y)
        $k.Size = New-Object System.Drawing.Size(170, 20)
        $grp.Controls.Add($k)

        $v = New-Object System.Windows.Forms.Label
        $v.Text = $pair.Val
        $v.Font = New-Object System.Drawing.Font('Consolas', 9)
        $v.Location = New-Object System.Drawing.Point(190, $y)
        $v.Size = New-Object System.Drawing.Size(460, 20)
        $grp.Controls.Add($v)
        $y += 26
    }

    # Warn-Label wenn Versionen identisch
    if ($CurrentVersion -eq $NewVersion -and $CurrentVersion -ne 'unbekannt') {
        $warn = New-Object System.Windows.Forms.Label
        $warn.Text = "Hinweis: Installierte Version und Update-Version sind identisch ($CurrentVersion). Das Update kann trotzdem ausgefuehrt werden."
        $warn.ForeColor = [System.Drawing.Color]::DarkOrange
        $warn.Font = New-Object System.Drawing.Font('Segoe UI', 9, [System.Drawing.FontStyle]::Italic)
        $warn.Location = New-Object System.Drawing.Point(15, ($y + 4))
        $warn.Size = New-Object System.Drawing.Size(630, 20)
        $grp.Controls.Add($warn)
    }

    $btnNext.Text = 'Update starten'
    $btnNext.Enabled = $true
    $btnCancel.Enabled = $true
}

function Show-ProgressPage {
    $script:currentPage = 'progress'
    $body.Controls.Clear()

    $lbl1 = New-Object System.Windows.Forms.Label
    $lbl1.Text = 'Update-Fortschritt'
    $lbl1.Font = New-Object System.Drawing.Font('Segoe UI', 14, [System.Drawing.FontStyle]::Bold)
    $lbl1.Location = New-Object System.Drawing.Point(20, 15)
    $lbl1.AutoSize = $true
    $body.Controls.Add($lbl1)

    $steps = @(
        @{ Id='acl';    Text='1. ACL-Fix fuer .db-credentials' },
        @{ Id='backup'; Text='2. Datenbank-Backup erstellen' },
        @{ Id='stop';   Text='3. PraxisZeit-Service stoppen' },
        @{ Id='copy';   Text='4. Dateien aktualisieren' },
        @{ Id='pip';    Text='5. Python-Dependencies pruefen' },
        @{ Id='start';  Text='6. Service starten' },
        @{ Id='task';   Text='7. Scheduled Task registrieren' }
    )
    $script:stepLabels = @{}
    $y = 50
    foreach ($step in $steps) {
        $l = New-Object System.Windows.Forms.Label
        $l.Text = "   -  $($step.Text)"
        $l.Font = New-Object System.Drawing.Font('Segoe UI', 10)
        $l.Location = New-Object System.Drawing.Point(20, $y)
        $l.Size = New-Object System.Drawing.Size(660, 22)
        $l.ForeColor = [System.Drawing.Color]::DimGray
        $body.Controls.Add($l)
        $script:stepLabels[$step.Id] = $l
        $y += 24
    }

    $y += 8
    $script:progressBar = New-Object System.Windows.Forms.ProgressBar
    $script:progressBar.Location = New-Object System.Drawing.Point(20, $y)
    $script:progressBar.Size = New-Object System.Drawing.Size(660, 18)
    $script:progressBar.Minimum = 0
    $script:progressBar.Maximum = 100
    $body.Controls.Add($script:progressBar)

    $y += 26
    $lblLog = New-Object System.Windows.Forms.Label
    $lblLog.Text = 'Protokoll:'
    $lblLog.Location = New-Object System.Drawing.Point(20, $y)
    $lblLog.AutoSize = $true
    $lblLog.Font = New-Object System.Drawing.Font('Segoe UI', 9)
    $body.Controls.Add($lblLog)

    $y += 20
    $script:logBox = New-Object System.Windows.Forms.TextBox
    $script:logBox.Multiline = $true
    $script:logBox.ReadOnly = $true
    $script:logBox.ScrollBars = 'Vertical'
    $script:logBox.Font = New-Object System.Drawing.Font('Consolas', 8)
    $script:logBox.BackColor = [System.Drawing.Color]::FromArgb(250, 250, 250)
    $script:logBox.Location = New-Object System.Drawing.Point(20, $y)
    $script:logBox.Size = New-Object System.Drawing.Size(660, 160)
    $body.Controls.Add($script:logBox)

    $btnNext.Text = 'Bitte warten...'
    $btnNext.Enabled = $false
    $btnCancel.Enabled = $false
}

function Write-Log([string]$msg) {
    if ($script:logBox) {
        $line = '[{0}] {1}{2}' -f (Get-Date -Format 'HH:mm:ss'), $msg, "`r`n"
        $script:logBox.AppendText($line)
        [System.Windows.Forms.Application]::DoEvents()
    }
}

function Set-StepStatus([string]$id, [string]$status) {
    $lbl = $script:stepLabels[$id]
    if (-not $lbl) { return }
    $txt = $lbl.Text.Substring(7)
    $marker = switch ($status) {
        'running' { '>>' }
        'ok'      { '[OK]' }
        'fail'    { '[!!]' }
        'warn'    { '[??]' }
        default   { '  ' }
    }
    $color = switch ($status) {
        'running' { [System.Drawing.Color]::Blue }
        'ok'      { [System.Drawing.Color]::ForestGreen }
        'fail'    { [System.Drawing.Color]::Firebrick }
        'warn'    { [System.Drawing.Color]::DarkOrange }
        default   { [System.Drawing.Color]::DimGray }
    }
    $lbl.Text = "  $marker $txt"
    $lbl.ForeColor = $color
    [System.Windows.Forms.Application]::DoEvents()
}

function Update-Progress([int]$percent) {
    $script:progressBar.Value = [Math]::Min(100, [Math]::Max(0, $percent))
    [System.Windows.Forms.Application]::DoEvents()
}

# ------------------------------------------------------------
# Update-Schritte
# ------------------------------------------------------------

function Step-ACLFix {
    Set-StepStatus 'acl' 'running'
    Write-Log 'Setze Administrator-Leserechte auf .db-credentials (F-037)...'
    $credsFile = Join-Path $InstallDir 'config\.db-credentials'
    if (-not (Test-Path $credsFile)) {
        Write-Log 'WARNUNG: .db-credentials nicht vorhanden (Erstinstallation?). Schritt uebersprungen.'
        Set-StepStatus 'acl' 'warn'
        return $true
    }
    if ($DryRun) { Start-Sleep -Seconds 1; Set-StepStatus 'acl' 'ok'; return $true }
    try {
        # SID *S-1-5-32-544 = BUILTIN\Administrators (locale-unabhaengig)
        $out = & icacls.exe $credsFile /grant '*S-1-5-32-544:(R)' 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Log 'Administrator-Lesezugriff gewaehrt'
            Set-StepStatus 'acl' 'ok'
            return $true
        }
        Write-Log "WARNUNG: icacls-Exit $LASTEXITCODE - $out"
        Set-StepStatus 'acl' 'warn'
        return $true
    } catch {
        Write-Log "FEHLER bei icacls: $_"
        Set-StepStatus 'acl' 'fail'
        return $false
    }
}

function Step-Backup {
    Set-StepStatus 'backup' 'running'
    Write-Log 'Starte Datenbank-Backup (Service laeuft noch)...'
    if ($DryRun) { Start-Sleep -Seconds 2; Set-StepStatus 'backup' 'ok'; return $true }

    $python = Join-Path $InstallDir 'bin\python\python.exe'
    $server = Join-Path $InstallDir 'praxiszeit-server.py'
    if (-not (Test-Path $python)) {
        Write-Log "WARNUNG: Python nicht gefunden ($python) - Backup uebersprungen"
        Set-StepStatus 'backup' 'warn'
        return $true
    }
    if (-not (Test-Path $server)) {
        Write-Log "WARNUNG: praxiszeit-server.py nicht gefunden - Backup uebersprungen"
        Set-StepStatus 'backup' 'warn'
        return $true
    }
    try {
        $env:PYTHONUTF8 = '1'
        # PowerShell 5.1 / .NET Framework hat KEIN ProcessStartInfo.ArgumentList
        # (kam erst mit .NET Core 2.1). Wir bauen den Argument-String selbst und
        # quoten den server-Pfad, falls er Spaces enthaelt.
        $quotedServer = if ($server -match '\s') { "`"$server`"" } else { $server }
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = $python
        $psi.Arguments = "$quotedServer backup"
        $psi.WorkingDirectory = $InstallDir
        $psi.UseShellExecute = $false
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError = $true
        $psi.CreateNoWindow = $true
        $proc = [System.Diagnostics.Process]::Start($psi)
        $stdout = $proc.StandardOutput.ReadToEnd()
        $stderr = $proc.StandardError.ReadToEnd()
        $proc.WaitForExit()
        $rc = $proc.ExitCode
        foreach ($line in ($stdout -split "`r?`n")) {
            if ($line.Trim()) { Write-Log "  $line" }
        }
        if ($rc -eq 0) {
            Write-Log 'Backup erfolgreich'
            Set-StepStatus 'backup' 'ok'
            return $true
        }
        Write-Log "WARNUNG: Backup-Exit-Code $rc"
        foreach ($line in ($stderr -split "`r?`n")) {
            if ($line.Trim()) { Write-Log "  $line" }
        }
        Set-StepStatus 'backup' 'warn'
        return $true  # Nicht-kritisch, Update geht weiter
    } catch {
        Write-Log "FEHLER beim Backup: $_"
        Set-StepStatus 'backup' 'warn'
        return $true
    }
}

function Step-PipInstall {
    Set-StepStatus 'pip' 'running'
    Write-Log 'Installiere/aktualisiere Python-Dependencies (idempotent)...'
    if ($DryRun) { Start-Sleep -Seconds 1; Set-StepStatus 'pip' 'ok'; return $true }

    $python = Join-Path $InstallDir 'bin\python\python.exe'
    $req = Join-Path $InstallDir 'app\backend\requirements.txt'
    if (-not (Test-Path $python)) {
        Write-Log "WARNUNG: Python nicht gefunden - pip install uebersprungen"
        Set-StepStatus 'pip' 'warn'
        return $true
    }
    if (-not (Test-Path $req)) {
        Write-Log "WARNUNG: requirements.txt nicht gefunden - pip install uebersprungen"
        Set-StepStatus 'pip' 'warn'
        return $true
    }
    try {
        $env:PYTHONUTF8 = '1'

        # F-056 (1.3.6): pip selbst vorher bootstrappen. Robocopy merged
        # bin/python/Lib/site-packages/ ohne Purge — Resultat beim Kunden
        # war ein Mix aus alten + neuen pip._vendor.resolvelib-Files, der
        # mit `ImportError: cannot import name 'RequirementInformation'
        # from pip._vendor.resolvelib.structs` gecrasht ist. get-pip.py
        # --force-reinstall baut pip sauber neu, damit das egal ist.
        $getPip = Join-Path $InstallDir 'bin\python\get-pip.py'
        if (Test-Path $getPip) {
            Write-Log 'Bootstrap pip (get-pip.py --force-reinstall)...'
            $quotedGetPip = if ($getPip -match '\s') { "`"$getPip`"" } else { $getPip }
            $psiBoot = New-Object System.Diagnostics.ProcessStartInfo
            $psiBoot.FileName = $python
            $psiBoot.Arguments = "$quotedGetPip --force-reinstall --no-warn-script-location --quiet"
            $psiBoot.WorkingDirectory = $InstallDir
            $psiBoot.UseShellExecute = $false
            $psiBoot.RedirectStandardOutput = $true
            $psiBoot.RedirectStandardError = $true
            $psiBoot.CreateNoWindow = $true
            $procBoot = [System.Diagnostics.Process]::Start($psiBoot)
            $bootStderr = $procBoot.StandardError.ReadToEnd()
            $procBoot.WaitForExit()
            if ($procBoot.ExitCode -ne 0) {
                Write-Log "WARNUNG: pip-Bootstrap exit=$($procBoot.ExitCode)"
                foreach ($line in ($bootStderr -split "`r?`n")) {
                    if ($line.Trim()) { Write-Log "  $line" }
                }
            } else {
                Write-Log 'pip neu installiert'
            }
        } else {
            Write-Log 'WARNUNG: get-pip.py nicht gefunden - pip-Bootstrap uebersprungen'
        }

        $quotedReq = if ($req -match '\s') { "`"$req`"" } else { $req }
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = $python
        $psi.Arguments = "-m pip install --quiet -r $quotedReq"
        $psi.WorkingDirectory = $InstallDir
        $psi.UseShellExecute = $false
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError = $true
        $psi.CreateNoWindow = $true
        $proc = [System.Diagnostics.Process]::Start($psi)
        $stdout = $proc.StandardOutput.ReadToEnd()
        $stderr = $proc.StandardError.ReadToEnd()
        $proc.WaitForExit()
        $rc = $proc.ExitCode
        if ($rc -eq 0) {
            Write-Log 'Python-Dependencies aktuell'
            Set-StepStatus 'pip' 'ok'
            return $true
        }
        Write-Log "FEHLER: pip install exit=$rc"
        foreach ($line in ($stderr -split "`r?`n")) {
            if ($line.Trim()) { Write-Log "  $line" }
        }
        Set-StepStatus 'pip' 'fail'
        return $false
    } catch {
        Write-Log "FEHLER bei pip install: $_"
        Set-StepStatus 'pip' 'fail'
        return $false
    }
}

function Step-StopService {
    Set-StepStatus 'stop' 'running'
    Write-Log 'Stoppe PraxisZeit-Service...'
    if ($DryRun) { Start-Sleep -Seconds 1; Set-StepStatus 'stop' 'ok'; return $true }
    try {
        $svc = Get-Service -Name 'PraxisZeit' -ErrorAction SilentlyContinue
        if (-not $svc) {
            Write-Log "WARNUNG: Service 'PraxisZeit' nicht gefunden"
            Set-StepStatus 'stop' 'warn'
            return $true
        }
        if ($svc.Status -eq 'Stopped') {
            Write-Log 'Service war bereits gestoppt'
        } else {
            Stop-Service -Name 'PraxisZeit' -Force -ErrorAction Stop
            $svc.WaitForStatus('Stopped', (New-TimeSpan -Seconds 90))
            Write-Log 'Service gestoppt'
        }
        Set-StepStatus 'stop' 'ok'
        return $true
    } catch {
        Write-Log "FEHLER beim Stoppen: $_"
        Set-StepStatus 'stop' 'fail'
        return $false
    }
}

function Step-CopyFiles {
    Set-StepStatus 'copy' 'running'
    Write-Log 'Kopiere neue Dateien (robocopy mit Excludes)...'
    if ($DryRun) { Start-Sleep -Seconds 2; Set-StepStatus 'copy' 'ok'; return $true }
    try {
        $rcArgs = @(
            $WizardDirResolved,
            $InstallDir,
            '/E',
            '/NFL', '/NDL', '/NJH', '/NJS', '/NC', '/NS',
            '/R:2', '/W:2',
            '/XD', 'data', 'logs', 'ssl',
            '/XF', 'praxiszeit.conf', '.db-credentials', '.secret-key', 'license.key'
        )
        Write-Log "  robocopy $WizardDirResolved -> $InstallDir"
        $out = & robocopy.exe @rcArgs 2>&1
        $rc = $LASTEXITCODE
        # Robocopy: 0-7 = success variants, 8+ = failure
        if ($rc -lt 8) {
            Write-Log "Dateien aktualisiert (robocopy exit=$rc)"
            Set-StepStatus 'copy' 'ok'
            return $true
        }
        Write-Log "FEHLER: robocopy exit=$rc"
        foreach ($line in $out) { Write-Log "  $line" }
        Set-StepStatus 'copy' 'fail'
        return $false
    } catch {
        Write-Log "FEHLER beim Kopieren: $_"
        Set-StepStatus 'copy' 'fail'
        return $false
    }
}

function Step-StartService {
    Set-StepStatus 'start' 'running'
    Write-Log 'Starte PraxisZeit-Service...'
    if ($DryRun) { Start-Sleep -Seconds 1; Set-StepStatus 'start' 'ok'; return $true }
    try {
        Start-Service -Name 'PraxisZeit' -ErrorAction Stop
        $svc = Get-Service -Name 'PraxisZeit'
        $svc.WaitForStatus('Running', (New-TimeSpan -Seconds 120))
        Write-Log 'Service laeuft (Migrationen werden beim Start ausgefuehrt)'
        Set-StepStatus 'start' 'ok'
        return $true
    } catch {
        Write-Log "FEHLER beim Starten: $_"
        Write-Log 'Pruefe logs\service-stderr.log und logs\praxiszeit.log im Install-Verzeichnis.'
        Set-StepStatus 'start' 'fail'
        return $false
    }
}

function Step-ScheduledTask {
    Set-StepStatus 'task' 'running'
    Write-Log 'Registriere Scheduled Task PraxisZeit-Backup (taeglich 03:00 als SYSTEM)...'
    if ($DryRun) { Start-Sleep -Seconds 1; Set-StepStatus 'task' 'ok'; return $true }
    $backupBat = Join-Path $InstallDir 'backup.bat'
    if (-not (Test-Path $backupBat)) {
        Write-Log "WARNUNG: backup.bat nicht gefunden unter $backupBat"
        Set-StepStatus 'task' 'warn'
        return $true
    }
    try {
        # schtasks via cmd /c fuer verlaessliches Quoting von /tr
        $trValue = '"\"' + $backupBat + '\""'
        $cmdLine = "schtasks /create /tn `"PraxisZeit-Backup`" /tr $trValue /sc daily /st 03:00 /ru SYSTEM /f"
        $out = cmd /c $cmdLine 2>&1
        $rc = $LASTEXITCODE
        foreach ($line in ($out -split "`r?`n")) {
            if ($line.Trim()) { Write-Log "  $line" }
        }
        if ($rc -eq 0) {
            Write-Log 'Scheduled Task aktiv'
            Set-StepStatus 'task' 'ok'
            return $true
        }
        Write-Log "WARNUNG: schtasks exit=$rc"
        Set-StepStatus 'task' 'warn'
        return $true
    } catch {
        Write-Log "FEHLER bei Scheduled Task: $_"
        Set-StepStatus 'task' 'warn'
        return $true
    }
}

function Invoke-Update {
    Write-Log "Update: $CurrentVersion -> $NewVersion"
    Write-Log "Install: $InstallDir"
    Write-Log "Quelle:  $WizardDirResolved"
    Write-Log ''

    $ok1 = Step-ACLFix;        Update-Progress 8
    $ok2 = Step-Backup;        Update-Progress 25
    $ok3 = Step-StopService;   Update-Progress 40
    if (-not $ok3) { return $false }
    $ok4 = Step-CopyFiles;     Update-Progress 60
    if (-not $ok4) {
        Write-Log ''
        Write-Log 'Versuche Service trotzdem wieder zu starten...'
        Step-StartService | Out-Null
        return $false
    }
    $ok5 = Step-PipInstall;    Update-Progress 78
    if (-not $ok5) {
        Write-Log ''
        Write-Log 'pip install fehlgeschlagen - Service wird nicht starten koennen.'
        Write-Log 'Manuell nachholen mit:'
        Write-Log "  $InstallDir\bin\python\python.exe -m pip install -r $InstallDir\app\backend\requirements.txt"
        return $false
    }
    $ok6 = Step-StartService;  Update-Progress 92
    $ok7 = Step-ScheduledTask; Update-Progress 100

    return ($ok6 -and $ok7)
}

function Show-Done([bool]$success) {
    $script:currentPage = 'done'
    Write-Log ''
    Write-Log '=================================================='
    if ($success) {
        Write-Log "Update auf Version $NewVersion erfolgreich abgeschlossen."
    } else {
        Write-Log 'Update mit FEHLERN beendet. Siehe Protokoll oben.'
        Write-Log "Backup liegt unter: $InstallDir\data\backups"
    }
    Write-Log '=================================================='

    $btnNext.Text = 'Schliessen'
    $btnNext.Enabled = $true
    $btnCancel.Enabled = $false
}

# ------------------------------------------------------------
# Buttons
# ------------------------------------------------------------

$btnCancel.Add_Click({
    if ($script:currentPage -eq 'welcome') {
        $form.Close()
    }
})

$btnNext.Add_Click({
    switch ($script:currentPage) {
        'welcome'  {
            Show-ProgressPage
            $success = Invoke-Update
            Show-Done $success
        }
        'done'     { $form.Close() }
    }
})

Show-WelcomePage
[void]$form.ShowDialog()
