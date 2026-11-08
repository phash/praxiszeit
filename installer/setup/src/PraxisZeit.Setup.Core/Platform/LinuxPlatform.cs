using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Runtime.Versioning;

namespace PraxisZeit.Setup.Core.Platform;

/// <summary>
/// Linux-Implementierung (systemd: Status, Start, Stop). Elevation via
/// <c>geteuid() == 0</c>. Dienst-Registrierung macht installer/linux/install.sh.
/// </summary>
[SupportedOSPlatform("linux")]
public sealed class LinuxPlatform : IPlatform
{
    private const string ServiceName = "praxiszeit";
    private const string UnitFile = "/etc/systemd/system/praxiszeit.service";

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
