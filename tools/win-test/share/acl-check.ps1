param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Paths)

# Test-Harness (NICHT Teil des Pakets): prueft, ob eine Datei noch fuer
# breite Prinzipale zugaenglich ist. Gibt sowohl die woertliche icacls-
# Ausgabe als auch eine SID-basierte (also sprachunabhaengige) Bewertung aus.

$broad = @{
    'S-1-5-32-545' = 'BUILTIN\Users'
    'S-1-5-11'     = 'NT AUTHORITY\Authenticated Users'
    'S-1-1-0'      = 'Everyone'
    'S-1-5-32-546' = 'BUILTIN\Guests'
    'S-1-5-32-547' = 'BUILTIN\Power Users'
    'S-1-5-4'      = 'NT AUTHORITY\INTERACTIVE'
}

foreach ($p in $Paths) {
    Write-Output "----- $p -----"
    if (-not (Test-Path -LiteralPath $p)) {
        Write-Output 'VERDICT: MISSING (Datei existiert nicht)'
        continue
    }
    Write-Output 'ICACLS:'
    & icacls.exe $p 2>&1 | ForEach-Object { Write-Output $_ }

    $acl = Get-Acl -LiteralPath $p
    $bad = @()
    $lines = @()
    foreach ($ace in $acl.Access) {
        $sid = try {
            $ace.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value
        } catch {
            $ace.IdentityReference.Value
        }
        $lines += "$sid rights=$($ace.FileSystemRights) type=$($ace.AccessControlType) inherited=$($ace.IsInherited)"
        if ($broad.ContainsKey($sid) -and $ace.AccessControlType -eq 'Allow') {
            $bad += "$sid ($($broad[$sid]))"
        }
    }
    Write-Output 'ACEs (SID-basiert):'
    foreach ($l in $lines) { Write-Output "  $l" }
    Write-Output "OWNER: $($acl.Owner)"
    if ($bad.Count -gt 0) {
        Write-Output ('VERDICT: FAIL - breite Prinzipale berechtigt: ' + ($bad -join ', '))
    } else {
        Write-Output 'VERDICT: OK - kein Users / Authenticated Users / Everyone'
    }
}
