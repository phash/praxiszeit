using FluentAssertions;
using PraxisZeit.Setup.Core.Models;

namespace PraxisZeit.Setup.Core.Tests.Services;

public class InstallModeTests
{
    [Theory]
    [InlineData(InstallMode.Update, true)]
    [InlineData(InstallMode.Repair, true)]
    [InlineData(InstallMode.FreshInstall, false)]
    public void Only_fresh_install_rewrites_the_configuration(InstallMode mode, bool keeps)
    {
        mode.KeepsExistingInstallation().Should().Be(keeps);
    }
}
