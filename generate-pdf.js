const { mdToPdf } = require('md-to-pdf');
const path = require('path');

async function generatePDF() {
  console.log('🔄 Generiere PDF aus HANDBUCH.md...\n');

  const inputFile = path.join(__dirname, 'HANDBUCH-V3.md');
  const outputFile = path.join(__dirname, 'PraxisZeit-Handbuch-V3.pdf');

  try {
    const pdf = await mdToPdf(
      { path: inputFile },
      {
        dest: outputFile,
        launch_options: { headless: true },
        pdf_options: {
          format: 'A4',
          margin: {
            top: '20mm',
            right: '20mm',
            bottom: '20mm',
            left: '20mm'
          },
          printBackground: true,
          displayHeaderFooter: true,
          headerTemplate: '<div></div>',
          footerTemplate: `
            <div style="font-size: 9px; text-align: center; width: 100%; color: #666; padding: 0 20mm;">
              <span class="pageNumber"></span> / <span class="totalPages"></span>
            </div>
          `
        },
        css: `
          body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            font-size: 11pt;
            line-height: 1.6;
            color: #333;
            max-width: 100%;
          }
          h1 {
            font-size: 28pt;
            font-weight: bold;
            margin-top: 20px;
            margin-bottom: 20px;
            page-break-after: avoid;
            color: #1a1a1a;
            border-bottom: 3px solid #2563EB;
            padding-bottom: 10px;
          }
          h2 {
            font-size: 20pt;
            font-weight: bold;
            margin-top: 30px;
            margin-bottom: 15px;
            page-break-after: avoid;
            color: #2563EB;
          }
          h3 {
            font-size: 14pt;
            font-weight: bold;
            margin-top: 20px;
            margin-bottom: 10px;
            page-break-after: avoid;
            color: #1a1a1a;
          }
          h4 {
            font-size: 12pt;
            font-weight: bold;
            margin-top: 15px;
            margin-bottom: 8px;
            page-break-after: avoid;
            color: #374151;
          }
          p {
            margin-bottom: 10px;
            text-align: justify;
          }
          ul, ol {
            margin-bottom: 10px;
            padding-left: 20px;
          }
          li {
            margin-bottom: 5px;
          }
          code {
            background-color: #f3f4f6;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: 'Courier New', monospace;
            font-size: 10pt;
            color: #dc2626;
          }
          pre {
            background-color: #f9fafb;
            border: 1px solid #e5e7eb;
            border-radius: 5px;
            padding: 12px;
            overflow-x: auto;
            margin-bottom: 15px;
            page-break-inside: avoid;
          }
          pre code {
            background-color: transparent;
            padding: 0;
            color: #1f2937;
          }
          table {
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 15px;
            font-size: 10pt;
            page-break-inside: avoid;
          }
          th {
            background-color: #2563EB;
            color: white;
            padding: 8px;
            text-align: left;
            font-weight: bold;
          }
          td {
            border: 1px solid #e5e7eb;
            padding: 8px;
          }
          tr:nth-child(even) {
            background-color: #f9fafb;
          }
          blockquote {
            border-left: 4px solid #2563EB;
            padding-left: 15px;
            margin-left: 0;
            color: #6b7280;
            font-style: italic;
          }
          hr {
            border: none;
            border-top: 2px solid #e5e7eb;
            margin: 30px 0;
          }
          .page-break {
            page-break-after: always;
          }
          strong {
            color: #1a1a1a;
          }
          em {
            color: #374151;
          }
          a {
            color: #2563EB;
            text-decoration: none;
          }
          a:hover {
            text-decoration: underline;
          }
        `
      }
    );

    if (pdf) {
      console.log('✅ PDF erfolgreich erstellt!');
      console.log(`📄 Datei: ${outputFile}`);
      console.log(`📏 Größe: ${(require('fs').statSync(outputFile).size / 1024 / 1024).toFixed(2)} MB\n`);
    }
  } catch (error) {
    console.error('❌ Fehler beim Generieren des PDFs:', error);
    process.exit(1);
  }
}

generatePDF();
