using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Runtime.Versioning;

namespace PraxisZeit.Setup.Core.Platform;

/// <summary>
/// Linux-Implementierung via systemd Unit Files + cron.d. Firewall via
/// Tool-Detection (firewalld / ufw). Elevation via <c>geteuid() == 0</c>.
/// </summary>
[SupportedOSPlatform("linux")]
public sealed class LinuxPlatform : IPlatform
{
    private const string ServiceName = "praxiszeit";
    private const string UnitFile = "/etc/systemd/system/praxiszeit.service";
    private const string CronFile = "/etc/cron.d/praxiszeit-backup";

    [DllImport("libc", EntryPoint = "geteuid")]
    private static extern uint geteuid();

    public string Name => "Linux";

    public string DefaultInstallDirectory => "/opt/praxiszeit";

    public string RuntimeIdentifier =>
        RuntimeInformation.OSArchitecture == Architecture.Arm64 ? "linux-arm64" : "linux-x64";

    public Task<bool> IsElevatedAsync() => Task.FromResult(geteuid() == 0);

    public async Task<bool> IsServiceInstalledAsync(CancellationToken ct = default)
    {
        var exit = await RunProcessAsync("systemctl", ["status", ServiceName], ct, ignoreExitCode: true)
            .ConfigureAwait(false);
        // systemctl status: 0=running, 3=stopped-but-exists, 4=not-found
        return exit != 4 && File.Exists(UnitFile);
    }

    public async Task<ServiceStatus> GetServiceStatusAsync(CancellationToken ct = default)
    {
        if (!File.Exists(UnitFile))
        {
            return ServiceStatus.NotInstalled;
        }

        var (_, stdout, _) = await RunProcessCaptureAsync(
            "systemctl", ["is-active", ServiceName], ct, ignoreExitCode: true)
            .ConfigureAwait(false);

        return stdout.Trim() switch
        {
            "active" => ServiceStatus.Running,
            "activating" => ServiceStatus.StartPending,
            "deactivating" => ServiceStatus.StopPending,
            "inactive" => ServiceStatus.Stopped,
            "failed" => ServiceStatus.Stopped,
            _ => ServiceStatus.Unknown,
        };
    }

    public async Task StartServiceAsync(CancellationToken ct = default)
    {
        await RunProcessAsync("systemctl", ["start", ServiceName], ct).ConfigureAwait(false);
        for (var i = 0; i < 60; i++)
        {
            if (await GetServiceStatusAsync(ct).ConfigureAwait(false) == ServiceStatus.Running)
            {
                return;
            }
            await Task.Delay(1000, ct).ConfigureAwait(false);
        }
        throw new TimeoutException("praxiszeit.service did not start within 60 seconds");
    }

    public async Task StopServiceAsync(CancellationToken ct = default)
    {
        await RunProcessAsync("systemctl", ["stop", ServiceName], ct, ignoreExitCode: true)
            .ConfigureAwait(false);
        for (var i = 0; i < 60; i++)
        {
            var status = await GetServiceStatusAsync(ct).ConfigureAwait(false);
            if (status is ServiceStatus.Stopped or ServiceStatus.NotInstalled)
            {
                return;
            }
            await Task.Delay(1000, ct).ConfigureAwait(false);
        }
    }

    public async Task InstallServiceAsync(
        string executablePath,
        string[] arguments,
        string workingDirectory,
        CancellationToken ct = default)
    {
        var execStart = arguments.Length == 0
            ? executablePath
            : $"{executablePath} {string.Join(' ', arguments)}";

        var unit = $"""
            [Unit]
            Description=PraxisZeit Zeiterfassung
            After=network.target postgresql.service

            [Service]
            Type=simple
            User=praxiszeit
            Group=praxiszeit
            WorkingDirectory={workingDirectory}
            ExecStart={execStart}
            Restart=on-failure
            RestartSec=5
            StandardOutput=append:{workingDirectory}/logs/service-stdout.log
            StandardError=append:{workingDirectory}/logs/service-stderr.log
            Environment=PYTHONUTF8=1

            [Install]
            WantedBy=multi-user.target
            """;

        await File.WriteAllTextAsync(UnitFile, unit, ct).ConfigureAwait(false);
        await RunProcessAsync("systemctl", ["daemon-reload"], ct).ConfigureAwait(false);
        await RunProcessAsync("systemctl", ["enable", ServiceName], ct).ConfigureAwait(false);
    }

