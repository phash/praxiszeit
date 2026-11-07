using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Runtime.Versioning;
using System.Security.Principal;
using System.ServiceProcess;

namespace PraxisZeit.Setup.Core.Platform;

/// <summary>
/// Windows-Implementierung. Nutzt den Service Control Manager via
/// <see cref="ServiceController"/> fuer Status, Start und Stop. Registrierung
/// (NSSM mit AppExit 78, PYTHONNOUSERSITE), Firewall-Regel und Backup-Task
/// macht ausschliesslich install-service.bat bzw. update-wizard.ps1 (S3-17).
/// </summary>
[SupportedOSPlatform("windows")]
public sealed class WindowsPlatform : IPlatform
{
    private const string ServiceName = "PraxisZeit";

    public string Name => "Windows";

    public string DefaultInstallDirectory => @"C:\PraxisZeit";

    public string RuntimeIdentifier =>
        RuntimeInformation.OSArchitecture == Architecture.Arm64 ? "win-arm64" : "win-x64";

    public Task<bool> IsElevatedAsync()
    {
        using var identity = WindowsIdentity.GetCurrent();
        var principal = new WindowsPrincipal(identity);
        return Task.FromResult(principal.IsInRole(WindowsBuiltInRole.Administrator));
    }

    public Task<bool> IsServiceInstalledAsync(CancellationToken ct = default)
    {
        try
        {
            using var sc = new ServiceController(ServiceName);
            _ = sc.Status;
            return Task.FromResult(true);
        }
        catch (InvalidOperationException)
        {
            return Task.FromResult(false);
        }
    }

    public Task<ServiceStatus> GetServiceStatusAsync(CancellationToken ct = default)
    {
        try
        {
            using var sc = new ServiceController(ServiceName);
            return Task.FromResult(sc.Status switch
            {
                ServiceControllerStatus.Stopped => ServiceStatus.Stopped,
                ServiceControllerStatus.StartPending => ServiceStatus.StartPending,
                ServiceControllerStatus.StopPending => ServiceStatus.StopPending,
                ServiceControllerStatus.Running => ServiceStatus.Running,
                ServiceControllerStatus.Paused => ServiceStatus.Paused,
                _ => ServiceStatus.Unknown,
            });
        }
        catch (InvalidOperationException)
        {
            return Task.FromResult(ServiceStatus.NotInstalled);
        }
    }

    public async Task StartServiceAsync(CancellationToken ct = default)
    {
        using var sc = new ServiceController(ServiceName);
        if (sc.Status == ServiceControllerStatus.Running)
        {
            return;
        }

        sc.Start();
        while (sc.Status != ServiceControllerStatus.Running)
        {
            ct.ThrowIfCancellationRequested();
            await Task.Delay(500, ct).ConfigureAwait(false);
            sc.Refresh();
        }
    }

    public async Task StopServiceAsync(CancellationToken ct = default)
    {
        using var sc = new ServiceController(ServiceName);
        if (sc.Status == ServiceControllerStatus.Stopped)
        {
            return;
        }

        sc.Stop();
        while (sc.Status != ServiceControllerStatus.Stopped)
        {
            ct.ThrowIfCancellationRequested();
            await Task.Delay(500, ct).ConfigureAwait(false);
            sc.Refresh();
        }
    }
}
