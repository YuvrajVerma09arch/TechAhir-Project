import { InboxIcon } from '../Icons/Icons.jsx';
import './StatePanel.css';

export default function EmptyState({ title, description, action }) {
  return (
    <div className="card state-panel" role="status">
      <span className="state-panel__icon">
        <InboxIcon width={22} height={22} />
      </span>
      <h3>{title}</h3>
      <p>{description}</p>
      {action && <div className="state-panel__action">{action}</div>}
    </div>
  );
}
