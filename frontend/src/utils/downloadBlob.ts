// Löst einen Browser-Download für Blob-Daten aus und gibt die Object-URL
// anschließend wieder frei. Review 2026-06-23: die früher überall inline
// duplizierte Variante rief revokeObjectURL NIE auf -> jeder Export (teils
// mehrere MB) leakte eine Object-URL für die Lebensdauer der Seite.
export function downloadBlob(data: BlobPart, filename: string, mimeType?: string): void {
  const blob = mimeType ? new Blob([data], { type: mimeType }) : new Blob([data]);
  const url = window.URL.createObjectURL(blob);
  try {
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', filename);
    document.body.appendChild(link);
    link.click();
    link.remove();
  } finally {
    window.URL.revokeObjectURL(url);
  }
}
