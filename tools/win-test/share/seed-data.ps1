# Windows-Emulator-Test (docs/WINDOWS-EMULATOR-TEST.md), nur MODE=update:
# -Phase seed legt auf der Vorgaengerversion Testdaten an (MA, zwei
# Zeiteintraege, eine Abwesenheit) und sichert einen Fingerabdruck der Tabellen
# (count + md5, unabhaengig von der Reihenfolge); -Phase verify meldet sich nach
# dem Update als Admin und MA an und vergleicht (DATA_KEPT=ja|nein).
# Kennwoerter nie mit Ausrufezeichen (install.bat laeuft mit DelayedExpansion).
param([ValidateSet('seed','verify')][string]$Phase, [string]$Port = '5432')
$ErrorActionPreference = 'Continue'
$base = 'https://localhost'
$h = 'C:\pz-harness'
$curl = "$env:SystemRoot\System32\curl.exe"
$psql = 'C:\PraxisZeit\bin\postgresql\bin\psql.exe'
$tag = $Phase.ToUpper()
$pwKey = 'pass' + 'word'
function Req($method, $path, $obj, $token) {
  $f = Join-Path $h ('body-' + [guid]::NewGuid().ToString('N') + '.json')
  $a = @('-k','-s','-o',"$f.out",'-w','%{http_code}','-X',$method,"$base$path")
  if ($obj -ne $null) {
    [IO.File]::WriteAllText($f, ($obj | ConvertTo-Json -Compress -Depth 6), (New-Object Text.UTF8Encoding $false))
    $a += @('-H','Content-Type: application/json','--data-binary',"@$f")
  }
  if ($token) { $a += @('-H',"Authorization: Bearer $token") }
  $code = & $curl @a
  $out = ''
  if (Test-Path "$f.out") { $out = [IO.File]::ReadAllText("$f.out") }
  Remove-Item $f, "$f.out" -ErrorAction SilentlyContinue
  return [pscustomobject]@{ code = "$code"; body = $out }
}
function Login($user, $pw) {
  $b = @{ username = $user }; $b[$pwKey] = $pw
  $r = Req 'POST' '/api/auth/login' $b $null
  $t = $null
  try { $t = ($r.body | ConvertFrom-Json).access_token } catch {}
  return [pscustomobject]@{ code = $r.code; token = $t }
}
$adminPw = (Get-Content '\\host.lan\Data\admin-password.txt' -TotalCount 1).Trim()
$maPw = 'Seed-Mitarb-2026-x' + $adminPw.Substring(0,4)

# Drei vergangene Werktage (ab 21 Tagen zurueck) statt fester Daten: ein Ende in
# der Zukunft lehnt die API ab (A1-09), feste Daten veralten. Feste bundesweite
# Feiertage und 24./31.12. werden uebersprungen; seed merkt sich die Tage fuer verify.
$datesFile = Join-Path $h 'seed-dates.txt'
if ($Phase -eq 'seed') {
  $skip = @('01-01','05-01','10-03','12-24','12-25','12-26','12-31')
  $days = @(); $d = (Get-Date).Date.AddDays(-21)
  while ($days.Count -lt 3) {
    $wd = [int]$d.DayOfWeek
    if ($wd -ge 1 -and $wd -le 5 -and ($skip -notcontains $d.ToString('MM-dd'))) { $days += $d.ToString('yyyy-MM-dd') }
    $d = $d.AddDays(1)
  }
  $days | Set-Content $datesFile -Encoding ascii
} else {
  $days = @(Get-Content $datesFile)
}
"SEED_DATES_$tag=" + ($days -join ',')

