import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Eye, LogOut } from 'lucide-react';
import { useAuthStore } from '../stores/authStore';

/**
 * #370: persistent banner shown while an admin views the app as an employee
 * (read-only "Login als …"). Makes the impersonation state unmistakable and
 * offers a one-click return to the admin account.
 */
export default function ImpersonationBanner() {
  const impersonation = useAuthStore((s) => s.impersonation);
  const stopImpersonation = useAuthStore((s) => s.stopImpersonation);
  const navigate = useNavigate();
  const [leaving, setLeaving] = useState(false);

  if (!impersonation) return null;

  const handleReturn = async () => {
    setLeaving(true);
    try {
      await stopImpersonation();
      navigate('/admin/users');
    } finally {
      setLeaving(false);
    }
  };

  return (
    <div
      role="status"
      className="sticky top-0 z-20 flex items-center justify-between gap-3 bg-indigo-600 px-4 py-2 text-sm text-white shadow-md"
    >
      <div className="flex items-center gap-2 min-w-0">
        <Eye size={16} className="shrink-0" />
        <span className="truncate">
          Sie sehen PraxisZeit als <strong>{impersonation.targetName}</strong> — nur Lesen.
        </span>
      </div>
      <button
        type="button"
        onClick={handleReturn}
        disabled={leaving}
        className="shrink-0 inline-flex items-center gap-1.5 rounded-md bg-white/15 px-3 py-1 font-medium hover:bg-white/25 disabled:opacity-50 transition-colors"
      >
        <LogOut size={14} />
        Zurück zu Admin
      </button>
    </div>
  );
}
