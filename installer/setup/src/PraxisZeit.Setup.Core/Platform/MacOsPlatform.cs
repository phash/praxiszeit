using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Runtime.Versioning;

namespace PraxisZeit.Setup.Core.Platform;

/// <summary>
/// macOS-Implementierung (launchctl: Status, Start, Stop). Elevation via
/// <c>geteuid() == 0</c>. Dienst-Registrierung macht installer/macos/install.sh.
/// </summary>
[SupportedOSPlatform("macos")]
public sealed class MacOsPlatform : IPlatform
{
    private const string PlistLabel = "de.praxiszeit.server";
    private const string PlistPath = "/Library/LaunchDaemons/de.praxiszeit.server.plist";

    [DllImport("libc", EntryPoint = "geteuid")]
    private static extern uint geteuid();

    public string Name => "macOS";

    public string DefaultInstallDirectory => "/usr/local/praxiszeit";

    public string RuntimeIdentifier =>
        RuntimeInformation.OSArchitecture == Architecture.Arm64 ? "osx-arm64" : "osx-x64";

    public Task<bool> IsElevatedAsync() => Task.FromResult(geteuid() == 0);

    public Task<bool> IsServiceInstalledAsync(CancellationToken ct = default)
        => Task.FromResult(File.Exists(PlistPath));

    public async Task<ServiceStatus> GetServiceStatusAsync(CancellationToken ct = default)
    {
        if (!File.Exists(PlistPath))
        {
            return ServiceStatus.NotInstalled;
        }

        var (_, stdout, _) = await RunProcessCaptureAsync(
            "launchctl", ["list", PlistLabel], ct, ignoreExitCode: true).ConfigureAwait(false);

        // launchctl list <label>: 0 = running (returns plist dict), non-zero = not loaded
        if (string.IsNullOrWhiteSpace(stdout))
        {
            return ServiceStatus.Stopped;
        }
        return stdout.Contains("\"PID\"") ? ServiceStatus.Running : ServiceStatus.Stopped;
    }

    public async Task StartServiceAsync(CancellationToken ct = default)
    {
        await RunProcessAsync("launchctl", ["load", "-w", PlistPath], ct, ignoreExitCode: true)
            .ConfigureAwait(false);
        await RunProcessAsync("launchctl", ["start", PlistLabel], ct, ignoreExitCode: true)
            .ConfigureAwait(false);

        for (var i = 0; i < 60; i++)
        {
            if (await GetServiceStatusAsync(ct).ConfigureAwait(false) == ServiceStatus.Running)
            {
                return;
            }
            await Task.Delay(1000, ct).ConfigureAwait(false);
        }
        throw new TimeoutException("praxiszeit LaunchDaemon did not start within 60 seconds");
    }

    public async Task StopServiceAsync(CancellationToken ct = default)
    {
        await RunProcessAsync("launchctl", ["stop", PlistLabel], ct, ignoreExitCode: true)
            .ConfigureAwait(false);
        await RunProcessAsync("launchctl", ["unload", "-w", PlistPath], ct, ignoreExitCode: true)
            .ConfigureAwait(false);
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
