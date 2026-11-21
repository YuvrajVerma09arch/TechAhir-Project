import './Pagination.css';

export default function Pagination({ page, totalPages, totalItems, onPage }) {
  if (totalPages <= 1) return null;
  return (
    <nav className="pagination" aria-label="Review queue pagination">
      <span className="pagination__status" role="status">
        Page {page} of {totalPages} · {totalItems} tickets
      </span>
      <div className="pagination__controls">
        <button
          type="button"
          className="btn btn--secondary btn--sm"
          disabled={page <= 1}
          onClick={() => onPage(page - 1)}
          aria-label="Previous page"
        >
          Previous
        </button>
        <button
          type="button"
          className="btn btn--secondary btn--sm"
          disabled={page >= totalPages}
          onClick={() => onPage(page + 1)}
          aria-label="Next page"
        >
          Next
        </button>
      </div>
    </nav>
  );
}
