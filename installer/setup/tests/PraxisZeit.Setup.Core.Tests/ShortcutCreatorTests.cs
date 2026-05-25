using FluentAssertions;
using PraxisZeit.Setup.Core.Services;
using Xunit;

namespace PraxisZeit.Setup.Core.Tests;

public sealed class ShortcutCreatorTests
{
    [Fact]
    public void Serialize_WritesInternetShortcutWithUrl()
    {
        var content = ShortcutCreator.Serialize("https://localhost/");

        content.Should().Contain("[InternetShortcut]");
        content.Should().Contain("URL=https://localhost/");
    }

    [Theory]
    [InlineData("")]
    [InlineData("   ")]
    [InlineData(null)]
    public void Serialize_RejectsEmptyUrl(string? url)
    {
        var act = () => ShortcutCreator.Serialize(url!);
        act.Should().Throw<ArgumentException>();
    }

    [Fact]
    public void WriteTo_CreatesUrlFileWithExpectedNameAndContent()
    {
        var dir = Path.Combine(Path.GetTempPath(), "pz-shortcut-test-" + Guid.NewGuid().ToString("N"));
        try
        {
            var path = ShortcutCreator.WriteTo(dir, "https://localhost:8443/");

            path.Should().NotBeNull();
            Path.GetFileName(path!).Should().Be("PraxisZeit.url");
            File.Exists(path!).Should().BeTrue();
            File.ReadAllText(path!).Should().Contain("URL=https://localhost:8443/");
        }
        finally
        {
            if (Directory.Exists(dir)) { Directory.Delete(dir, recursive: true); }
        }
    }

    [Fact]
    public void WriteTo_ReturnsNullForEmptyDirectory()
    {
        ShortcutCreator.WriteTo("", "https://localhost/").Should().BeNull();
        ShortcutCreator.WriteTo(null, "https://localhost/").Should().BeNull();
    }
}
