import { Clock, CheckCircle, XCircle } from 'lucide-react';

// #219: gemeinsame Status-Badge-Konfiguration. Vorher 3x (fast) identisch
// dupliziert in pages/ChangeRequests, pages/admin/ChangeRequests und
// pages/admin/VacationApprovals. `withdrawn` wird nur von VacationApprovals
// genutzt, schadet den anderen aber nicht.
export const STATUS_CONFIG = {
  pending: { label: 'Offen', color: 'bg-yellow-100 text-yellow-800', icon: Clock },
  approved: { label: 'Genehmigt', color: 'bg-green-100 text-green-800', icon: CheckCircle },
  rejected: { label: 'Abgelehnt', color: 'bg-red-100 text-red-800', icon: XCircle },
  withdrawn: { label: 'Zurückgezogen', color: 'bg-gray-100 text-gray-600', icon: XCircle },
} as const;
