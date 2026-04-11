using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Runtime.Versioning;

namespace PraxisZeit.Setup.Core.Platform;

/// <summary>
/// macOS-Implementierung via launchd-Plists + launchctl. Firewall via
/// <c>pfctl</c> (falls noetig — LAN-Deployments brauchen das meistens
/// nicht). Elevation via <c>geteuid() == 0</c>.
/// </summary>
[SupportedOSPlatform("macos")]
public sealed class MacOsPlatform : IPlatform
{
    private const string PlistLabel = "de.praxiszeit.server";
    private const string PlistPath = "/Library/LaunchDaemons/de.praxiszeit.server.plist";
    private const string BackupPlistLabel = "de.praxiszeit.backup";
    private const string BackupPlistPath = "/Library/LaunchDaemons/de.praxiszeit.backup.plist";

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

    public async Task InstallServiceAsync(
        string executablePath,
        string[] arguments,
        string workingDirectory,
        CancellationToken ct = default)
    {
        var programArgsXml = new System.Text.StringBuilder();
        programArgsXml.AppendLine($"      <string>{executablePath}</string>");
        foreach (var arg in arguments)
        {
            programArgsXml.AppendLine($"      <string>{System.Security.SecurityElement.Escape(arg)}</string>");
        }

        var plist = $"""
            <?xml version="1.0" encoding="UTF-8"?>
            <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
            <plist version="1.0">
            <dict>
              <key>Label</key>
              <string>{PlistLabel}</string>
              <key>ProgramArguments</key>
              <array>
            {programArgsXml}
              </array>
              <key>WorkingDirectory</key>
              <string>{workingDirectory}</string>
              <key>RunAtLoad</key>
              <true/>
              <key>KeepAlive</key>
              <true/>
              <key>StandardOutPath</key>
              <string>{workingDirectory}/logs/service-stdout.log</string>
              <key>StandardErrorPath</key>
              <string>{workingDirectory}/logs/service-stderr.log</string>
              <key>EnvironmentVariables</key>
              <dict>
                <key>PYTHONUTF8</key>
                <string>1</string>
              </dict>
              <key>UserName</key>
              <string>praxiszeit</string>
              <key>GroupName</key>
              <string>praxiszeit</string>
            </dict>
            </plist>
            """;

        await File.WriteAllTextAsync(PlistPath, plist, ct).ConfigureAwait(false);
        await RunProcessAsync("chmod", ["644", PlistPath], ct).ConfigureAwait(false);
        await RunProcessAsync("chown", ["root:wheel", PlistPath], ct).ConfigureAwait(false);
    }

    public async Task UninstallServiceAsync(CancellationToken ct = default)
    {
        await StopServiceAsync(ct).ConfigureAwait(false);
        if (File.Exists(PlistPath))
        {
            File.Delete(PlistPath);
        }
    }

    public Task OpenFirewallAsync(int port, CancellationToken ct = default)
    {
        // macOS Application Firewall ist per-App, nicht per-Port. Fuer
        // Server-Usecase ist pfctl zustaendig, aber LAN-Deployments
        // brauchen das typischerweise nicht. Skippen.
        return Task.CompletedTask;
    }

    public Task CloseFirewallAsync(int port, CancellationToken ct = default) => Task.CompletedTask;

    public async Task ScheduleDailyBackupAsync(
        string backupCommand,
        TimeOnly dailyAt,
        CancellationToken ct = default)
    {
        // launchd StartCalendarInterval als zweites Plist
        var plist = $"""
            <?xml version="1.0" encoding="UTF-8"?>
            <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
            <plist version="1.0">
            <dict>
              <key>Label</key>
              <string>{BackupPlistLabel}</string>
              <key>ProgramArguments</key>
              <array>
                <string>/bin/sh</string>
                <string>-c</string>
                <string>{System.Security.SecurityElement.Escape(backupCommand)}</string>
              </array>
              <key>StartCalendarInterval</key>
              <dict>
                <key>Hour</key>
                <integer>{dailyAt.Hour}</integer>
                <key>Minute</key>
                <integer>{dailyAt.Minute}</integer>
              </dict>
              <key>UserName</key>
              <string>praxiszeit</string>
            </dict>
            </plist>
            """;

        await File.WriteAllTextAsync(BackupPlistPath, plist, ct).ConfigureAwait(false);
        await RunProcessAsync("chmod", ["644", BackupPlistPath], ct).ConfigureAwait(false);
        await RunProcessAsync("chown", ["root:wheel", BackupPlistPath], ct).ConfigureAwait(false);
        await RunProcessAsync("launchctl", ["load", "-w", BackupPlistPath], ct, ignoreExitCode: true)
            .ConfigureAwait(false);
    }

    public async Task UnscheduleDailyBackupAsync(CancellationToken ct = default)
    {
        await RunProcessAsync("launchctl", ["unload", "-w", BackupPlistPath], ct, ignoreExitCode: true)
            .ConfigureAwait(false);
        if (File.Exists(BackupPlistPath))
        {
            File.Delete(BackupPlistPath);
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
