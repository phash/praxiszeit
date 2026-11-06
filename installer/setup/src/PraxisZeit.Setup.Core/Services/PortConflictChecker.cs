namespace PraxisZeit.Setup.Core.Services;

/// <summary>
/// Reiner Teil der Port-Konfliktpruefung: welche beschrifteten Ports sind
/// in der Menge der belegten Ports? Die Abfrage des Betriebssystems bleibt
/// im ViewModel.
/// </summary>
public static class PortConflictChecker
{
    public static IReadOnlyList<string> Conflicts(
        IReadOnlyDictionary<string, int> labelledPorts, ISet<int> busyPorts)
    {
        return labelledPorts
            .Where(p => busyPorts.Contains(p.Value))
            .Select(p => p.Key)
            .ToList();
    }
}
