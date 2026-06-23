import { useEffect, useState } from 'react';
import { CreditCard, ArrowUpCircle, AlertTriangle, Download, FileText, Pause, Trash2, UserCheck } from 'lucide-react';
import apiClient from '../../api/client';
import { getErrorMessage } from '../../utils/errorMessage';
import { safeHttpUrl } from '../../utils/url';
import { useConfirm } from '../../hooks/useConfirm';
import ConfirmDialog from '../../components/ConfirmDialog';

interface BillingInfo {
  id: string;
  plan: 'trial' | 'starter' | 'pro' | 'enterprise';
  subscription_status: 'active' | 'past_due' | 'canceled' | 'suspended';
  trial_ends_at: string | null;
  stripe_customer_id: string | null;
  billing_email: string | null;
  company_name: string | null;
  vat_id: string | null;
  country: string | null;
}


interface UsageInfo {
  plan: string;
  used_seats: number;
  seat_limit: number | null;
  features: string[];
}

interface Invoice {
  id: string;
  stripe_invoice_id: string;
  amount_cents: number;
  currency: string;
  status: string;
  paid_at: string | null;
  created_at: string;
  hosted_invoice_url: string | null;
}

export default function Billing() {
  const [info, setInfo] = useState<BillingInfo | null>(null);
  const [usage, setUsage] = useState<UsageInfo | null>(null);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const { confirmState, confirm, handleConfirm, handleCancel } = useConfirm();

  useEffect(() => {
    void refresh();
  }, []);

  async function suspendAccount() {
    try {
      await apiClient.post('/tenant/suspend');
      await refresh();
    } catch (err: any) {
      setError(getErrorMessage(err, 'Pausieren fehlgeschlagen'));
    }
  }

  async function requestDeletion() {
    try {
      await apiClient.post('/tenant/request-deletion');
      await refresh();
    } catch (err: any) {
      setError(getErrorMessage(err, 'Löschantrag fehlgeschlagen'));
    }
  }

  async function refresh() {
    setLoading(true);
    try {
      const [b, u, i] = await Promise.all([
        apiClient.get<BillingInfo>('/tenant/billing'),
        apiClient.get<UsageInfo>('/tenant/usage'),
        apiClient.get<Invoice[]>('/tenant/invoices'),
      ]);
      setInfo(b.data);
      setUsage(u.data);
      setInvoices(i.data);
    } catch (err: any) {
      setError(getErrorMessage(err, 'Fehler beim Laden der Abrechnung'));
    } finally {
      setLoading(false);
    }
  }

  async function upgrade(plan: 'starter' | 'pro', yearly: boolean) {
    try {
      const { data } = await apiClient.post<{ url: string }>('/billing/checkout', {
        plan,
        yearly,
        success_url: `${window.location.origin}/admin/billing?success=1`,
        cancel_url: `${window.location.origin}/admin/billing?canceled=1`,
      });
      const safeUrl = safeHttpUrl(data.url);  // Review 2026-06-23: kein offener Redirect
      if (safeUrl) window.location.href = safeUrl;
      else setError('Ungültige Weiterleitungs-URL vom Server erhalten.');
    } catch (err: any) {
      setError(getErrorMessage(err, 'Checkout fehlgeschlagen'));
    }
  }

  async function openPortal() {
    try {
      const { data } = await apiClient.post<{ url: string }>('/billing/portal', {
        return_url: `${window.location.origin}/admin/billing`,
      });
      const safeUrl = safeHttpUrl(data.url);  // Review 2026-06-23: kein offener Redirect
      if (safeUrl) window.location.href = safeUrl;
      else setError('Ungültige Weiterleitungs-URL vom Server erhalten.');
    } catch (err: any) {
      setError(getErrorMessage(err, 'Kundenportal nicht erreichbar'));
    }
  }

  if (loading) return <p className="p-6 text-sm text-gray-600">Laden…</p>;
  if (!info) return <p className="p-6 text-sm text-red-600">{error || 'Keine Daten verfügbar.'}</p>;

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <ConfirmDialog
        isOpen={confirmState.isOpen}
        title={confirmState.title}
        message={confirmState.message}
        confirmLabel={confirmState.confirmLabel}
        variant={confirmState.variant}
        onConfirm={handleConfirm}
        onCancel={handleCancel}
      />
      <div className="flex items-center gap-3">
        <CreditCard className="text-primary" />
        <h1 className="text-2xl font-semibold">Abrechnung</h1>
      </div>

      {info.subscription_status === 'past_due' && (
        <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 flex items-start gap-2 text-sm">
          <AlertTriangle className="text-amber-700 mt-0.5" size={18} />
          <div>
            <p className="font-medium text-amber-900">Letzte Zahlung fehlgeschlagen</p>
            <p className="text-amber-800">Bitte aktualisiere deine Zahlungsmethode im Kundenportal.</p>
          </div>
        </div>
      )}

      {info.subscription_status === 'suspended' && (
        <div className="rounded-lg border border-red-300 bg-red-50 p-4 flex items-start gap-2 text-sm">
          <AlertTriangle className="text-red-700 mt-0.5" size={18} />
          <div>
            <p className="font-medium text-red-900">Account gesperrt</p>
            <p className="text-red-800">
              Der Schreibzugriff ist deaktiviert. Bestehende Daten bleiben lesbar und
              exportierbar (§16 ArbZG). Zahlungsmethode aktualisieren, um wieder freizuschalten.
            </p>
          </div>
        </div>
      )}

      <section className="bg-white rounded-xl shadow-card p-6 space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-medium">Aktueller Plan</h2>
            <p className="text-2xl font-semibold mt-1 capitalize">{info.plan}</p>
            <p className="text-sm text-gray-600 mt-1">
              Status: <span className="font-medium">{info.subscription_status}</span>
            </p>
            {info.trial_ends_at && info.plan === 'trial' && (
              <p className="text-xs text-gray-500 mt-1">
                Trial endet am {new Date(info.trial_ends_at).toLocaleDateString('de-DE')}
              </p>
            )}
          </div>
          {info.stripe_customer_id && (
            <button
              onClick={openPortal}
              className="px-4 py-2 bg-gray-100 hover:bg-gray-200 rounded-lg text-sm"
            >
              Kundenportal
            </button>
          )}
        </div>

        {usage && (
          <div className="pt-3 border-t border-gray-100">
            <div className="flex items-center justify-between text-sm">
              <span className="text-gray-600">Sitze</span>
              <span className="font-medium">
                {usage.used_seats}
                {usage.seat_limit !== null && <span className="text-gray-500"> / {usage.seat_limit}</span>}
                {usage.seat_limit === null && <span className="text-gray-500"> / ∞</span>}
              </span>
            </div>
            {usage.seat_limit !== null && (
              <div className="mt-1 h-2 bg-gray-100 rounded-sm overflow-hidden">
                <div
                  className={`h-full ${
                    usage.used_seats >= usage.seat_limit ? 'bg-red-500' :
                    usage.used_seats >= usage.seat_limit * 0.8 ? 'bg-amber-500' :
                    'bg-primary'
                  }`}
                  style={{ width: `${Math.min(100, (usage.used_seats / usage.seat_limit) * 100)}%` }}
                />
              </div>
            )}
          </div>
        )}
      </section>

      {(info.plan === 'trial' || info.plan === 'starter') && (
        <section className="bg-white rounded-xl shadow-card p-6">
          <h2 className="text-lg font-medium mb-4">Upgrade</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {info.plan === 'trial' && (
              <button
                onClick={() => upgrade('starter', false)}
                className="flex items-center gap-2 p-4 border border-gray-200 rounded-lg hover:border-primary hover:bg-primary/5 text-left"
              >
                <ArrowUpCircle size={20} className="text-primary" />
                <div>
                  <p className="font-medium">Starter</p>
                  <p className="text-sm text-gray-500">5 Sitze, monatlich</p>
                </div>
              </button>
            )}
            <button
              onClick={() => upgrade('pro', false)}
              className="flex items-center gap-2 p-4 border border-gray-200 rounded-lg hover:border-primary hover:bg-primary/5 text-left"
            >
              <ArrowUpCircle size={20} className="text-primary" />
              <div>
                <p className="font-medium">Pro</p>
                <p className="text-sm text-gray-500">25 Sitze, monatlich</p>
              </div>
            </button>
          </div>
        </section>
      )}

      <section className="bg-white rounded-xl shadow-card p-6">
        <h2 className="text-lg font-medium mb-4">Dokumente &amp; Export</h2>
        <div className="flex flex-wrap gap-3">
          <button
            onClick={() => window.open('/api/tenant/export', '_blank')}
            className="flex items-center gap-2 px-3 py-2 bg-gray-100 hover:bg-gray-200 rounded-lg text-sm"
          >
            <Download size={16} /> Daten-Export (JSON)
          </button>
          <button
            onClick={() => window.open('/api/tenant/avv', '_blank')}
            className="flex items-center gap-2 px-3 py-2 bg-gray-100 hover:bg-gray-200 rounded-lg text-sm"
          >
            <FileText size={16} /> AVV (Entwurf, PDF)
          </button>
        </div>
      </section>

      <section className="bg-white rounded-xl shadow-card p-6 border border-red-200">
        <h2 className="text-lg font-medium mb-2 text-red-700 flex items-center gap-2">
          <AlertTriangle size={18} /> Gefahrenzone
        </h2>
        <p className="text-xs text-gray-500 mb-4">
          Schreibzugriffe werden nach Pause gesperrt. Nach Löschantrag werden die
          personenbezogenen Daten nach 30 Tagen anonymisiert. Arbeitszeitdaten bleiben
          für 2 Jahre gemäß §16 ArbZG aufbewahrt.
        </p>
        <div className="flex flex-wrap gap-3">
          <button
            onClick={() =>
              confirm({
                title: 'Account pausieren',
                message: 'Account nach 7 Tagen pausieren? Schreibzugriffe werden anschließend gesperrt.',
                confirmLabel: 'Sperren',
                variant: 'danger',
                onConfirm: suspendAccount,
              })
            }
            className="flex items-center gap-2 px-3 py-2 border border-amber-300 text-amber-800 hover:bg-amber-50 rounded-lg text-sm"
          >
            <Pause size={16} /> Account pausieren
          </button>
          <button
            onClick={() =>
              confirm({
                title: 'Account löschen',
                message: 'Account nach 30 Tagen löschen? Die personenbezogenen Daten werden anonymisiert.',
                confirmLabel: 'Löschen & anonymisieren',
                variant: 'danger',
                onConfirm: requestDeletion,
              })
            }
            className="flex items-center gap-2 px-3 py-2 border border-red-300 text-red-700 hover:bg-red-50 rounded-lg text-sm"
          >
            <Trash2 size={16} /> Account löschen
          </button>
        </div>
      </section>

      <section className="bg-white rounded-xl shadow-card p-6">
        <h2 className="text-lg font-medium mb-4 flex items-center gap-2">
          <UserCheck size={18} /> Rechnungen
        </h2>
        {invoices.length === 0 ? (
          <p className="text-sm text-gray-500">Noch keine Rechnungen.</p>
        ) : (
          <ul className="divide-y">
            {invoices.map((inv) => (
              <li key={inv.id} className="py-3 flex items-center justify-between text-sm">
                <div>
                  <p>{new Date(inv.created_at).toLocaleDateString('de-DE')}</p>
                  <p className="text-xs text-gray-500">
                    {(inv.amount_cents / 100).toFixed(2)} {inv.currency.toUpperCase()} · {inv.status}
                  </p>
                </div>
                {safeHttpUrl(inv.hosted_invoice_url) && (
                  <a
                    href={safeHttpUrl(inv.hosted_invoice_url) ?? undefined}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-primary hover:underline"
                  >
                    öffnen
                  </a>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      {error && <p className="text-sm text-red-600">{error}</p>}
    </div>
  );
}
