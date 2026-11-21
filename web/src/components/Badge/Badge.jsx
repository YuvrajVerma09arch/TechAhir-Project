import { STATUS_LABELS } from '../../utils/constants.js';

export function PriorityBadge({ priority }) {
  const value = priority || '—';
  const modifier = String(value).toLowerCase();
  return (
    <span className={`badge badge--${modifier}`}>
      <span className="badge__dot" aria-hidden="true" />
      {value}
    </span>
  );
}

export function StatusBadge({ status }) {
  const value = status || 'unknown';
  return (
    <span className={`badge badge--${value}`}>
      <span className="badge__dot" aria-hidden="true" />
      {STATUS_LABELS[value] || value}
    </span>
  );
}
