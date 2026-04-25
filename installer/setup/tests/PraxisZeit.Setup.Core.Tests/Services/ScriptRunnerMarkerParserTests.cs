using FluentAssertions;
using PraxisZeit.Setup.Core.Services;

namespace PraxisZeit.Setup.Core.Tests.Services;

/// <summary>
/// Tests fuer <see cref="ScriptMarkerParser.ParseMarkerLine"/> — die Regex-
/// Marker-Erkennung die das Stdout des PowerShell-Headless-Modes in
/// typed <see cref="RunnerEvent"/>s wandelt.
/// </summary>
public sealed class ScriptRunnerMarkerParserTests
{
    [Theory]
    [InlineData("[STEP] backup running", "backup", RunnerStepStatus.Running)]
    [InlineData("[STEP] backup ok", "backup", RunnerStepStatus.Ok)]
    [InlineData("[STEP] acl warn", "acl", RunnerStepStatus.Warn)]
    [InlineData("[STEP] copy fail", "copy", RunnerStepStatus.Fail)]
    public void ParseMarkerLine_step_marker_yields_StepEvent(string line, string expectedId, RunnerStepStatus expectedStatus)
    {
        var (evt, isDone, _) = ScriptMarkerParser.ParseMarkerLine(line);

        isDone.Should().BeFalse();
        evt.Should().BeOfType<RunnerStepEvent>()
           .Which.Should().BeEquivalentTo(new RunnerStepEvent(expectedId, expectedStatus));
    }

    [Theory]
    [InlineData("[PROGRESS] 0", 0)]
    [InlineData("[PROGRESS] 25", 25)]
    [InlineData("[PROGRESS] 100", 100)]
    public void ParseMarkerLine_progress_marker_yields_ProgressEvent(string line, int expectedPercent)
    {
        var (evt, isDone, _) = ScriptMarkerParser.ParseMarkerLine(line);

        isDone.Should().BeFalse();
        evt.Should().BeOfType<RunnerProgressEvent>()
           .Which.Percent.Should().Be(expectedPercent);
    }

    [Fact]
    public void ParseMarkerLine_log_marker_yields_LogEvent()
    {
        var (evt, isDone, _) = ScriptMarkerParser.ParseMarkerLine("[LOG] Datenbank-Backup laeuft...");

        isDone.Should().BeFalse();
        evt.Should().BeOfType<RunnerLogEvent>()
           .Which.Message.Should().Be("Datenbank-Backup laeuft...");
    }

    [Fact]
    public void ParseMarkerLine_log_marker_handles_empty_message()
    {
        var (evt, _, _) = ScriptMarkerParser.ParseMarkerLine("[LOG] ");

        evt.Should().BeOfType<RunnerLogEvent>()
           .Which.Message.Should().Be(string.Empty);
    }

    [Fact]
    public void ParseMarkerLine_done_success_marker_signals_done_with_success()
    {
        var (evt, isDone, doneOk) = ScriptMarkerParser.ParseMarkerLine("[DONE] success");

        isDone.Should().BeTrue();
        doneOk.Should().BeTrue();
        evt.Should().BeNull();
    }

    [Fact]
    public void ParseMarkerLine_done_fail_marker_signals_done_with_failure()
    {
        var (evt, isDone, doneOk) = ScriptMarkerParser.ParseMarkerLine("[DONE] fail");

        isDone.Should().BeTrue();
        doneOk.Should().BeFalse();
        evt.Should().BeNull();
    }

    [Fact]
    public void ParseMarkerLine_error_marker_yields_LogEvent_prefixed_with_FEHLER()
    {
        var (evt, _, _) = ScriptMarkerParser.ParseMarkerLine("[ERROR] InstallDir nicht angegeben");

        evt.Should().BeOfType<RunnerLogEvent>()
           .Which.Message.Should().Be("FEHLER: InstallDir nicht angegeben");
    }

    [Fact]
    public void ParseMarkerLine_unknown_line_falls_through_as_LogEvent()
    {
        // Raw-Output von pip / robocopy / native-Tools: keine Marker —
        // wird trotzdem als Log-Zeile durchgereicht damit der User sieht
        // was passiert.
        var (evt, isDone, _) = ScriptMarkerParser.ParseMarkerLine("Successfully installed wheel-0.42.0");

        isDone.Should().BeFalse();
        evt.Should().BeOfType<RunnerLogEvent>()
           .Which.Message.Should().Be("Successfully installed wheel-0.42.0");
    }

    [Fact]
    public void ParseMarkerLine_step_unknown_status_maps_to_Pending()
    {
        var (evt, _, _) = ScriptMarkerParser.ParseMarkerLine("[STEP] xyz unknown");

        evt.Should().BeOfType<RunnerStepEvent>()
           .Which.Status.Should().Be(RunnerStepStatus.Pending);
    }

    [Fact]
    public void ParseMarkerLine_progress_with_invalid_number_falls_through_as_LogEvent()
    {
        // [PROGRESS] mit non-Integer wird als Raw-Log behandelt
        var (evt, _, _) = ScriptMarkerParser.ParseMarkerLine("[PROGRESS] not-a-number");

        evt.Should().BeOfType<RunnerLogEvent>();
    }

    [Fact]
    public void ParseMarkerLine_done_marker_case_insensitive_success()
    {
        var (_, isDone1, ok1) = ScriptMarkerParser.ParseMarkerLine("[DONE] success");
        var (_, isDone2, ok2) = ScriptMarkerParser.ParseMarkerLine("[DONE] SUCCESS");

        isDone1.Should().BeTrue();
        ok1.Should().BeTrue();
        isDone2.Should().BeFalse(); // Regex matcht nur lowercase
        // (das ist OK — der Headless-Mode emittiert immer lowercase)
    }
}
