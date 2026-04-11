using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Runtime.Versioning;
using System.Security.Principal;
using System.ServiceProcess;

namespace PraxisZeit.Setup.Core.Platform;

/// <summary>
/// Windows-Implementierung. Nutzt den Service Control Manager via
/// <see cref="ServiceController"/> fuer den Service-Lifecycle,
/// <c>nssm.exe</c> fuer die Service-Registrierung (weil es einen
/// Python-Subprocess wrappen muss, nicht ein natives Service-Binary),
/// <c>netsh advfirewall</c> fuer Firewall-Regeln und <c>schtasks</c>
/// fuer den taeglichen Backup-Task.
/// </summary>
[SupportedOSPlatform("windows")]
public sealed class WindowsPlatform : IPlatform
{
    private const string ServiceName = "PraxisZeit";
    private const string FirewallRuleName = "PraxisZeit";
    private const string BackupTaskName = "PraxisZeit-Backup";

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

    public async Task InstallServiceAsync(string executablePath, string[] arguments, string workingDirectory, CancellationToken ct = default)
    {
        // NSSM ist der pragmatische Weg fuer Python-basierte Services.
        // Alternativ: natives .NET "Worker Service"-Binary, aber PraxisZeit
        // ist Python-basiert — dann muessten wir ein Wrapper-Binary schreiben.
        var nssmPath = Path.Combine(workingDirectory, "nssm.exe");
        if (!File.Exists(nssmPath))
        {
            throw new FileNotFoundException(
                $"nssm.exe not found next to installer payload at {nssmPath}. " +
                "The payload ZIP must bundle nssm.exe for Windows service registration.");
        }

        var argString = string.Join(' ', arguments.Select(a => a.Contains(' ') ? $"\"{a}\"" : a));
        await RunProcessAsync(nssmPath, ["install", ServiceName, executablePath, argString], ct).ConfigureAwait(false);
        await RunProcessAsync(nssmPath, ["set", ServiceName, "AppDirectory", workingDirectory], ct).ConfigureAwait(false);
        await RunProcessAsync(nssmPath, ["set", ServiceName, "DisplayName", "PraxisZeit Zeiterfassung"], ct).ConfigureAwait(false);
        await RunProcessAsync(nssmPath, ["set", ServiceName, "Description", "Zeiterfassung fuer Arztpraxen"], ct).ConfigureAwait(false);
        await RunProcessAsync(nssmPath, ["set", ServiceName, "Start", "SERVICE_AUTO_START"], ct).ConfigureAwait(false);
        await RunProcessAsync(nssmPath, ["set", ServiceName, "AppStdout", Path.Combine(workingDirectory, "logs", "service-stdout.log")], ct).ConfigureAwait(false);
        await RunProcessAsync(nssmPath, ["set", ServiceName, "AppStderr", Path.Combine(workingDirectory, "logs", "service-stderr.log")], ct).ConfigureAwait(false);
        await RunProcessAsync(nssmPath, ["set", ServiceName, "AppRotateFiles", "1"], ct).ConfigureAwait(false);
        await RunProcessAsync(nssmPath, ["set", ServiceName, "AppRotateBytes", "10485760"], ct).ConfigureAwait(false);
    }

    public async Task UninstallServiceAsync(CancellationToken ct = default)
    {
        if (!await IsServiceInstalledAsync(ct).ConfigureAwait(false))
        {
            return;
        }

        await StopServiceAsync(ct).ConfigureAwait(false);
        // Fallback via sc.exe, weil nssm.exe vom alten Install nicht unbedingt
        // noch unter dem erwarteten Pfad liegt (wenn der Kunde manuell was
        // geloescht hat).
        await RunProcessAsync("sc.exe", ["delete", ServiceName], ct, ignoreExitCode: true).ConfigureAwait(false);
    }

    public async Task OpenFirewallAsync(int port, CancellationToken ct = default)
    {
        await RunProcessAsync(
            "netsh.exe",
            ["advfirewall", "firewall", "add", "rule",
             $"name={FirewallRuleName}", "dir=in", "action=allow",
             "protocol=TCP", $"localport={port}"],
            ct).ConfigureAwait(false);
    }

    public async Task CloseFirewallAsync(int port, CancellationToken ct = default)
    {
        await RunProcessAsync(
            "netsh.exe",
            ["advfirewall", "firewall", "delete", "rule", $"name={FirewallRuleName}"],
            ct, ignoreExitCode: true).ConfigureAwait(false);
    }

    public async Task ScheduleDailyBackupAsync(string backupCommand, TimeOnly dailyAt, CancellationToken ct = default)
    {
        var timeArg = dailyAt.ToString("HH:mm", System.Globalization.CultureInfo.InvariantCulture);
        await RunProcessAsync(
            "schtasks.exe",
            ["/create", "/tn", BackupTaskName,
             "/tr", $"\"{backupCommand}\"",
             "/sc", "daily", "/st", timeArg,
             "/ru", "SYSTEM", "/f"],
            ct).ConfigureAwait(false);
    }

    public async Task UnscheduleDailyBackupAsync(CancellationToken ct = default)
    {
        await RunProcessAsync(
            "schtasks.exe",
            ["/delete", "/tn", BackupTaskName, "/f"],
            ct, ignoreExitCode: true).ConfigureAwait(false);
    }

    private static async Task RunProcessAsync(
        string fileName,
        string[] arguments,
        CancellationToken ct,
        bool ignoreExitCode = false)
    {
        var psi = new ProcessStartInfo(fileName)
        {
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true,
        };
        foreach (var arg in arguments)
        {
            psi.ArgumentList.Add(arg);
        }

        using var process = Process.Start(psi)
            ?? throw new InvalidOperationException($"Failed to start process: {fileName}");

        await process.WaitForExitAsync(ct).ConfigureAwait(false);

        if (!ignoreExitCode && process.ExitCode != 0)
        {
            var stderr = await process.StandardError.ReadToEndAsync(ct).ConfigureAwait(false);
            throw new InvalidOperationException(
                $"{fileName} exited with code {process.ExitCode}: {stderr}");
        }
    }
}
