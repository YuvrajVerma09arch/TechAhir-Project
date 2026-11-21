import { ArrowRightIcon } from '../../components/Icons/Icons.jsx';
import { PriorityBadge, StatusBadge } from '../../components/Badge/Badge.jsx';
import { formatConfidence } from '../../utils/format.js';

export default function ReviewTable({ tickets, onSelect }) {
  return (
    <div className="review-table-wrap">
      <table className="review-table">
        <caption className="sr-only">Tickets requiring human review</caption>
        <thead>
          <tr>
            <th scope="col">Ticket</th>
            <th scope="col">Category</th>
            <th scope="col">Priority</th>
            <th scope="col">Confidence (cat / pri)</th>
            <th scope="col">Status</th>
            <th scope="col">Escalation reason</th>
          </tr>
        </thead>
        <tbody>
          {tickets.map((ticket) => (
            <tr key={ticket.id}>
              <td>
                <button
                  type="button"
                  className="review-table__open"
                  onClick={() => onSelect(ticket.id)}
                  aria-label={`Review ticket ${ticket.id}: ${ticket.subject}`}
                >
                  <span className="review-table__id">{ticket.id}</span>
                  <span className="review-table__subject">{ticket.subject}</span>
                  <ArrowRightIcon className="review-table__arrow" aria-hidden="true" />
                </button>
              </td>
              <td>{ticket.category}</td>
              <td>
                <PriorityBadge priority={ticket.priority} />
              </td>
              <td className="review-table__confidence">
                {formatConfidence(ticket.categoryConfidence)} / {formatConfidence(ticket.priorityConfidence)}
              </td>
              <td>
                <StatusBadge status={ticket.status} />
              </td>
              <td className="review-table__reason" title={ticket.reviewReason}>
                {ticket.reviewReason}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
