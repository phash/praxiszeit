import FeedbackDialog from './FeedbackDialog';
import { useReportStore } from '../stores/reportStore';

/**
 * #557: zeigt die Problemmeldung, die der Fehler-Toast („An Entwickler
 * schicken“) angefordert hat. Einmal global unterhalb des Routers montiert.
 */
export default function ReportDialogHost() {
  const request = useReportStore((s) => s.request);
  const closeReport = useReportStore((s) => s.closeReport);
  if (!request) return null;
  const { serverError, initialTitle } = request;
  return (
    <FeedbackDialog
      key={`${serverError.method} ${serverError.path} ${serverError.status} ${initialTitle}`}
      origin="toast"
      serverError={serverError}
      initialTitle={initialTitle}
      onClose={closeReport}
    />
  );
}
