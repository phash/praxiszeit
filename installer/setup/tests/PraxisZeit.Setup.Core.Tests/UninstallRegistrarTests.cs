using FluentAssertions;
using PraxisZeit.Setup.Core.Services;
using Xunit;

namespace PraxisZeit.Setup.Core.Tests;

public sealed class UninstallRegistrarTests
{
    [Fact]
    public void BuildEntries_ContainsAppsAndFeaturesBasics()
    {
        var entries = UninstallRegistrar.BuildEntries(@"C:\PraxisZeit", "1.5.1");

        entries.Should().Contain(e => e.Name == "DisplayName" && e.Data == "PraxisZeit");
        entries.Should().Contain(e => e.Name == "DisplayVersion" && e.Data == "1.5.1");
        entries.Should().Contain(e => e.Name == "Publisher");
        entries.Should().Contain(e => e.Name == "InstallLocation" && e.Data == @"C:\PraxisZeit");
    }

    [Fact]
    public void BuildEntries_UninstallStringPointsToQuotedUninstallBat()
    {
        var entries = UninstallRegistrar.BuildEntries(@"C:\Praxis Zeit", "1.5.1");

        var uninstall = entries.Single(e => e.Name == "UninstallString");
        // Zitiert, weil der Pfad Leerzeichen enthalten kann.
        uninstall.Data.Should().Be("\"C:\\Praxis Zeit\\uninstall.bat\"");
    }

    [Fact]
    public void BuildEntries_NoModifyNoRepairAreDwords()
    {
        var entries = UninstallRegistrar.BuildEntries(@"C:\PraxisZeit", "1.5.1");

        entries.Should().Contain(e => e.Name == "NoModify" && e.Type == "REG_DWORD" && e.Data == "1");
        entries.Should().Contain(e => e.Name == "NoRepair" && e.Type == "REG_DWORD" && e.Data == "1");
    }

    [Fact]
    public void KeyPath_IsUnderHklmUninstall()
    {
        UninstallRegistrar.KeyPath.Should().StartWith(@"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\");
    }
}
