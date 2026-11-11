/** Text des Bestätigungsdialogs „Jahresabschluss“ (calc-01, R35). */
export function yearClosingMessage(
  year: number,
  isOpenYear: boolean,
  manualCarryoverCount: number,
): string {
  const next = year + 1;
  const parts: string[] = [];
  if (isOpenYear) {
    parts.push(
      `Achtung: ${year} ist noch nicht zu Ende. Das Soll der verbleibenden Monate wird ohne Ist als Überstunden-Saldo eingefroren, und der Resturlaub ist noch nicht endgültig.`,
    );
  }
  parts.push(
    `Überstunden-Saldo und Resturlaub aller aktiven Mitarbeiter werden berechnet und als Übernahme in ${next} gespeichert. Bestehende Übernahmen für ${next} werden überschrieben.`,
  );
  if (manualCarryoverCount > 0) {
    parts.push(
      manualCarryoverCount === 1
        ? `Davon ist 1 Übernahme von Hand eingetragen; sie wird ebenfalls überschrieben.`
        : `Davon sind ${manualCarryoverCount} Übernahmen von Hand eingetragen; sie werden ebenfalls überschrieben.`,
    );
  }
  parts.push('Fortfahren?');
  return parts.join('\n\n');
}
