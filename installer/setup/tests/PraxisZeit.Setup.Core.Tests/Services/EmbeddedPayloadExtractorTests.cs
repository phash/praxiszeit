using System.Reflection;
using FluentAssertions;
using PraxisZeit.Setup.Core.Services;

namespace PraxisZeit.Setup.Core.Tests.Services;

/// <summary>
/// Verifiziert <see cref="EmbeddedPayloadExtractor"/> end-to-end gegen
/// die in dieser Test-Assembly eingebettete <c>praxiszeit_payload.zip</c>
/// (siehe csproj — gleicher LogicalName wie der Production-Build).
/// </summary>
public sealed class EmbeddedPayloadExtractorTests
{
    private readonly Assembly _testAssembly = typeof(EmbeddedPayloadExtractorTests).Assembly;

    [Fact]
    public void HasEmbeddedPayload_returns_true_when_resource_present()
    {
        var extractor = new EmbeddedPayloadExtractor(_testAssembly);
        extractor.HasEmbeddedPayload.Should().BeTrue();
    }

    [Fact]
    public void HasEmbeddedPayload_returns_false_for_assembly_without_resource()
    {
        // System.Runtime hat sicher keine `praxiszeit_payload.zip` Ressource
        var extractor = new EmbeddedPayloadExtractor(typeof(string).Assembly);
        extractor.HasEmbeddedPayload.Should().BeFalse();
    }

    [Fact]
    public void GetEmbeddedPayloadSize_returns_positive_size()
    {
        var extractor = new EmbeddedPayloadExtractor(_testAssembly);
        extractor.GetEmbeddedPayloadSize().Should().BeGreaterThan(0);
    }

    [Fact]
    public async Task ExtractAsync_unpacks_all_payload_files()
    {
        var extractor = new EmbeddedPayloadExtractor(_testAssembly);
        var tempDir = await extractor.ExtractAsync();

        try
        {
            tempDir.Should().NotBeNullOrEmpty();
            Directory.Exists(tempDir).Should().BeTrue();
            // Zwei Fixture-Files sind im praxiszeit_payload.zip
            File.Exists(Path.Combine(tempDir, "sample-payload-content.txt")).Should().BeTrue();
            File.Exists(Path.Combine(tempDir, "sample-readme.txt")).Should().BeTrue();
            // Inhalt korrekt rausgeschrieben
            (await File.ReadAllTextAsync(Path.Combine(tempDir, "sample-payload-content.txt")))
                .Should().Contain("embedded-test-payload-for-EmbeddedPayloadExtractor");
        }
        finally
        {
            EmbeddedPayloadExtractor.DeleteExtractedPayload(tempDir);
        }
    }

    [Fact]
    public async Task ExtractAsync_creates_path_under_temp_directory()
    {
        var extractor = new EmbeddedPayloadExtractor(_testAssembly);
        var tempDir = await extractor.ExtractAsync();

        try
        {
            tempDir.Should().StartWith(Path.GetTempPath());
            Path.GetFileName(tempDir).Should().StartWith("praxiszeit-setup-");
        }
        finally
        {
            EmbeddedPayloadExtractor.DeleteExtractedPayload(tempDir);
        }
    }

    [Fact]
    public async Task ExtractAsync_reports_progress_to_completion()
    {
        var extractor = new EmbeddedPayloadExtractor(_testAssembly);
        var progressValues = new List<double>();
        var progress = new Progress<double>(v => progressValues.Add(v));

        var tempDir = await extractor.ExtractAsync(progress);
        // Progress<T> dispatched synchron in Tests ohne SynchronizationContext —
        // aber zur Sicherheit kurz warten falls einzelne Reports nachlaufen
        await Task.Delay(50);

        try
        {
            progressValues.Should().NotBeEmpty();
            progressValues.Last().Should().BeApproximately(1.0, 0.001);
        }
        finally
        {
            EmbeddedPayloadExtractor.DeleteExtractedPayload(tempDir);
        }
    }

    [Fact]
    public void ExtractAsync_throws_when_no_payload()
    {
        var extractor = new EmbeddedPayloadExtractor(typeof(string).Assembly);
        var act = () => extractor.ExtractAsync();
        act.Should().ThrowAsync<InvalidOperationException>();
    }

    [Fact]
    public void DeleteExtractedPayload_is_idempotent_on_missing_path()
    {
        // Soll keine Exception werfen
        EmbeddedPayloadExtractor.DeleteExtractedPayload("/path/that/does/not/exist");
        EmbeddedPayloadExtractor.DeleteExtractedPayload(string.Empty);
    }
}
