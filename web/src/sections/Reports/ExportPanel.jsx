import { DownloadIcon } from '../../components/Icons/Icons.jsx';
import { CATEGORIES, PRIORITIES } from '../../utils/constants.js';
import { downloadCsv, toCsv } from '../../utils/format.js';

/** CSV is generated in the browser from data already fetched from the API. */
export default function ExportPanel({ tickets, counts, coverage, reviewRate, failureRate, distribution }) {
  function exportTickets() {
    downloadCsv('tickets.csv', toCsv(tickets, [
      { label: 'id', get: (ticket) => ticket.id },
      { label: 'category', get: (ticket) => ticket.category },
      { label: 'priority', get: (ticket) => ticket.priority },
      { label: 'category_confidence', get: (ticket) => ticket.categoryConfidence },
      { label: 'priority_confidence', get: (ticket) => ticket.priorityConfidence },
      { label: 'requires_review', get: (ticket) => (ticket.requiresReview ? 'yes' : 'no') },
      { label: 'review_reason', get: (ticket) => ticket.reviewReason },
      { label: 'status', get: (ticket) => ticket.status },
      { label: 'customer', get: (ticket) => ticket.customer },
      { label: 'subject', get: (ticket) => ticket.subject },
      { label: 'received_at', get: (ticket) => ticket.receivedAt },
    ]));
  }

  function exportReviewQueue() {
    const rows = tickets.filter((ticket) => ticket.requiresReview || ticket.status === 'pending_review');
    downloadCsv('review_queue.csv', toCsv(rows, [
      { label: 'id', get: (ticket) => ticket.id },
      { label: 'category', get: (ticket) => ticket.category },
      { label: 'priority', get: (ticket) => ticket.priority },
      { label: 'review_reason', get: (ticket) => ticket.reviewReason },
      { label: 'status', get: (ticket) => ticket.status },
    ]));
  }

  function exportMatrix() {
    const rows = CATEGORIES.map((category) => ({
      category,
      ...distribution.matrix[category],
      total: distribution.categories[category],
    }));
    const columns = [
      { label: 'category', key: 'category' },
      ...PRIORITIES.map((priority) => ({ label: priority, key: priority })),
      { label: 'total', key: 'total' },
    ];
    downloadCsv('category_priority_breakdown.csv', toCsv(rows, columns));
  }

  function exportSummary() {
    const rows = [
      ['Total input', counts.total],
      ['Processed', counts.processed],
      ['Auto-classified', counts.autoClassified],
      ['Pending human review', counts.pendingReview],
      ['Human-reviewed', counts.humanReviewed],
      ['Failed', counts.failed],
      ['Automation coverage (%)', coverage.toFixed(1)],
      ['Review rate (%)', reviewRate.toFixed(1)],
      ['Failure rate (%)', failureRate.toFixed(1)],
    ].map(([metric, value]) => ({ metric, value }));
    downloadCsv('processing_summary.csv', toCsv(rows, [
      { label: 'metric', key: 'metric' },
      { label: 'value', key: 'value' },
    ]));
  }

  const exports = [
    { label: 'All tickets', description: 'One row per stored ticket', onClick: exportTickets },
    { label: 'Review queue', description: 'Tickets escalated to a person', onClick: exportReviewQueue },
    { label: 'Category × priority', description: 'Stacked breakdown counts', onClick: exportMatrix },
    { label: 'Processing summary', description: 'Counts and quality rates', onClick: exportSummary },
  ];

  return (
    <section className="card" aria-labelledby="exports-heading">
      <div className="card__header">
        <div>
          <h2 id="exports-heading">CSV exports</h2>
          <p>Generated in the browser from the data loaded above.</p>
        </div>
      </div>
      <ul className="export-list">
        {exports.map((item) => (
          <li key={item.label}>
            <button type="button" className="export-button" onClick={item.onClick}>
              <DownloadIcon aria-hidden="true" />
              <span className="export-button__text">
                <strong>{item.label}</strong>
                <small>{item.description}</small>
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
