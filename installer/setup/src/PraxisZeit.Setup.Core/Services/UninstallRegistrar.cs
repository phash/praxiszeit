using System.Diagnostics;
using System.Runtime.Versioning;

namespace PraxisZeit.Setup.Core.Services;

/// <summary>
/// Registriert PraxisZeit unter
/// <c>HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\PraxisZeit</c>,
/// damit es in „Einstellungen → Apps → Installierte Apps" (bzw.
/// „Programme und Features") auftaucht und von dort deinstalliert werden kann.
///
/// <para>
/// Geschrieben über <c>reg.exe</c> statt der <c>Microsoft.Win32.Registry</c>-API,
/// damit das plattformneutrale net10.0-Target ohne Windows-spezifisches
/// NuGet-Paket / TFM auskommt. Die zu schreibenden Werte werden in
/// <see cref="BuildEntries"/> rein berechnet (testbar); <see cref="Register"/>
/// ruft nur noch reg.exe auf (benötigt Adminrechte → läuft im elevierten
/// Installer).
/// </para>
/// </summary>
public static class UninstallRegistrar
{
    public const string KeyPath =
        @"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\PraxisZeit";

    /// <summary>Eine zu schreibende Registry-Wert-Definition.</summary>
    public readonly record struct RegEntry(string Name, string Type, string Data);

    /// <summary>Berechnet die Registry-Werte (rein, ohne Seiteneffekt → testbar).</summary>
    public static IReadOnlyList<RegEntry> BuildEntries(string installDir, string version)
    {
        var uninstall = Path.Combine(installDir, "uninstall.bat");
        var icon = Path.Combine(installDir, "app", "frontend", "favicon.ico");
        return new List<RegEntry>
        {
            new("DisplayName",     "REG_SZ",    "PraxisZeit"),
            new("DisplayVersion",  "REG_SZ",    version),
            new("Publisher",       "REG_SZ",    "MR Development"),
            new("InstallLocation", "REG_SZ",    installDir),
            // UninstallString muss zitiert sein (Pfad kann Leerzeichen enthalten).
            new("UninstallString", "REG_SZ",    $"\"{uninstall}\""),
            new("DisplayIcon",     "REG_SZ",    icon),
            new("URLInfoAbout",    "REG_SZ",    "https://praxiszeit.mr-development.de"),
            new("NoModify",        "REG_DWORD", "1"),
            new("NoRepair",        "REG_DWORD", "1"),
        };
    }

    /// <summary>Schreibt den Uninstall-Schlüssel nach HKLM (benötigt Adminrechte).</summary>
    [SupportedOSPlatform("windows")]
    public static void Register(string installDir, string version)
    {
        RunReg("add", KeyPath, "/f");
        foreach (var e in BuildEntries(installDir, version))
        {
            RunReg("add", KeyPath, "/v", e.Name, "/t", e.Type, "/d", e.Data, "/f");
        }
    }

    [SupportedOSPlatform("windows")]
    private static void RunReg(params string[] args)
    {
        var psi = new ProcessStartInfo("reg.exe")
        {
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        };
        foreach (var a in args) { psi.ArgumentList.Add(a); }
        using var p = Process.Start(psi);
        p?.WaitForExit();
    }
}
