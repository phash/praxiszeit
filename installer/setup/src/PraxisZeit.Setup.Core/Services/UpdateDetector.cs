using System.Text.RegularExpressions;
using PraxisZeit.Setup.Core.Models;

namespace PraxisZeit.Setup.Core.Services;

/// <summary>
/// Detektiert ob in einem Zielverzeichnis bereits eine PraxisZeit-
/// Installation vorhanden ist, und wenn ja welche Version. Parst
/// <c>backend/app/core/updater.py</c> auf <c>APP_VERSION = "X.Y.Z"</c>.
///
/// Das ist die Single-Source-of-Truth fuer die Versionierung (CLAUDE.md-
/// Regel aus dem Backend-Repo). Alternative waere eine Query auf die
/// laufende Admin-API <c>/api/admin/updates/status</c>, aber das ist
/// zu fragil — der Service koennte gerade runter sein.
/// </summary>
public sealed partial class UpdateDetector
{
    [GeneratedRegex(@"APP_VERSION\s*=\s*""([^""]+)""")]
    private static partial Regex AppVersionRegex();

    public InstallMode DetectMode(string targetDirectory, string installerVersion)
    {
        var currentVersion = DetectCurrentVersion(targetDirectory);
        if (currentVersion is null)
        {
            return InstallMode.FreshInstall;
        }

        return currentVersion == installerVersion ? InstallMode.Repair : InstallMode.Update;
    }

    public string? DetectCurrentVersion(string targetDirectory)
    {
        if (string.IsNullOrWhiteSpace(targetDirectory) || !Directory.Exists(targetDirectory))
        {
            return null;
        }

        // Primaer: app/backend/app/core/updater.py (Native-Install-Layout)
        // Fallback: backend/app/core/updater.py (Dev-Layout)
        var candidates = new[]
        {
            Path.Combine(targetDirectory, "app", "backend", "app", "core", "updater.py"),
            Path.Combine(targetDirectory, "backend", "app", "core", "updater.py"),
        };

        foreach (var candidate in candidates)
        {
            if (!File.Exists(candidate))
            {
                continue;
            }

            var content = File.ReadAllText(candidate);
            var match = AppVersionRegex().Match(content);
            if (match.Success)
            {
                return match.Groups[1].Value;
            }
        }

        // Server-Script existiert aber updater.py nicht gefunden?
        // Dann gibt's zumindest praxiszeit-server.py — merken wir uns als
        // "unbekannte Version" (= altes 1.2.x oder frueher)
        var serverScript = Path.Combine(targetDirectory, "praxiszeit-server.py");
        return File.Exists(serverScript) ? "unknown" : null;
    }
}
