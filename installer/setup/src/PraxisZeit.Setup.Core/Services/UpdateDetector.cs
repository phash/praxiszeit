using System.Runtime.Versioning;
using System.Security.AccessControl;
using System.Security.Principal;
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

    private readonly Func<string, bool> _ownedByAdmins;

    /// <param name="ownedByAdmins">
    /// Prueft, ob der Ordner Administratoren oder SYSTEM gehoert (Standard:
    /// Windows-ACL; ausserhalb von Windows immer true). Ersetzbar fuer Tests.
    /// </param>
    public UpdateDetector(Func<string, bool>? ownedByAdmins = null)
    {
        _ownedByAdmins = ownedByAdmins ?? DefaultOwnedByAdmins;
    }

    public InstallMode DetectMode(string targetDirectory, string installerVersion)
    {
        var currentVersion = DetectCurrentVersion(targetDirectory);
        if (currentVersion is null)
        {
            return InstallMode.FreshInstall;
        }

        if (currentVersion != installerVersion)
        {
            return InstallMode.Update;
        }

        // Gleiche Version: nur eine fertige Installation laesst sich ueber den
        // Update-Wizard reparieren. Ohne Datenbank-Zugangsdaten ist setup.bat
        // nie durchgelaufen -> Erstinstallation fortsetzen (Review 2026-11-15).
        var credentials = Path.Combine(targetDirectory, "config", ".db-credentials");
        if (File.Exists(credentials))
        {
            return InstallMode.Repair;
        }

        // "Fortsetzen" ueberspringt die Leerordner-Sperre (S3-01). Unter C:\
        // darf jedes Konto Ordner anlegen und eine passende updater.py
        // hineinlegen - deshalb nur, wenn der Ordner Administratoren/SYSTEM
        // gehoert (eine abgebrochene Erstinstallation hat ihn so hinterlassen).
        // Sonst wie eine Erstinstallation: die Sperre meldet "nicht leer".
        // Die eigentliche Absicherung folgt im Lauf: HardenInstallRootAsync vor
        // dem Kopieren, secure-install.ps1 als Schritt 0 von setup.bat
        // (Eigentuemer/DACL rekursiv, Manifest-Abgleich, Verknuepfungen -> Exit 2).
        // Ein Ordner, der selbst eine Verknuepfung ist, wird nie fortgesetzt.
        var isReparsePoint = new DirectoryInfo(targetDirectory).Attributes.HasFlag(FileAttributes.ReparsePoint);
        return !isReparsePoint && _ownedByAdmins(targetDirectory) ? InstallMode.Resume : InstallMode.FreshInstall;
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

    private static bool DefaultOwnedByAdmins(string directory)
    {
        if (!OperatingSystem.IsWindows())
        {
            return true;
        }
        return WindowsOwnedByAdmins(directory);
    }

    [SupportedOSPlatform("windows")]
    private static bool WindowsOwnedByAdmins(string directory)
    {
        try
        {
            var owner = new DirectoryInfo(directory).GetAccessControl(AccessControlSections.Owner)
                .GetOwner(typeof(SecurityIdentifier)) as SecurityIdentifier;
            return owner is not null
                && (owner.IsWellKnown(WellKnownSidType.BuiltinAdministratorsSid)
                    || owner.IsWellKnown(WellKnownSidType.LocalSystemSid));
        }
        catch (Exception)
        {
            return false;
        }
    }
}
