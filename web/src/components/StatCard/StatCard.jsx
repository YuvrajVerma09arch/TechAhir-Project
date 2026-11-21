import './StatCard.css';

export default function StatCard({ label, value, tone = 'default', hint, icon }) {
  return (
    <article className={`card stat-card stat-card--${tone}`}>
      <div className="stat-card__top">
        <h3 className="stat-card__label">{label}</h3>
        {icon && (
          <span className="stat-card__icon" aria-hidden="true">
            {icon}
          </span>
        )}
      </div>
      <p className="stat-card__value">{value}</p>
      {hint && <p className="stat-card__hint">{hint}</p>}
    </article>
  );
}
