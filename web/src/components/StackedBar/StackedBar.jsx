import './StackedBar.css';

/**
 * Category (or other) × segment stacked breakdown.
 * rows: [{ label, segments: { [key]: count } }]
 * keys: ordered segment keys; segmentClass(key) maps a key to a CSS modifier.
 */
export default function StackedBar({ rows, keys, legend, segmentClass, emptyLabel = 'No data' }) {
  const classFor = segmentClass || ((key) => `stacked-bar__seg--${String(key).toLowerCase()}`);
  const hasData = rows.some((row) => keys.some((key) => (row.segments?.[key] || 0) > 0));

  if (!hasData) {
    return <p className="stacked-bar__empty">{emptyLabel}</p>;
  }

  return (
    <div className="stacked-breakdown">
      <ul className="stacked-list">
        {rows.map((row) => {
          const segments = row.segments || {};
          const rowTotal = keys.reduce((sum, key) => sum + (Number(segments[key]) || 0), 0);
          if (rowTotal === 0) return null;
          const description = keys
            .map((key) => `${legend[key] || key}: ${segments[key] || 0}`)
            .join(', ');

          return (
            <li className="stacked-list__item" key={row.label}>
              <div className="stacked-list__head">
                <span className="stacked-list__label">{row.label}</span>
                <span className="stacked-list__total">{rowTotal} tickets</span>
              </div>
              <div
                className="stacked-bar"
                role="img"
                aria-label={`${row.label} — ${description}`}
              >
                {keys.map((key) => {
                  const value = Number(segments[key]) || 0;
                  if (value === 0) return null;
                  const size = (value / rowTotal) * 100;
                  return (
                    <span
                      className={`stacked-bar__seg ${classFor(key)}`}
                      key={key}
                      style={{ '--seg-size': `${size}%` }}
                      title={`${legend[key] || key}: ${value}`}
                    />
                  );
                })}
              </div>
            </li>
          );
        })}
      </ul>

      <ul className="chart-legend" aria-label="Chart legend">
        {keys.map((key) => (
          <li className="chart-legend__item" key={key}>
            <span className={`chart-legend__swatch ${classFor(key)}`} aria-hidden="true" />
            <span>{legend[key] || key}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
