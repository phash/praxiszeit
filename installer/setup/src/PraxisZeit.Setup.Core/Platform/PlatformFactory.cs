using System.Runtime.InteropServices;

namespace PraxisZeit.Setup.Core.Platform;

/// <summary>
/// Detektiert die aktuelle Plattform und instanziiert die passende
/// <see cref="IPlatform"/>-Implementierung. Wird beim Wizard-Start
/// einmal aufgerufen und per DI in ViewModels + Services injiziert.
/// </summary>
public static class PlatformFactory
{
    public static IPlatform Create()
    {
        if (OperatingSystem.IsWindows())
        {
            return new WindowsPlatform();
        }

        if (OperatingSystem.IsLinux())
        {
            return new LinuxPlatform();
        }

        if (OperatingSystem.IsMacOS())
        {
            return new MacOsPlatform();
        }

        throw new PlatformNotSupportedException(
            $"Unsupported OS: {RuntimeInformation.OSDescription}");
    }
}
