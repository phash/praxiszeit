namespace PraxisZeit.Setup.Core.Platform;

/// <summary>
/// Plattform-Abstraktion fuer alle OS-spezifischen Operationen, die der
/// Installer ausfuehren muss: Service-Registrierung, Firewall-Regeln,
/// Scheduled Tasks / Cron, Elevation-Check, Default-Install-Pfad.
///
/// Dient dazu, die Core-Logik (Wizard-Flow, Payload-Handling, Config)
/// plattform-unabhaengig zu halten. Die View-Models und Services in
/// <c>PraxisZeit.Setup.Core</c> kennen <b>nur</b> dieses Interface,
/// nicht die konkreten Implementierungen.
/// </summary>
public interface IPlatform
{
    /// <summary>Name der Plattform fuer Logging (z.B. "Windows", "Linux", "macOS").</summary>
    string Name { get; }

    /// <summary>Default-Installationsverzeichnis (C:\PraxisZeit, /opt/praxiszeit, /usr/local/praxiszeit).</summary>
    string DefaultInstallDirectory { get; }

    /// <summary>Runtime-Identifier fuer die Payload-Auswahl (z.B. "win-x64").</summary>
    string RuntimeIdentifier { get; }

    /// <summary>Prueft ob der aktuelle Prozess mit Admin-/Root-Rechten laeuft.</summary>
    Task<bool> IsElevatedAsync();

    /// <summary>Prueft ob der PraxisZeit-Service bereits registriert ist.</summary>
    Task<bool> IsServiceInstalledAsync(CancellationToken ct = default);

    /// <summary>Status des PraxisZeit-Service (falls registriert).</summary>
    Task<ServiceStatus> GetServiceStatusAsync(CancellationToken ct = default);

    /// <summary>Startet den PraxisZeit-Service und wartet bis <see cref="ServiceStatus.Running"/>.</summary>
    Task StartServiceAsync(CancellationToken ct = default);

    /// <summary>Stoppt den PraxisZeit-Service und wartet bis <see cref="ServiceStatus.Stopped"/>.</summary>
    Task StopServiceAsync(CancellationToken ct = default);

    // Audit 2026-11-07 S3-17: Service-Registrierung, Firewall und Backup-Task
    // laufen ausschliesslich ueber install-service.bat / update-wizard.ps1
    // (NSSM AppExit 78, PYTHONNOUSERSITE, AppEnvironmentExtra, Backup als
    // SYSTEM). Die frueheren, nie aufgerufenen C#-Gegenstuecke ohne diese
    // Haertung wurden entfernt - nicht wieder einfuehren, sondern die .bat nutzen.
}

public enum ServiceStatus
{
    NotInstalled,
    Stopped,
    StartPending,
    Running,
    StopPending,
    Paused,
    Unknown,
}
