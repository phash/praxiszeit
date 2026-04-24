import { useEffect, useState } from 'react';
import { Clock } from 'lucide-react';
import apiClient from '../api/client';
import { useAuthStore } from '../stores/authStore';
import { useSystemStore } from '../stores/systemStore';

interface BillingInfo {
  plan: string;
  subscription_status: string;
  trial_ends_at: string | null;
}

/**
 * Admin-only trial countdown. Hidden on on-prem + for non-admins. Fetches
 * /api/tenant/billing lazily on mount; a 5xx/404 silently hides the banner.
 */
export default function TrialBanner() {
  const user = useAuthStore((s) => s.user);
  const deploymentMode = useSystemStore((s) => s.info?.deployment_mode);
  const [billing, setBilling] = useState<BillingInfo | null>(null);

  useEffect(() => {
    if (user?.role !== 'admin' || deploymentMode !== 'saas') return;
    apiClient
      .get<BillingInfo>('/tenant/billing')
      .then((r) => setBilling(r.data))
      .catch(() => setBilling(null));
  }, [user?.role, deploymentMode]);

  if (!billing || billing.plan !== 'trial' || !billing.trial_ends_at) return null;

  const ends = new Date(billing.trial_ends_at);
  const msLeft = ends.getTime() - Date.now();
  const daysLeft = Math.max(0, Math.ceil(msLeft / (1000 * 60 * 60 * 24)));

  const urgent = daysLeft <= 3;
  return (
    <div
      className={`flex items-center justify-center gap-2 text-sm px-4 py-2 ${
        urgent ? 'bg-amber-100 text-amber-900' : 'bg-blue-50 text-blue-800'
      }`}
    >
      <Clock size={14} />
      <span>
        Trial läuft in <strong>{daysLeft}</strong> {daysLeft === 1 ? 'Tag' : 'Tagen'} ab
        {' '}({ends.toLocaleDateString('de-DE')}).
      </span>
    </div>
  );
}
