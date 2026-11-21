import {
  AnalyticsIcon,
  NewTicketIcon,
  OverviewIcon,
  ReportsIcon,
  ReviewIcon,
} from '../Icons/Icons.jsx';
import './Sidebar.css';

const ICONS = {
  overview: OverviewIcon,
  new: NewTicketIcon,
  analytics: AnalyticsIcon,
  review: ReviewIcon,
  reports: ReportsIcon,
};

export default function Sidebar({ items, active, onSelect }) {
  return (
    <nav className="sidebar" aria-label="Dashboard sections">
      <p className="sidebar__label">Workspace</p>
      <ul className="sidebar__list">
        {items.map((item) => {
          const Icon = ICONS[item.id] || OverviewIcon;
          const isActive = active === item.id;
          return (
            <li key={item.id}>
              <button
                type="button"
                className={`sidebar__link${isActive ? ' is-active' : ''}`}
                aria-current={isActive ? 'page' : undefined}
                onClick={() => onSelect(item.id)}
              >
                <Icon aria-hidden="true" />
                <span>{item.label}</span>
              </button>
            </li>
          );
        })}
      </ul>

      <div className="sidebar__foot">
        <span className="sidebar__foot-title">Dataset taxonomy</span>
        <span>Billing · Technical · Account · Shipping · Other</span>
        <span className="sidebar__foot-note">
          Uncertain tickets are escalated rather than auto-accepted.
        </span>
      </div>
    </nav>
  );
}