    public async Task UninstallServiceAsync(CancellationToken ct = default)
    {
        await StopServiceAsync(ct).ConfigureAwait(false);
        await RunProcessAsync("systemctl", ["disable", ServiceName], ct, ignoreExitCode: true)
            .ConfigureAwait(false);
        if (File.Exists(UnitFile))
        {
            File.Delete(UnitFile);
        }
        await RunProcessAsync("systemctl", ["daemon-reload"], ct, ignoreExitCode: true)
            .ConfigureAwait(false);
    }

    public async Task OpenFirewallAsync(int port, CancellationToken ct = default)
    {
        if (await CommandExistsAsync("firewall-cmd", ct).ConfigureAwait(false))
        {
            await RunProcessAsync(
                "firewall-cmd", ["--permanent", $"--add-port={port}/tcp"], ct).ConfigureAwait(false);
            await RunProcessAsync("firewall-cmd", ["--reload"], ct).ConfigureAwait(false);
            return;
        }

        if (await CommandExistsAsync("ufw", ct).ConfigureAwait(false))
        {
            await RunProcessAsync("ufw", ["allow", $"{port}/tcp"], ct).ConfigureAwait(false);
            return;
        }

        // Kein passendes Tool - no-op, Admin macht manuell
    }

    public async Task CloseFirewallAsync(int port, CancellationToken ct = default)
    {
        if (await CommandExistsAsync("firewall-cmd", ct).ConfigureAwait(false))
        {
            await RunProcessAsync(
                "firewall-cmd", ["--permanent", $"--remove-port={port}/tcp"], ct, ignoreExitCode: true)
                .ConfigureAwait(false);
            await RunProcessAsync("firewall-cmd", ["--reload"], ct, ignoreExitCode: true)
                .ConfigureAwait(false);
            return;
        }

        if (await CommandExistsAsync("ufw", ct).ConfigureAwait(false))
        {
            await RunProcessAsync(
                "ufw", ["delete", "allow", $"{port}/tcp"], ct, ignoreExitCode: true)
                .ConfigureAwait(false);
        }
    }

    public async Task ScheduleDailyBackupAsync(
        string backupCommand,
        TimeOnly dailyAt,
        CancellationToken ct = default)
    {
        var cronLine = $"{dailyAt.Minute} {dailyAt.Hour} * * * praxiszeit {backupCommand}\n";
        await File.WriteAllTextAsync(CronFile, cronLine, ct).ConfigureAwait(false);
    }

    public Task UnscheduleDailyBackupAsync(CancellationToken ct = default)
    {
        if (File.Exists(CronFile))
        {
            File.Delete(CronFile);
        }
        return Task.CompletedTask;
    }

    private static async Task<bool> CommandExistsAsync(string command, CancellationToken ct)
    {
        var exit = await RunProcessAsync("which", [command], ct, ignoreExitCode: true).ConfigureAwait(false);
        return exit == 0;
    }

    private static async Task<int> RunProcessAsync(
        string fileName,
        string[] arguments,
        CancellationToken ct,
        bool ignoreExitCode = false)
    {
        var (exit, _, stderr) = await RunProcessCaptureAsync(fileName, arguments, ct, ignoreExitCode)
            .ConfigureAwait(false);
        if (!ignoreExitCode && exit != 0)
        {
            throw new InvalidOperationException($"{fileName} exited with code {exit}: {stderr}");
        }
        return exit;
    }

    private static async Task<(int ExitCode, string StdOut, string StdErr)> RunProcessCaptureAsync(
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

        var stdoutTask = process.StandardOutput.ReadToEndAsync(ct);
        var stderrTask = process.StandardError.ReadToEndAsync(ct);
        await process.WaitForExitAsync(ct).ConfigureAwait(false);

        return (process.ExitCode, await stdoutTask.ConfigureAwait(false), await stderrTask.ConfigureAwait(false));
    }
}
