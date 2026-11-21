import { formatNumber } from '../../utils/format.js';

function RateRow({ label, value, description }) {
  const safe = Math.max(0, Math.min(100, Number(value) || 0));
  return (
    <div className="rate-row">
      <div className="rate-row__head">
        <span>{label}</span>
        <strong>{safe.toFixed(1)}%</strong>
      </div>
      <div className="rate-row__track" aria-hidden="true">
        <span className="rate-row__fill" style={{ '--rate-size': `${safe}%` }} />
      </div>
      <p className="rate-row__description">{description}</p>
    </div>
  );
}

export function SummaryPanel({ counts }) {
  const rows = [
    ['Total input', counts.total],
    ['Processed', counts.processed],
    ['Auto-classified', counts.autoClassified],
    ['Pending review', counts.pendingReview],
    ['Human-reviewed', counts.humanReviewed],
    ['Failed', counts.failed],
  ];

  return (
    <section className="card" aria-labelledby="summary-heading">
      <div className="card__header">
        <h2 id="summary-heading">Processing summary</h2>
      </div>
      <div className="card__body">
        <dl className="summary-list">
          {rows.map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{formatNumber(value)}</dd>
            </div>
          ))}
        </dl>
      </div>
    </section>
  );
}

export function QualityPanel({ coverage, reviewRate, failureRate }) {
  return (
    <section className="card" aria-labelledby="quality-heading">
      <div className="card__header">
        <h2 id="quality-heading">Automation &amp; quality</h2>
      </div>
      <div className="card__body reports-rates">
        <RateRow label="Automation coverage" value={coverage} description="Share of tickets accepted without a person." />
        <RateRow label="Review rate" value={reviewRate} description="Share routed to human review." />
        <RateRow label="Failure rate" value={failureRate} description="Share that could not be processed." />
      </div>
    </section>
  );
}
