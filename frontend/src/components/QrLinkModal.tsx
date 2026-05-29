import { useEffect } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import { X } from 'lucide-react';

interface QrLinkModalProps {
  open: boolean;
  onClose: () => void;
  /** URL to encode. Defaults to the current origin (the app's own address). */
  url?: string;
}

/**
 * Zeigt einen QR-Code der App-Adresse, damit Mitarbeiter die Seite auf dem
 * Smartphone öffnen können, ohne die URL eintippen zu müssen (einfach mit der
 * Handy-Kamera scannen).
 */
export default function QrLinkModal({ open, onClose, url }: QrLinkModalProps) {
  const target = url ?? window.location.origin;

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Auf dem Smartphone öffnen"
    >
      <div
        className="bg-white rounded-2xl shadow-2xl w-full max-w-xs p-6 text-center"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex justify-end -mt-2 -mr-2">
          <button
            onClick={onClose}
            aria-label="Schließen"
            className="p-1 text-gray-400 hover:text-gray-700 rounded-lg"
          >
            <X size={20} />
          </button>
        </div>
        <h2 className="text-lg font-bold text-gray-900 mb-1">Auf dem Smartphone öffnen</h2>
        <p className="text-sm text-gray-600 mb-4">
          Mit der Kamera des Smartphones scannen — die Adresse muss nicht eingetippt werden.
        </p>
        <div className="flex justify-center mb-4">
          <div className="p-3 bg-white border border-gray-200 rounded-xl">
            <QRCodeSVG value={target} size={200} />
          </div>
        </div>
        <a
          href={target}
          target="_blank"
          rel="noopener noreferrer"
          className="block text-xs text-primary break-all hover:underline"
        >
          {target}
        </a>
      </div>
    </div>
  );
}
