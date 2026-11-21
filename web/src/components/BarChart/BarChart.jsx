import './BarChart.css';

/** Accessible CSS-only horizontal bar chart. No charting dependency. */
export default function BarChart({ items, valueFormatter = (value) => value, max, label }) {
  const values = items.map((item) => Number(item.value) || 0);
  const ceiling = max != null ? max : Math.max(1, ...values);

  return (
    <ul className="bar-chart" aria-label={label || 'Distribution chart'}>
      {items.map((item, index) => {
        const value = values[index];
        const size = ceiling > 0 ? Math.max(0, Math.min(100, (value / ceiling) * 100)) : 0;
        return (
          <li className="bar-chart__row" key={item.label}>
            <span className="bar-chart__label" title={String(item.label)}>
              {item.label}
            </span>
            <span className="bar-chart__track" aria-hidden="true">
              <span className="bar-chart__fill" style={{ '--bar-size': `${size}%` }} />
            </span>
            <span className="bar-chart__value">{valueFormatter(value)}</span>
          </li>
        );
      })}
    </ul>
  );
}
