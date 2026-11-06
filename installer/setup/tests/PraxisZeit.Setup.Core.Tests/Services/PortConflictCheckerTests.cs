using FluentAssertions;
using PraxisZeit.Setup.Core.Services;

namespace PraxisZeit.Setup.Core.Tests.Services;

public class PortConflictCheckerTests
{
    [Fact]
    public void Returns_label_of_busy_db_port()
    {
        var labelled = new Dictionary<string, int>
        {
            ["HTTPS-Port 443"] = 443,
            ["Datenbank-Port 5432"] = 5432,
        };
        var busy = new HashSet<int> { 5432, 3306 };

        PortConflictChecker.Conflicts(labelled, busy).Should().Equal("Datenbank-Port 5432");
    }

    [Fact]
    public void Returns_empty_when_nothing_busy()
    {
        var labelled = new Dictionary<string, int> { ["HTTPS-Port 443"] = 443 };
        PortConflictChecker.Conflicts(labelled, new HashSet<int> { 22 }).Should().BeEmpty();
    }
}
