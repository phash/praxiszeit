// frontend/src/pages/admin/UserJournal.tsx
import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import MonthlyJournal from '../../components/MonthlyJournal';
import apiClient from '../../api/client';

export default function UserJournal() {
  const { userId } = useParams<{ userId: string }>();
  const navigate = useNavigate();
  // #311: show whose journal this is in the heading.
  const [name, setName] = useState('');

  useEffect(() => {
    if (!userId) return;
    let cancelled = false;
    apiClient
      .get(`/admin/users/${userId}`)
      .then((res) => {
        if (cancelled) return;
        const full = `${res.data.first_name ?? ''} ${res.data.last_name ?? ''}`.trim();
        setName(full || res.data.username || '');
      })
      .catch(() => {
        /* heading just falls back to "Monatsjournal" */
      });
    return () => {
      cancelled = true;
    };
  }, [userId]);

  if (!userId) return null;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <button
          onClick={() => navigate('/admin/users')}
          className="p-2 rounded-lg hover:bg-gray-100 text-gray-600 transition-colors"
          aria-label="Zurück zur Benutzerverwaltung"
        >
          <ArrowLeft className="w-5 h-5" />
        </button>
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Monatsjournal{name ? `: ${name}` : ''}</h1>
          <p className="text-sm text-gray-500">Zeiteinträge und Abwesenheiten im Überblick</p>
        </div>
      </div>

      <MonthlyJournal userId={userId} isAdminView={true} />
    </div>
  );
}
