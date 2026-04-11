namespace PraxisZeit.Setup.Core.Models;

/// <summary>
/// Aggregiert alle Wizard-Inputs, die der User im Laufe der Install-Pages
/// macht. Immutable Record, wird in der ProgressPage an die
/// <see cref="Core.Services.IInstallOrchestrator"/> uebergeben.
///
/// Im Update-Modus sind Praxis-Daten, Admin-Account und SSL-Modus
/// <c>null</c> — die werden aus der existierenden Config uebernommen.
/// </summary>
public sealed record InstallOptions
{
    public required InstallMode Mode { get; init; }
    public required string InstallDirectory { get; init; }

    // Nur bei FreshInstall gesetzt
    public PracticeInfo? Practice { get; init; }
    public AdminAccount? Admin { get; init; }
    public NetworkConfig? Network { get; init; }
    public SslConfig? Ssl { get; init; }

    // Payload-Location: Pfad zur praxiszeit-<version>-<rid>.zip neben der Setup-EXE
    public required string PayloadPath { get; init; }

    // Quell-Version die installiert werden soll (aus Payload-ZIP-Namen gelesen)
    public required string TargetVersion { get; init; }

    // Bei Update: aktuelle Version auf dem System
    public string? CurrentVersion { get; init; }
}

public sealed record PracticeInfo
{
    public required string Name { get; init; }
    public string? Address { get; init; }
    public required string HolidayState { get; init; } // "Bayern", "NRW", etc.
}

public sealed record AdminAccount
{
    public required string Username { get; init; }
    public required string Email { get; init; }
    public required string Password { get; init; }
    public string? FirstName { get; init; }
    public string? LastName { get; init; }
}

public sealed record NetworkConfig
{
    public required int Port { get; init; }
    public required bool OpenFirewall { get; init; }
    public string BindAddress { get; init; } = "0.0.0.0";
}

public sealed record SslConfig
{
    public required SslMode Mode { get; init; }

    // Bei SelfSigned: die IP/Hostname fuer SubjectAltName (wird automatisch erkannt
    // wenn null, kann aber vom User ueberschrieben werden)
    public string? SelfSignedIp { get; init; }

    // Bei BringYourOwn: Pfade zu den vorhandenen Cert-Dateien
    public string? ExistingCertPath { get; init; }
    public string? ExistingKeyPath { get; init; }
}
