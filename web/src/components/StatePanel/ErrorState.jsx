import { AlertIcon } from '../Icons/Icons.jsx';
import './StatePanel.css';

export default function ErrorState({
  title = 'Could not load data',
  message,
  onRetry,
}) {
  return (
    <div className="card state-panel" role="alert">
      <span className="state-panel__icon state-panel__icon--error">
        <AlertIcon width={22} height={22} />
      </span>
      <h3>{title}</h3>
      <p>{message || 'An unexpected error occurred while contacting the API.'}</p>
      {onRetry && (
        <div className="state-panel__action">
          <button type="button" className="btn btn--secondary" onClick={onRetry}>
            Try again
          </button>
        </div>
      )}
    </div>
  );
}