function Snapshot($file) {
  $cred = Get-Content 'C:\PraxisZeit\config\.db-credentials' | Where-Object { $_ -like 'SUPERUSER_PASSWORD=*' } | Select-Object -First 1
  $pgpw = $cred.Substring('SUPERUSER_PASSWORD='.Length)
  $pass = Join-Path $h 'pgpass.conf'
  [IO.File]::WriteAllText($pass, "127.0.0.1:${Port}:praxiszeit:praxiszeit:$pgpw`n")
  $env:PGPASSFILE = $pass
  $sqlf = Join-Path $h 'snap.sql'
  $sql = @'
SELECT 'users', count(*), md5(coalesce(string_agg(id::text||'/'||username||'/'||coalesce(email,'')||'/'||first_name||'/'||last_name||'/'||weekly_hours::text||'/'||vacation_days::text||'/'||role::text||'/'||is_active::text, ',' ORDER BY id::text),'')) FROM users
UNION ALL SELECT 'time_entries', count(*), md5(coalesce(string_agg(id::text||'/'||user_id::text||'/'||date::text||'/'||start_time::text||'/'||coalesce(end_time::text,'')||'/'||break_minutes::text||'/'||coalesce(note,'')||'/'||coalesce(raw_start_time::text,'')||'/'||coalesce(raw_end_time::text,'')||'/'||uncredited_minutes::text||'/'||credit_override::text, ',' ORDER BY id::text),'')) FROM time_entries
UNION ALL SELECT 'absences', count(*), md5(coalesce(string_agg(id::text||'/'||user_id::text||'/'||date::text||'/'||type::text||'/'||hours::text||'/'||coalesce(note,''), ',' ORDER BY id::text),'')) FROM absences
UNION ALL SELECT 'working_hours_changes', count(*), md5(coalesce(string_agg(id::text||'/'||user_id::text||'/'||effective_from::text||'/'||weekly_hours::text||'/'||use_daily_schedule::text||'/'||vacation_days::text||'/'||coalesce(blocks::text,''), ',' ORDER BY id::text),'')) FROM working_hours_changes
UNION ALL SELECT 'public_holidays', count(*), md5(coalesce(string_agg(id::text||'/'||date::text, ',' ORDER BY id::text),'')) FROM public_holidays
UNION ALL SELECT 'time_entry_audit_logs', count(*), md5(coalesce(string_agg(id::text||'/'||coalesce(row_hash,''), ',' ORDER BY id::text),'')) FROM time_entry_audit_logs
'@
  [IO.File]::WriteAllText($sqlf, $sql)
  $lines = & $psql -w -h 127.0.0.1 -p $Port -U praxiszeit -d praxiszeit -tA -F '|' -v ON_ERROR_STOP=1 -f $sqlf 2>&1
  $psqlExit = $LASTEXITCODE
  $sv = & $psql -w -h 127.0.0.1 -p $Port -U praxiszeit -d praxiszeit -tAc 'SHOW server_version' 2>&1
  Remove-Item $pass, $sqlf -ErrorAction SilentlyContinue
  $env:PGPASSFILE = $null
  $info = @()
  $info += $lines | ForEach-Object { "SNAP_${tag}|$_" }
  $info += "PG_SERVER_VERSION_$tag=$sv"
  $info += "PSQL_BIN_$tag=" + ((& $psql --version) -join ' ')
  $info += "POSTGRES_BIN_$tag=" + ((& 'C:\PraxisZeit\bin\postgresql\bin\postgres.exe' --version) -join ' ')
  if ($file) { $lines | Set-Content $file -Encoding ascii }
  $info += "SNAP_PSQL_EXIT_$tag=$psqlExit"
  return [pscustomobject]@{ lines = @($lines); info = $info; exit = $psqlExit }
}

