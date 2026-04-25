using System.Text.RegularExpressions;

namespace PraxisZeit.Setup.Core.Services;

/// <summary>
/// Plattform-agnostischer Parser fuer die Stdout-Marker, die der
/// PowerShell-Headless-Mode (<c>update-wizard.ps1 -Headless</c>) emittiert.
/// In eine eigene Klasse extrahiert (statt im Windows-restricted
/// <see cref="ScriptRunner"/>), damit Unit-Tests ohne CA1416-Suppress
/// laufen koennen.
/// </summary>
public static partial class ScriptMarkerParser
{
    [GeneratedRegex(@"^\[STEP\]\s+(\S+)\s+(\S+)\s*$")]
    private static partial Regex StepMarkerRegex();

    [GeneratedRegex(@"^\[LOG\]\s?(.*)$")]
    private static partial Regex LogMarkerRegex();

    [GeneratedRegex(@"^\[PROGRESS\]\s+(\d+)\s*$")]
    private static partial Regex ProgressMarkerRegex();

    [GeneratedRegex(@"^\[DONE\]\s+(success|fail)\s*$")]
    private static partial Regex DoneMarkerRegex();

    [GeneratedRegex(@"^\[ERROR\]\s?(.*)$")]
    private static partial Regex ErrorMarkerRegex();

    /// <summary>
    /// Parst eine Zeile aus dem Subprocess-Stdout in einen
    /// <see cref="RunnerEvent"/>. <c>[DONE]</c> wird als Tupel
    /// (isDone=true, doneOk=success) zurueckgegeben statt als Event,
    /// weil es im Aufrufer Sentinel-State setzt.
    /// </summary>
    public static (RunnerEvent? Event, bool IsDone, bool DoneOk) ParseMarkerLine(string line)
    {
        var stepMatch = StepMarkerRegex().Match(line);
        if (stepMatch.Success)
        {
            var status = stepMatch.Groups[2].Value.ToLowerInvariant() switch
            {
                "running" => RunnerStepStatus.Running,
                "ok" => RunnerStepStatus.Ok,
                "warn" => RunnerStepStatus.Warn,
                "fail" => RunnerStepStatus.Fail,
                _ => RunnerStepStatus.Pending,
            };
            return (new RunnerStepEvent(stepMatch.Groups[1].Value, status), false, false);
        }

        var progMatch = ProgressMarkerRegex().Match(line);
        if (progMatch.Success && int.TryParse(progMatch.Groups[1].Value, out var pct))
        {
            return (new RunnerProgressEvent(pct), false, false);
        }

        var doneMatch = DoneMarkerRegex().Match(line);
        if (doneMatch.Success)
        {
            var success = doneMatch.Groups[1].Value.Equals("success", StringComparison.OrdinalIgnoreCase);
            return (null, true, success);
        }

        var logMatch = LogMarkerRegex().Match(line);
        if (logMatch.Success)
        {
            return (new RunnerLogEvent(logMatch.Groups[1].Value), false, false);
        }

        var errMatch = ErrorMarkerRegex().Match(line);
        if (errMatch.Success)
        {
            return (new RunnerLogEvent($"FEHLER: {errMatch.Groups[1].Value}"), false, false);
        }

        // Kein Marker — Raw-Output (von Subprozessen wie pip, robocopy)
        return (new RunnerLogEvent(line), false, false);
    }
}
