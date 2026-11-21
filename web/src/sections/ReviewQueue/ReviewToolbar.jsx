import { SearchIcon } from '../../components/Icons/Icons.jsx';
import { PRIORITIES, STATUS_OPTIONS } from '../../utils/constants.js';

export default function ReviewToolbar({
  search,
  onSearch,
  priority,
  onPriority,
  status,
  onStatus,
  count,
}) {
  return (
    <div className="card review-toolbar">
      <div className="review-toolbar__field review-toolbar__field--search">
        <label htmlFor="review-search">Search</label>
        <div className="input-with-icon">
          <SearchIcon aria-hidden="true" />
          <input
            id="review-search"
            type="search"
            placeholder="ID, subject, customer, reason…"
            value={search}
            onChange={(event) => onSearch(event.target.value)}
          />
        </div>
      </div>

      <div className="review-toolbar__field">
        <label htmlFor="review-priority">Priority</label>
        <select
          id="review-priority"
          value={priority}
          onChange={(event) => onPriority(event.target.value)}
        >
          <option value="">All priorities</option>
          {PRIORITIES.map((item) => (
            <option key={item} value={item}>
              {item}
            </option>
          ))}
        </select>
      </div>

      <div className="review-toolbar__field">
        <label htmlFor="review-status">Status</label>
        <select
          id="review-status"
          value={status}
          onChange={(event) => onStatus(event.target.value)}
        >
          <option value="">All statuses</option>
          {STATUS_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </div>

      <div className="review-toolbar__count" role="status">
        <strong>{count}</strong> {count === 1 ? 'ticket' : 'tickets'}
      </div>
    </div>
  );
}
