import { useMemo, useState } from 'react';
import api from '../../api.js';
import { useData } from '../../context/DataContext.jsx';
import { useApi } from '../../hooks/useApi.js';
import { normalizeTicket } from '../../utils/format.js';
import SeedButton from '../../components/SeedButton/SeedButton.jsx';
import EmptyState from '../../components/StatePanel/EmptyState.jsx';
import ErrorState from '../../components/StatePanel/ErrorState.jsx';
import { TableSkeleton } from '../../components/LoadingSkeleton/LoadingSkeleton.jsx';
import Pagination from '../../components/Pagination/Pagination.jsx';
import ReviewModal from '../../components/ReviewModal/ReviewModal.jsx';
import ReviewToolbar from './ReviewToolbar.jsx';
import ReviewTable from './ReviewTable.jsx';
import './ReviewQueue.css';

const PAGE_SIZE = 10;

export default function ReviewQueue() {
  const { version, bump } = useData();
  const { data, loading, error, refetch } = useApi(
    (signal) => api.getAllReviewQueue(signal),
    [version]
  );

  const [search, setSearch] = useState('');
  const [priority, setPriority] = useState('');
  const [status, setStatus] = useState('');
  const [page, setPage] = useState(1);
  const [selectedId, setSelectedId] = useState(null);

  const tickets = useMemo(() => (data || []).map(normalizeTicket), [data]);

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    return tickets.filter((ticket) => {
      if (priority && ticket.priority !== priority) return false;
      if (status && ticket.status !== status) return false;
      if (!query) return true;
      return [ticket.id, ticket.subject, ticket.body, ticket.customer, ticket.category, ticket.reviewReason]
        .some((value) => String(value || '').toLowerCase().includes(query));
    });
  }, [tickets, search, priority, status]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const visible = filtered.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);
  const selected = tickets.find((ticket) => ticket.id === selectedId) || null;

  function changeFilter(setter, value) {
    setter(value);
    setPage(1);
  }

  if (loading) {
    return (
      <div className="stack">
        <div className="card review-toolbar" aria-busy="true" aria-label="Loading review filters">
          <div className="skeleton skeleton-filter" />
        </div>
        <TableSkeleton />
      </div>
    );
  }

  if (error) {
    return (
      <ErrorState
        title="Could not load the review queue"
        message={error.message}
        onRetry={refetch}
      />
    );
  }

  return (
    <div className="stack">
      <ReviewToolbar
        search={search}
        onSearch={(value) => changeFilter(setSearch, value)}
        priority={priority}
        onPriority={(value) => changeFilter(setPriority, value)}
        status={status}
        onStatus={(value) => changeFilter(setStatus, value)}
        count={filtered.length}
      />

      <section className="card" aria-labelledby="review-queue-heading">
        <div className="card__header">
          <div>
            <h2 id="review-queue-heading">Tickets requiring review</h2>
            <p>Select a ticket to inspect the original text and apply a correction.</p>
          </div>
        </div>

        {tickets.length === 0 ? (
          <EmptyState
            title="Review queue is empty"
            description="No tickets currently require human review. Process the sample dataset to populate the queue."
            action={<SeedButton size="sm" />}
          />
        ) : filtered.length === 0 ? (
          <EmptyState
            title="No tickets match these filters"
            description="Try a different search term or clear the priority and status filters."
            action={
              <button
                type="button"
                className="btn btn--secondary btn--sm"
                onClick={() => {
                  setSearch('');
                  setPriority('');
                  setStatus('');
                  setPage(1);
                }}
              >
                Clear filters
              </button>
            }
          />
        ) : (
          <ReviewTable tickets={visible} onSelect={setSelectedId} />
        )}
      </section>

      <Pagination
        page={currentPage}
        totalPages={totalPages}
        totalItems={filtered.length}
        onPage={setPage}
      />

      {selected && (
        <ReviewModal
          ticket={selected}
          onClose={() => setSelectedId(null)}
          onSubmitted={() => {
            setSelectedId(null);
            bump();
          }}
        />
      )}
    </div>
  );
}
