using System.Diagnostics;
using System.Runtime.Versioning;

namespace PraxisZeit.Setup.Core.Services;

public enum RunnerStepStatus
{
    Pending,
    Running,
    Ok,
    Warn,
    Fail,
}

public abstract record RunnerEvent;
public sealed record RunnerStepEvent(string Id, RunnerStepStatus Status) : RunnerEvent;
public sealed record RunnerLogEvent(string Message) : RunnerEvent;
public sealed record RunnerProgressEvent(int Percent) : RunnerEvent;
public sealed record RunnerDoneEvent(bool Success) : RunnerEvent;

/// <summary>
/// Orchestriert die Ausfuehrung der bestehenden, kampferprobten
/// <c>setup.bat</c> / <c>install-service.bat</c> (Fresh-Install) bzw.
/// <c>update-wizard.ps1 -Headless</c> (Update). Die Scripts werden
/// als Subprocess gestartet, stdout/stderr werden zeilenweise an einen
/// <see cref="IProgress{RunnerEvent}"/>-Sink gepusht — der Avalonia-
/// Wizard rendert daraus die Step-Liste, das Live-Log und den
/// Fortschrittsbalken.
///
/// <para>
/// Bewusster Architektur-Entscheid: Wir reimplementieren die
/// 1436+ Zeilen .bat/.ps1-Logik NICHT in C#. Die existierenden Scripts
/// kennen alle Customer-Edge-Cases (cp1252, Junctions, EDB-Aufraeumung,
/// RLS-Kontext, robocopy-Excludes, F-037 ACL-Fix) und werden
/// unveraendert beim Kunden ausgefuehrt — ZERO Regressionsrisiko fuer
/// die Install-Logik.
/// </para>
/// </summary>
[SupportedOSPlatform("windows")]
public sealed class ScriptRunner
{

    /// <summary>
    /// Update-Pfad: spawnt <c>powershell.exe -Headless -InstallDir &lt;existing&gt;
    /// -File &lt;payloadDir&gt;\update-wizard.ps1</c>. Der headless-Mode des
    /// Wizards emittiert <c>[STEP]</c>/<c>[LOG]</c>/<c>[PROGRESS]</c>/<c>[DONE]</c>
    /// auf stdout — wir parsen die Marker und reichen sie als typed
    /// <see cref="RunnerEvent"/>s an den UI-Sink durch.
    /// </summary>
    public async Task<bool> RunUpdateAsync(
        string installDir,
        string payloadDir,
        IProgress<RunnerEvent> sink,
        CancellationToken ct = default)
    {
        var ps1 = Path.Combine(payloadDir, "update-wizard.ps1");
        if (!File.Exists(ps1))
        {
            sink.Report(new RunnerLogEvent($"FEHLER: update-wizard.ps1 nicht gefunden unter {ps1}"));
            sink.Report(new RunnerDoneEvent(false));
            return false;
        }

        var psi = new ProcessStartInfo("powershell.exe")
        {
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true,
            WorkingDirectory = payloadDir,
        };
        psi.ArgumentList.Add("-NoProfile");
        psi.ArgumentList.Add("-NonInteractive");
        psi.ArgumentList.Add("-ExecutionPolicy");
        psi.ArgumentList.Add("Bypass");
        psi.ArgumentList.Add("-File");
        psi.ArgumentList.Add(ps1);
        psi.ArgumentList.Add("-Headless");
        psi.ArgumentList.Add("-InstallDir");
        psi.ArgumentList.Add(installDir);

        var success = await RunAndParseMarkersAsync(psi, sink, ct).ConfigureAwait(false);
        sink.Report(new RunnerDoneEvent(success));
        return success;
    }