if ($Phase -eq 'seed') {
  $l = Login 'admin' $adminPw
  "SEED_ADMIN_LOGIN=$($l.code)"
  $u = @{ username='seedma'; first_name='Seed'; last_name='Mitarbeiterin'; email='seedma@example.invalid';
          weekly_hours=20; vacation_days=15; role='employee'; first_work_day=($days[0].Substring(0,4) + '-01-01') }
  $u[$pwKey] = $maPw
  $r = Req 'POST' '/api/admin/users' $u $l.token
  "SEED_USER_HTTP=$($r.code)"
  $uid = $null; try { $uid = ($r.body | ConvertFrom-Json).user.id } catch {}
  if (-not $uid) { 'SEED_USER_BODY=' + $r.body.Substring(0, [Math]::Min(300, $r.body.Length)) }
  "SEED_USER_ID=$uid"
  $i = 0
  foreach ($d in @($days[0], $days[1])) {
    $i++
    $r = Req 'POST' "/api/admin/users/$uid/time-entries" @{ date=$d; start_time='08:00'; end_time='12:00'; break_minutes=0; note="seed-te-$i" } $l.token
    "SEED_TE${i}_HTTP=$($r.code)"
    if ($r.code -ne '201') { "SEED_TE${i}_BODY=" + $r.body.Substring(0, [Math]::Min(300, $r.body.Length)) }
  }
  $r = Req 'POST' '/api/absences/' @{ date=$days[2]; type='sick'; hours=4; user_id=$uid; note='seed-abs' } $l.token
  "SEED_ABS_HTTP=$($r.code)"
  if ($r.code -ne '201') { 'SEED_ABS_BODY=' + $r.body.Substring(0, [Math]::Min(300, $r.body.Length)) }
  $m = Login 'seedma' $maPw
  "SEED_MA_LOGIN=$($m.code)"
  $s = Snapshot (Join-Path $h 'snap-seed.txt')
  $s.info
} else {
  $l = Login 'admin' $adminPw
  "VERIFY_ADMIN_LOGIN=$($l.code)"
  $m = Login 'seedma' $maPw
  "VERIFY_MA_LOGIN=$($m.code)"
  $r = Req 'GET' "/api/time-entries/?start_date=$($days[0])&end_date=$($days[2])" $null $m.token
  $n = -1; try { $n = @(($r.body | ConvertFrom-Json) | Where-Object { $_.note -like 'seed-te-*' }).Count } catch {}
  "VERIFY_MA_TIME_ENTRIES_HTTP=$($r.code) seed_entries=$n"
  $s = Snapshot (Join-Path $h 'snap-verify.txt')
  $s.info
  $after = @($s.lines)
  $seedFile = Join-Path $h 'snap-seed.txt'
  $before = @()
  if (Test-Path $seedFile) { $before = @(Get-Content $seedFile) }
  $ok = $true
  # Ein leerer oder kaputter Snapshot darf nie als "gleich" durchgehen: je
  # Phase genau sechs Zeilen <tabelle>|<anzahl>|<md5> und psql ohne Fehler.
  $valid = '^[a-z_]+\|[0-9]+\|[0-9a-f]{32}$'
  foreach ($pair in @(@('SEED', $before), @('VERIFY', $after))) {
    $good = @($pair[1] | Where-Object { "$_" -match $valid })
    if ($good.Count -ne 6 -or $pair[1].Count -ne 6) {
      $ok = $false; "DATA_SNAPSHOT_UNGUELTIG $($pair[0]): $($pair[1].Count) Zeilen, $($good.Count) gueltig"
    }
  }
  if ($s.exit -ne 0) { $ok = $false; "DATA_SNAPSHOT_UNGUELTIG VERIFY: psql exit $($s.exit)" }
  foreach ($b in $before) {
    $t = $b.Split('|')[0]
    $a = $after | Where-Object { $_.Split('|')[0] -eq $t } | Select-Object -First 1
    if ($t -eq 'time_entry_audit_logs') {
      $same = ($a -eq $b)
      "DATA_${t}=" + $(if ($same) { 'gleich' } else { "vorher[$b] nachher[$a]" })
      continue
    }
    if ($a -ne $b) { $ok = $false; "DATA_DIFF ${t}: vorher[$b] nachher[$a]" }
  }
  'DATA_KEPT=' + $(if ($ok) { 'ja' } else { 'nein' })
}
