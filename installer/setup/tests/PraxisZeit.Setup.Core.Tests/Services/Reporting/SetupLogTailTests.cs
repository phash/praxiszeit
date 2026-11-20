using System.Text;
using FluentAssertions;
using PraxisZeit.Setup.Core.Services.Reporting;

namespace PraxisZeit.Setup.Core.Tests.Services.Reporting;

public class SetupLogTailTests : IDisposable
{
    private readonly string _dir = Path.Combine(Path.GetTempPath(), $"pz-logtail-{Guid.NewGuid():N}");

    public SetupLogTailTests() => Directory.CreateDirectory(_dir);

    public void Dispose()
    {
        if (Directory.Exists(_dir)) Directory.Delete(_dir, recursive: true);
        GC.SuppressFinalize(this);
    }

    [Fact]
    public void ReadsOnlyLastBytesOfLargeFile()
    {
        var path = Path.Combine(_dir, "big.log");
        var sb = new StringBuilder();
        var i = 0;
        while (sb.Length < 5 * 1024 * 1024)
        {
            sb.Append("12:00:00 Zeile ").Append(i++).Append(' ').Append('x', 80).Append("\r\n");
        }
        sb.Append("12:00:01 FEHLER: letzte Zeile\r\n");
        File.WriteAllText(path, sb.ToString(), new UTF8Encoding(false));

        var lines = SetupLogTail.Read(path, maxLines: 5000, maxBytes: 4096);

        lines.Should().NotBeEmpty();
        lines[^1].Should().Be("12:00:01 FEHLER: letzte Zeile");
        lines.Sum(l => l.Length + 2).Should().BeLessThanOrEqualTo(4096);
        lines[0].Should().StartWith("12:00:00 Zeile ", "the cut-off first line is dropped");
        lines.Should().OnlyContain(l => !l.Contains('\r'));
    }

    [Fact]
    public void KeepsOnlyLastMaxLines()
    {
        var path = Path.Combine(_dir, "many.log");
        File.WriteAllLines(path, Enumerable.Range(0, 500).Select(n => $"Zeile {n}"));

        var lines = SetupLogTail.Read(path);

        lines.Should().HaveCount(200);
        lines[0].Should().Be("Zeile 300");
        lines[^1].Should().Be("Zeile 499");
    }

    [Fact]
    public void MissingFile_ReturnsEmpty()
    {
        SetupLogTail.Read(Path.Combine(_dir, "fehlt.log")).Should().BeEmpty();
        SetupLogTail.Read(null).Should().BeEmpty();
        SetupLogTail.Read("").Should().BeEmpty();
        SetupLogTail.Read(_dir).Should().BeEmpty("a directory is no log file");
    }

    [Fact]
    public void LockedForWrite_StillReadable()
    {
        var path = Path.Combine(_dir, "open.log");
        using var writer = new FileStream(path, FileMode.Create, FileAccess.Write, FileShare.Read);
        var bytes = Encoding.UTF8.GetBytes("12:00:00 eins\n12:00:01 zwei\n");
        writer.Write(bytes);
        writer.Flush();

        SetupLogTail.Read(path).Should().Equal("12:00:00 eins", "12:00:01 zwei");
    }
}