    /// <summary>
    /// Fresh-Install-Pfad: kopiert das extrahierte Payload nach
    /// <paramref name="installDir"/> und ruft <c>setup.bat</c>,
    /// <c>install-service.bat</c> und <c>net start PraxisZeit</c> der Reihe
    /// nach auf. Beide .bat erkennen <c>PRAXISZEIT_NONINTERACTIVE=1</c> und
    /// ueberspringen ihre <c>pause</c>-Aufrufe.
    ///
    /// <para>
    /// Optional kann ein <see cref="PraxisZeitConfigValues"/>-Objekt
    /// uebergeben werden — dann wird zwischen Copy und setup.bat eine
    /// fertige <c>config\praxiszeit.conf</c> mit den User-Werten
    /// geschrieben. setup.bat sieht dann das File schon und ueberspringt
    /// das Kopieren der <c>conf.example</c> mit Platzhaltern. Das
    /// Backend-Bootstrap legt beim ersten Service-Start den Admin-User
    /// mit den User-gewaehlten Credentials an, kein
    /// "BITTE_AENDERN"-Crash.
    /// </para>
    /// </summary>
    public async Task<bool> RunFreshInstallAsync(
        string installDir,
        string payloadDir,
        IProgress<RunnerEvent> sink,
        PraxisZeitConfigValues? configValues = null,
        CancellationToken ct = default)
    {
        // ---- Schritt 1: Payload kopieren ----
        sink.Report(new RunnerStepEvent("copy", RunnerStepStatus.Running));
        sink.Report(new RunnerLogEvent($"Kopiere Installationsdateien nach {installDir}..."));
        sink.Report(new RunnerProgressEvent(5));

        try
        {
            Directory.CreateDirectory(installDir);
            CopyDirectoryRecursive(payloadDir, installDir, ct);
            sink.Report(new RunnerStepEvent("copy", RunnerStepStatus.Ok));
            sink.Report(new RunnerProgressEvent(20));
        }
        catch (OperationCanceledException)
        {
            sink.Report(new RunnerStepEvent("copy", RunnerStepStatus.Fail));
            sink.Report(new RunnerLogEvent("Abgebrochen."));
            sink.Report(new RunnerDoneEvent(false));
            return false;
        }
        catch (Exception ex)
        {
            sink.Report(new RunnerStepEvent("copy", RunnerStepStatus.Fail));
            sink.Report(new RunnerLogEvent($"FEHLER beim Kopieren: {ex.Message}"));
            sink.Report(new RunnerDoneEvent(false));
            return false;
        }

        // ---- Schritt 1b: User-Config schreiben (wenn ConfigPage Werte geliefert hat) ----
        if (configValues is not null)
        {
            try
            {
                var confPath = Path.Combine(installDir, "config", "praxiszeit.conf");
                await PraxisZeitConfigWriter.WriteAsync(confPath, configValues, ct).ConfigureAwait(false);
                sink.Report(new RunnerLogEvent($"Konfiguration geschrieben: {confPath}"));
            }
            catch (Exception ex)
            {
                sink.Report(new RunnerStepEvent("copy", RunnerStepStatus.Fail));
                sink.Report(new RunnerLogEvent($"FEHLER beim Schreiben der praxiszeit.conf: {ex.Message}"));
                sink.Report(new RunnerDoneEvent(false));
                return false;
            }
        }

        // ---- Schritt 2: setup.bat (PostgreSQL-Install + pip + Config) ----
        sink.Report(new RunnerStepEvent("setup", RunnerStepStatus.Running));
        sink.Report(new RunnerLogEvent("Starte setup.bat (PostgreSQL, Python-Dependencies, Config)..."));

        var setupRc = await RunBatchScriptAsync(
            Path.Combine(installDir, "setup.bat"),
            installDir,
            sink,
            ct).ConfigureAwait(false);
        if (setupRc != 0)
        {
            sink.Report(new RunnerStepEvent("setup", RunnerStepStatus.Fail));
            sink.Report(new RunnerLogEvent($"setup.bat exit={setupRc}"));
            sink.Report(new RunnerDoneEvent(false));
            return false;
        }
        sink.Report(new RunnerStepEvent("setup", RunnerStepStatus.Ok));
        sink.Report(new RunnerProgressEvent(60));

        // ---- Schritt 3: install-service.bat (NSSM, Firewall, Backup-Task) ----
        sink.Report(new RunnerStepEvent("service", RunnerStepStatus.Running));
        sink.Report(new RunnerLogEvent("Registriere PraxisZeit-Service + Firewall-Regel + Backup-Task..."));

        var svcRc = await RunBatchScriptAsync(
            Path.Combine(installDir, "install-service.bat"),
            installDir,
            sink,
            ct).ConfigureAwait(false);
        if (svcRc != 0)
        {
            sink.Report(new RunnerStepEvent("service", RunnerStepStatus.Fail));
            sink.Report(new RunnerLogEvent($"install-service.bat exit={svcRc}"));
            sink.Report(new RunnerDoneEvent(false));
            return false;
        }
        sink.Report(new RunnerStepEvent("service", RunnerStepStatus.Ok));
        sink.Report(new RunnerProgressEvent(85));

        // ---- Schritt 4: Service starten ----
        sink.Report(new RunnerStepEvent("start", RunnerStepStatus.Running));
        sink.Report(new RunnerLogEvent("Starte PraxisZeit-Service..."));

        var startRc = await RunNetCommandAsync(["start", "PraxisZeit"], sink, ct).ConfigureAwait(false);
        if (startRc != 0)
        {
            sink.Report(new RunnerStepEvent("start", RunnerStepStatus.Warn));
            sink.Report(new RunnerLogEvent(
                $"net start exit={startRc} — Service konnte nicht gestartet werden. " +
                "Pruefe logs\\service-stderr.log und logs\\praxiszeit.log."));
        }
        else
        {
            sink.Report(new RunnerStepEvent("start", RunnerStepStatus.Ok));
        }
        sink.Report(new RunnerProgressEvent(100));

        var success = startRc == 0;
        sink.Report(new RunnerDoneEvent(success));
        return success;
    }

