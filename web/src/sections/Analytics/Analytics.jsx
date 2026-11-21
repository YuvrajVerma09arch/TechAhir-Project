import api from '../../api.js';
import { useData } from '../../context/DataContext.jsx';
import { useApi } from '../../hooks/useApi.js';
import { buildDistributions, formatNumber, normalizeTicket } from '../../utils/format.js';
import { CATEGORIES, PRIORITIES } from '../../utils/constants.js';
import BarChart from '../../components/BarChart/BarChart.jsx';
import StackedBar from '../../components/StackedBar/StackedBar.jsx';
import SeedButton from '../../components/SeedButton/SeedButton.jsx';
import EmptyState from '../../components/StatePanel/EmptyState.jsx';
import ErrorState from '../../components/StatePanel/ErrorState.jsx';
import { ChartSkeleton } from '../../components/LoadingSkeleton/LoadingSkeleton.jsx';

export default function Analytics() {
  const { version } = useData();
  const { data, loading, error, refetch } = useApi(
    (signal) => api.getAllTickets(signal),
    [version]
  );

  if (loading) {
    return (
      <div className="analytics-grid">
        <ChartSkeleton />
        <ChartSkeleton />
      </div>
    );
  }

  if (error) {
    return (
      <ErrorState
        title="Could not load analytics"
        message={error.message}
        onRetry={refetch}
      />
    );
  }

  const tickets = (data || []).map(normalizeTicket);
  if (!tickets.length) {
    return (
      <EmptyState
        title="No tickets to analyse"
        description="Process the sample dataset first. Charts are computed from real stored ticket records."
        action={<SeedButton />}
      />
    );
  }

  const distribution = buildDistributions(tickets);
  const priorityLegend = PRIORITIES.reduce((acc, priority) => {
    acc[priority] = priority;
    return acc;
  }, {});

  return (
    <div className="stack">
      <section className="card" aria-labelledby="priority-analytics-heading">
        <div className="card__header">
          <div>
            <h2 id="priority-analytics-heading">Priority analytics</h2>
            <p>Predicted priority across {formatNumber(tickets.length)} tickets</p>
          </div>
        </div>
        <div className="card__body">
          <BarChart
            label="Tickets by priority"
            items={PRIORITIES.map((priority) => ({
              label: priority,
              value: distribution.priorities[priority],
            }))}
            valueFormatter={formatNumber}
          />
        </div>
      </section>

      <div className="analytics-grid">
        <section className="card" aria-labelledby="category-analytics-heading">
          <div className="card__header">
            <div>
              <h2 id="category-analytics-heading">Category distribution</h2>
              <p>Tickets per predicted category</p>
            </div>
          </div>
          <div className="card__body">
            <BarChart
              label="Tickets by category"
              items={CATEGORIES.map((category) => ({
                label: category,
                value: distribution.categories[category],
              }))}
              valueFormatter={formatNumber}
            />
          </div>
        </section>

        <section className="card" aria-labelledby="matrix-heading">
          <div className="card__header">
            <div>
              <h2 id="matrix-heading">Category × priority</h2>
              <p>Where urgency concentrates by category</p>
            </div>
          </div>
          <div className="card__body">
            <StackedBar
              rows={CATEGORIES.map((category) => ({
                label: category,
                segments: distribution.matrix[category],
              }))}
              keys={PRIORITIES}
              legend={priorityLegend}
            />
          </div>
        </section>
      </div>
    </div>
  );
}
