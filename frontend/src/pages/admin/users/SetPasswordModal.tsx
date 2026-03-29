import { useState } from 'react';
import FocusTrap from 'focus-trap-react';
import apiClient from '../../../api/client';
import { Key, X } from 'lucide-react';
import { useToast } from '../../../contexts/ToastContext';
import PasswordInput from '../../../components/PasswordInput';
import { getErrorMessage } from '../../../utils/errorMessage';

interface SetPasswordModalProps {
  userId: string;
  userName: string;
  onClose: () => void;
}

export default function SetPasswordModal({ userId, userName, onClose }: SetPasswordModalProps) {
  const toast = useToast();
  const [newPassword, setNewPassword] = useState('');

  const handleSubmit = async () => {
    if (newPassword.length < 10) return;
    try {
      await apiClient.post(`/admin/users/${userId}/set-password`, {
        password: newPassword,
      });
      toast.success('Passwort erfolgreich gesetzt');
      onClose();
    } catch (error: any) {
      toast.error(getErrorMessage(error, 'Fehler beim Setzen des Passworts'));
    }
  };

  return (
    <div
      className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50"
      onClick={onClose}
    >
      <FocusTrap
        focusTrapOptions={{
          allowOutsideClick: true,
          escapeDeactivates: true,
          onDeactivate: onClose,
        }}
      >
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="password-modal-title"
          className="bg-white rounded-xl shadow-2xl max-w-md w-full p-6"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex items-center justify-between mb-4">
            <h3 id="password-modal-title" className="text-xl font-semibold text-gray-900">
              Passwort setzen
            </h3>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-600 transition"
              aria-label="Modal schließen"
            >
              <X size={24} />
            </button>
          </div>

          <div className="mb-4">
            <p className="text-sm text-gray-600 mb-3">
              Neues Passwort für <strong>{userName}</strong>:
            </p>
            <PasswordInput
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              placeholder="Neues Passwort (mind. 10 Zeichen)"
              minLength={10}
              aria-label="Neues Passwort"
              aria-describedby={newPassword.length > 0 && newPassword.length < 10 ? 'pw-error' : 'pw-hint'}
              aria-invalid={newPassword.length > 0 && newPassword.length < 10 ? 'true' : 'false'}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary"
              autoFocus
              onKeyDown={(e) => {
                if (e.key === 'Enter' && newPassword.length >= 10) {
                  handleSubmit();
                }
              }}
            />
            <p id="pw-hint" className="text-xs text-gray-500 mt-1">
              Mind. 10 Zeichen, 1 Großbuchstabe, 1 Kleinbuchstabe, 1 Ziffer
            </p>
            {newPassword.length > 0 && newPassword.length < 10 && (
              <p id="pw-error" role="alert" className="text-xs text-red-500 mt-1">Mindestens 10 Zeichen erforderlich</p>
            )}
          </div>

          <button
            onClick={handleSubmit}
            disabled={newPassword.length < 10}
            className="w-full bg-primary hover:bg-primary-dark text-white px-4 py-3 rounded-lg flex items-center justify-center space-x-2 transition mb-3 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Key size={18} />
            <span>Passwort setzen</span>
          </button>

          <button
            onClick={onClose}
            className="w-full bg-gray-100 hover:bg-gray-200 text-gray-700 px-4 py-2 rounded-lg transition"
          >
            Abbrechen
          </button>
        </div>
      </FocusTrap>
    </div>
  );
}
