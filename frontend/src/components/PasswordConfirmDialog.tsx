import { useState } from 'react';
import { KeyRound } from 'lucide-react';
import FocusTrap from 'focus-trap-react';
import PasswordInput from './PasswordInput';

/**
 * Audit 2026-11-07 (S1-02/S1-09): Passwort-Rückfrage vor einer heiklen Aktion
 * (Sicherung herunterladen, Zwei-Faktor einer anderen Person zurücksetzen).
 * Der Server prüft das Passwort mit derselben Sperre wie die Anmeldung; Fehler
 * zeigt die aufrufende Seite (Toast) an, der Dialog bleibt dann offen.
 */
interface PasswordConfirmDialogProps {
  isOpen: boolean;
  title: string;
  message: string;
  confirmLabel: string;
  onSubmit: (password: string) => Promise<boolean>;
  onCancel: () => void;
}

export default function PasswordConfirmDialog({
  isOpen, title, message, confirmLabel, onSubmit, onCancel,
}: PasswordConfirmDialogProps) {
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);

  if (!isOpen) return null;

  const close = () => {
    setPassword('');
    onCancel();
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!password || busy) return;
    setBusy(true);
    try {
      const ok = await onSubmit(password);
      if (ok) setPassword('');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-10000 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/50" onClick={close} aria-hidden="true" />
      <FocusTrap focusTrapOptions={{ escapeDeactivates: true, onDeactivate: close, allowOutsideClick: true }}>
        <form
          role="dialog"
          aria-modal="true"
          aria-labelledby="password-confirm-title"
          onSubmit={submit}
          className="relative bg-white rounded-xl shadow-2xl max-w-md w-full mx-4 p-6"
        >
          <div className="flex items-start space-x-4">
            <div className="shrink-0 w-10 h-10 rounded-full flex items-center justify-center bg-blue-100 text-blue-600" aria-hidden="true">
              <KeyRound size={20} />
            </div>
            <div className="flex-1">
              <h3 id="password-confirm-title" className="text-lg font-semibold text-gray-900">{title}</h3>
              <p className="mt-2 text-sm text-gray-600 whitespace-pre-line">{message}</p>
              <label htmlFor="password-confirm-input" className="block mt-4 text-sm font-medium text-gray-700">
                Ihr Passwort
              </label>
              <PasswordInput
                id="password-confirm-input"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                autoFocus
                className="mt-1 w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
              />
            </div>
          </div>
          <div className="mt-6 flex justify-end space-x-3">
            <button
              type="button"
              onClick={close}
              className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50"
            >
              Abbrechen
            </button>
            <button
              type="submit"
              disabled={!password || busy}
              className="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {confirmLabel}
            </button>
          </div>
        </form>
      </FocusTrap>
    </div>
  );
}
