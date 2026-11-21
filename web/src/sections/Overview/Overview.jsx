import api from '../../api.js';
import { useData } from '../../context/DataContext.jsx';
import { useApi } from '../../hooks/useApi.js';
import { formatNumber, normalizeReport, percentage } from '../../utils/format.js';
import { STATUS_OPTIONS } from '../../utils/constants.js';
import StatCard from '../../components/StatCard/StatCard.jsx';
import SeedButton from '../../components/SeedButton/SeedButton.jsx';
import EmptyState from '../../components/StatePanel/EmptyState.jsx';
import ErrorState from '../../components/StatePanel/ErrorState.jsx';
import { StatsSkeleton } from '../../components/LoadingSkeleton/LoadingSkeleton.jsx';
import StackedBar from '../../components/StackedBar/StackedBar.jsx';
import './Overview.css';

export default function Overview() {
  const { version } = useData();
  const { data, loading, error, refetch } = useApi((signal) => api.getReport(signal), [version]);

  if (loading) {
    return (
      <div className="stack">
        <StatsSkeleton />
        <div className="card card__body">
          <div className="skeleton skeleton-overview-bar" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <ErrorState
        title="Could not load the processing summary"
        message={error.message}
        onRetry={refetch}
      />
    );
  }

  const { counts } = normalizeReport(data);
  const total = counts.total;

  if (!total) {
    return (
      <EmptyState
        title="No tickets processed yet"
        description="Load the provided sample dataset to populate the dashboard. All metrics below come from stored records — nothing is shown until tickets are processed."
        action={<SeedButton />}
      />
    );
  }

  const statusSegments = {
    auto_classified: counts.autoClassified,
    pending_review: counts.pendingReview,
    human_reviewed: counts.humanReviewed,
    failed: counts.failed,
  };
  const statusLegend = STATUS_OPTIONS.reduce((acc, option) => {
    acc[option.value] = option.label;
    return acc;
  }, {});

  return (
    <div className="stack">
      <div className="overview__actions">
        <div>
          <h2>Processing summary</h2>
          <p>Counts are derived from stored ticket records, not estimates.</p>
        </div>
        <SeedButton />
      </div>

      <div className="stats-grid">
        <StatCard label="Total tickets" value={formatNumber(total)} tone="primary" hint="Input dataset" />
        <StatCard
          label="Successfully processed"
          value={formatNumber(counts.processed)}
          tone="info"
          hint={`${percentage(counts.processed, total)} of input`}
        />
        <StatCard
          label="Auto-classified"
          value={formatNumber(counts.autoClassified)}
          tone="success"
          hint={`${percentage(counts.autoClassified, total)} of input`}
        />
        <StatCard
          label="Pending human review"
          value={formatNumber(counts.pendingReview)}
          tone="warning"
          hint={`${percentage(counts.pendingReview, total)} of input`}
        />
        <StatCard
          label="Human-reviewed"
          value={formatNumber(counts.humanReviewed)}
          tone="info"
          hint={`${percentage(counts.humanReviewed, total)} of input`}
        />
        <StatCard
          label="Failed"
          value={formatNumber(counts.failed)}
          tone="danger"
          hint={`${percentage(counts.failed, total)} of input`}
        />
      </div>

      <section className="card" aria-labelledby="lifecycle-heading">
        <div className="card__header">
          <div>
            <h2 id="lifecycle-heading">Lifecycle breakdown</h2>
            <p>Each processed ticket occupies exactly one state.</p>
          </div>
        </div>
        <div className="card__body">
          <StackedBar
            rows={[{ label: 'All tickets', segments: statusSegments }]}
            keys={STATUS_OPTIONS.map((option) => option.value)}
            legend={statusLegend}
          />
        </div>
      </section>
    </div>
  );
}