    private async Task<bool> RunAndParseMarkersAsync(
        ProcessStartInfo psi,
        IProgress<RunnerEvent> sink,
        CancellationToken ct)
    {
        using var process = Process.Start(psi)
            ?? throw new InvalidOperationException($"Process.Start returned null for {psi.FileName}");

        var anyDoneMarker = false;
        var doneSuccess = false;

        process.OutputDataReceived += (_, e) =>
        {
            if (e.Data is null) { return; }
            ParseAndDispatch(e.Data, sink, ref anyDoneMarker, ref doneSuccess);
        };
        process.ErrorDataReceived += (_, e) =>
        {
            if (e.Data is null) { return; }
            sink.Report(new RunnerLogEvent($"[stderr] {e.Data}"));
        };
        process.BeginOutputReadLine();
        process.BeginErrorReadLine();

        await process.WaitForExitAsync(ct).ConfigureAwait(false);

        // Wenn das Script ein [DONE]-Marker emittiert hat, vertrauen wir dem.
        // Sonst interpretieren wir Exit-Code 0 als success.
        return anyDoneMarker ? doneSuccess : process.ExitCode == 0;
    }

    private static void ParseAndDispatch(
        string line,
        IProgress<RunnerEvent> sink,
        ref bool anyDoneMarker,
        ref bool doneSuccess)
    {
        var (evt, isDone, doneOk) = ScriptMarkerParser.ParseMarkerLine(line);
        if (isDone)
        {
            anyDoneMarker = true;
            doneSuccess = doneOk;
            return;
        }
        if (evt is not null)
        {
            sink.Report(evt);
        }
    }

    private static async Task<int> RunBatchScriptAsync(
        string batPath,
        string workingDir,
        IProgress<RunnerEvent> sink,
        CancellationToken ct)
    {
        if (!File.Exists(batPath))
        {
            sink.Report(new RunnerLogEvent($"FEHLER: {batPath} nicht gefunden"));
            return -1;
        }

        var psi = new ProcessStartInfo("cmd.exe")
        {
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true,
            WorkingDirectory = workingDir,
        };
        psi.ArgumentList.Add("/c");
        psi.ArgumentList.Add(batPath);
        // PRAXISZEIT_NONINTERACTIVE: setup.bat / install-service.bat ueberspringen
        // damit alle pause-Aufrufe (siehe `if not defined PRAXISZEIT_NONINTERACTIVE pause`).
        psi.Environment["PRAXISZEIT_NONINTERACTIVE"] = "1";
        // PYTHONUTF8 wegen cp1252-Crashes bei Emojis im uvicorn-Subprocess
        // (gleiche Regel wie in CLAUDE.md: "PYTHONUTF8=1: Immer fuer uvicorn-Subprozesse setzen").
        psi.Environment["PYTHONUTF8"] = "1";

        using var process = Process.Start(psi)
            ?? throw new InvalidOperationException($"Process.Start returned null for {batPath}");

        process.OutputDataReceived += (_, e) =>
        {
            if (e.Data is not null) { sink.Report(new RunnerLogEvent(e.Data)); }
        };
        process.ErrorDataReceived += (_, e) =>
        {
            if (e.Data is not null) { sink.Report(new RunnerLogEvent($"[stderr] {e.Data}")); }
        };
        process.BeginOutputReadLine();
        process.BeginErrorReadLine();

        await process.WaitForExitAsync(ct).ConfigureAwait(false);
        return process.ExitCode;
    }

    private static async Task<int> RunNetCommandAsync(
        string[] arguments,
        IProgress<RunnerEvent> sink,
        CancellationToken ct)
    {
        var psi = new ProcessStartInfo("net.exe")
        {
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true,
        };
        foreach (var a in arguments)
        {
            psi.ArgumentList.Add(a);
        }

        using var process = Process.Start(psi)
            ?? throw new InvalidOperationException("Process.Start returned null for net.exe");

        process.OutputDataReceived += (_, e) =>
        {
            if (e.Data is not null) { sink.Report(new RunnerLogEvent(e.Data)); }
        };
        process.ErrorDataReceived += (_, e) =>
        {
            if (e.Data is not null) { sink.Report(new RunnerLogEvent($"[stderr] {e.Data}")); }
        };
        process.BeginOutputReadLine();
        process.BeginErrorReadLine();

        await process.WaitForExitAsync(ct).ConfigureAwait(false);
        return process.ExitCode;
    }

    private static void CopyDirectoryRecursive(string sourceDir, string destDir, CancellationToken ct)
    {
        Directory.CreateDirectory(destDir);
        foreach (var file in Directory.EnumerateFiles(sourceDir))
        {
            ct.ThrowIfCancellationRequested();
            var fileName = Path.GetFileName(file);
            var destFile = Path.Combine(destDir, fileName);
            File.Copy(file, destFile, overwrite: true);
        }
        foreach (var subDir in Directory.EnumerateDirectories(sourceDir))
        {
            ct.ThrowIfCancellationRequested();
            var subDirName = Path.GetFileName(subDir);
            var destSubDir = Path.Combine(destDir, subDirName);
            CopyDirectoryRecursive(subDir, destSubDir, ct);
        }
    }
}
