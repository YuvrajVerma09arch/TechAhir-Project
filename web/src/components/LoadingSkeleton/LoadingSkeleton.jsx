import './LoadingSkeleton.css';

export function StatsSkeleton({ count = 6 }) {
  return (
    <div className="stats-grid" aria-busy="true" aria-label="Loading summary statistics">
      {Array.from({ length: count }, (_, index) => (
        <div className="card skeleton-card" key={index}>
          <div className="skeleton skeleton-card__label" />
          <div className="skeleton skeleton-card__value" />
          <div className="skeleton skeleton-card__hint" />
        </div>
      ))}
    </div>
  );
}

export function ChartSkeleton() {
  return (
    <div className="card card__body skeleton-chart" aria-busy="true" aria-label="Loading chart">
      {Array.from({ length: 4 }, (_, index) => (
        <div className="skeleton-chart__row" key={index}>
          <div className="skeleton skeleton-chart__label" />
          <div className="skeleton skeleton-chart__track" />
          <div className="skeleton skeleton-chart__value" />
        </div>
      ))}
    </div>
  );
}

export function TableSkeleton({ rows = 6 }) {
  return (
    <div className="card skeleton-table" aria-busy="true" aria-label="Loading table rows">
      {Array.from({ length: rows }, (_, index) => (
        <div className="skeleton-table__row" key={index}>
          <div className="skeleton skeleton-table__cell skeleton-table__cell--wide" />
          <div className="skeleton skeleton-table__cell" />
          <div className="skeleton skeleton-table__cell" />
          <div className="skeleton skeleton-table__cell" />
        </div>
      ))}
    </div>
  );
}
