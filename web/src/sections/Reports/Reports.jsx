import api from '../../api.js';
import { useData } from '../../context/DataContext.jsx';
import { useApi } from '../../hooks/useApi.js';
import { CATEGORIES, PRIORITIES } from '../../utils/constants.js';
import {
  buildDistributions,
  formatNumber,
  normalizeReport,
  normalizeTicket,
  safeRate,
} from '../../utils/format.js';
import BarChart from '../../components/BarChart/BarChart.jsx';
import SeedButton from '../../components/SeedButton/SeedButton.jsx';
import EmptyState from '../../components/StatePanel/EmptyState.jsx';
import ErrorState from '../../components/StatePanel/ErrorState.jsx';
import { ChartSkeleton, StatsSkeleton } from '../../components/LoadingSkeleton/LoadingSkeleton.jsx';
import { QualityPanel, SummaryPanel } from './ReportStats.jsx';
import ExportPanel from './ExportPanel.jsx';
import './Reports.css';

function countsFromTickets(tickets) {
  const byStatus = (status) => tickets.filter((ticket) => ticket.status === status).length;
  return {
    total: tickets.length,
    processed: tickets.filter((ticket) => ticket.status !== 'failed' && ticket.status !== 'unknown').length,
    autoClassified: byStatus('auto_classified'),
    pendingReview: byStatus('pending_review'),
    humanReviewed: byStatus('human_reviewed'),
    failed: byStatus('failed'),
  };
}

export default function Reports() {
  const { version } = useData();
  const reportRequest = useApi((signal) => api.getReport(signal), [version]);
  const ticketRequest = useApi((signal) => api.getAllTickets(signal), [version]);

  if (reportRequest.loading || ticketRequest.loading) {
    return (
      <div className="stack">
        <StatsSkeleton count={3} />
        <ChartSkeleton />
      </div>
    );
  }

  if (reportRequest.error) {
    return <ErrorState title="Could not load the report" message={reportRequest.error.message} onRetry={reportRequest.refetch} />;
  }
  if (ticketRequest.error) {
    return <ErrorState title="Could not load ticket records" message={ticketRequest.error.message} onRetry={ticketRequest.refetch} />;
  }

  const report = normalizeReport(reportRequest.data);
  const tickets = (ticketRequest.data || []).map(normalizeTicket);
  const fromReport = report.counts.total > 0;
  const counts = fromReport ? report.counts : countsFromTickets(tickets);
  const coverage = fromReport ? report.coverage : safeRate(counts.autoClassified, counts.processed || counts.total);
  const reviewRate = fromReport ? report.reviewRate : safeRate(counts.pendingReview + counts.humanReviewed, counts.total);
  const failureRate = fromReport ? report.failureRate : safeRate(counts.failed, counts.total);
  const distribution = buildDistributions(tickets);
  const categories = fromReport ? report.categories : distribution.categories;
  const priorities = fromReport ? report.priorities : distribution.priorities;
  const reasons = fromReport ? report.escalationReasons : [];

  if (!counts.total) {
    return (
      <EmptyState
        title="No report data yet"
        description="Process the sample dataset to generate a processing report and CSV exports."
        action={<SeedButton />}
      />
    );
  }

  const reasonItems = reasons.map((reason) => ({ label: reason.reason, value: reason.count }));

  return (
    <div className="stack">
      <div className="reports-grid">
        <SummaryPanel counts={counts} />
        <QualityPanel coverage={coverage} reviewRate={reviewRate} failureRate={failureRate} />

        <section className="card" aria-labelledby="distribution-heading">
          <div className="card__header">
            <h2 id="distribution-heading">Distribution snapshot</h2>
          </div>
          <div className="card__body">
            <p className="report-subheading">Categories</p>
            <BarChart
              label="Category distribution"
              items={CATEGORIES.map((category) => ({ label: category, value: categories[category] || 0 }))}
              valueFormatter={formatNumber}
            />
            <p className="report-subheading">Priorities</p>
            <BarChart
              label="Priority distribution"
              items={PRIORITIES.map((priority) => ({ label: priority, value: priorities[priority] || 0 }))}
              valueFormatter={formatNumber}
            />
          </div>
        </section>
      </div>

      <section className="card" aria-labelledby="escalation-heading">
        <div className="card__header">
          <div>
            <h2 id="escalation-heading">Escalation reasons</h2>
            <p>Why tickets were routed to a person</p>
          </div>
        </div>
        <div className="card__body reports-chart">
          {reasonItems.length ? (
            <BarChart label="Escalation reasons" items={reasonItems} valueFormatter={formatNumber} />
          ) : (
            <p className="reports-empty">No escalation reasons were recorded in the report.</p>
          )}
        </div>
      </section>

      <ExportPanel
        tickets={tickets}
        counts={counts}
        coverage={coverage}
        reviewRate={reviewRate}
        failureRate={failureRate}
        distribution={distribution}
      />
    </div>
  );
}
