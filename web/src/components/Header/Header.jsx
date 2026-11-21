import { useData } from '../../context/DataContext.jsx';
import useHealth from '../../hooks/useHealth.js';
import './Header.css';

const LABELS = {
  checking: 'Checking backend…',
  online: 'Backend connected',
  offline: 'Backend offline',
  unknown: 'Backend status unknown',
};

export default function Header() {
  const { version } = useData();
  const { status, refetch } = useHealth(version);

  return (
    <header className="app-header">
      <div className="app-header__brand">
        <span className="app-header__mark" aria-hidden="true">
          ST
        </span>
        <span className="app-header__titles">
          <span className="app-header__name">Support Ticket Triage</span>
          <span className="app-header__subtitle">Operations dashboard</span>
        </span>
      </div>

      <div className="connection" role="status" aria-live="polite">
        <span className={`connection__dot connection__dot--${status}`} aria-hidden="true" />
        <span className="connection__label">{LABELS[status]}</span>
        {status === 'offline' && (
          <button type="button" className="btn btn--ghost btn--sm" onClick={refetch}>
            Retry
          </button>
        )}
      </div>
    </header>
  );
}
