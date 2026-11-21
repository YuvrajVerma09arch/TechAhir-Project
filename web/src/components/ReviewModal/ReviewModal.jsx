import { useEffect, useRef, useState } from 'react';
import api from '../../api.js';
import { CATEGORIES, PRIORITIES } from '../../utils/constants.js';
import { formatConfidence, formatDate, text } from '../../utils/format.js';
import './ReviewModal.css';

const FOCUSABLE =
  'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [href], [tabindex]:not([tabindex="-1"])';

export default function ReviewModal({ ticket, onClose, onSubmitted }) {
  const [category, setCategory] = useState(ticket.category);
  const [priority, setPriority] = useState(ticket.priority);
  const [reviewer, setReviewer] = useState('human');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const dialogRef = useRef(null);
  const closeRef = useRef(null);

  const categoryOptions = CATEGORIES.includes(ticket.category)
    ? CATEGORIES
    : [ticket.category, ...CATEGORIES];
  const priorityOptions = PRIORITIES.includes(ticket.priority)
    ? PRIORITIES
    : [ticket.priority, ...PRIORITIES];

  useEffect(() => {
    const previousFocus = document.activeElement;
    const previousOverflow = document.body.style.overflow;
    closeRef.current?.focus();
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previousOverflow;
      if (previousFocus && typeof previousFocus.focus === 'function') previousFocus.focus();
    };
  }, []);

  function handleKeyDown(event) {
    if (event.key === 'Escape') {
      event.preventDefault();
      onClose();
      return;
    }
    if (event.key !== 'Tab') return;
    const nodes = dialogRef.current?.querySelectorAll(FOCUSABLE);
    if (!nodes || nodes.length === 0) return;
    const first = nodes[0];
    const last = nodes[nodes.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await api.submitReview(ticket.id, { category, priority, reviewer });
      onSubmitted();
    } catch (requestError) {
      setError(requestError.message || 'Could not submit the review. Please try again.');
    } finally {
      setSubmitting(false);
    }
  }

  const correction = ticket.correction;

  return (
    <div
      className="modal-overlay"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="review-modal-title"
        ref={dialogRef}
        onKeyDown={handleKeyDown}
      >
        <div className="modal__header">
          <div>
            <h2 id="review-modal-title">Review ticket {ticket.id}</h2>
            <p>The original prediction is read-only. Your correction is stored separately.</p>
          </div>
          <button
            type="button"
            className="btn btn--ghost btn--sm"
            onClick={onClose}
            aria-label="Close review dialog"
            ref={closeRef}
          >
            Close
          </button>
        </div>

        <div className="modal__body">
          <section className="review-block" aria-labelledby="original-ticket-heading">
            <h3 id="original-ticket-heading">Original ticket</h3>
            <dl className="review-meta">
              <div><dt>Customer</dt><dd>{ticket.customer}</dd></div>
              <div><dt>Received</dt><dd>{formatDate(ticket.receivedAt)}</dd></div>
              <div><dt>Subject</dt><dd>{ticket.subject}</dd></div>
            </dl>
            <p className="review-block__label">Message</p>
            <div className="review-body">{ticket.body || '(no message body supplied)'}</div>
          </section>

          <section className="review-block" aria-labelledby="prediction-heading">
            <h3 id="prediction-heading">Predicted classification (read-only)</h3>
            <dl className="review-meta">
              <div><dt>Category</dt><dd>{ticket.category}</dd></div>
              <div><dt>Category confidence</dt><dd>{formatConfidence(ticket.categoryConfidence)}</dd></div>
              <div><dt>Priority</dt><dd>{ticket.priority}</dd></div>
              <div><dt>Priority confidence</dt><dd>{formatConfidence(ticket.priorityConfidence)}</dd></div>
            </dl>
            <p className="review-reason">
              <strong>Why it was escalated:</strong> {ticket.reviewReason}
            </p>
          </section>

          {correction && (
            <section className="review-block review-block--correction" aria-labelledby="correction-heading">
              <h3 id="correction-heading">Human correction on record</h3>
              <dl className="review-meta">
                <div><dt>Category</dt><dd>{text(correction.category)}</dd></div>
                <div><dt>Priority</dt><dd>{text(correction.priority)}</dd></div>
                <div><dt>Reviewer</dt><dd>{text(correction.reviewer)}</dd></div>
                <div><dt>Reviewed at</dt><dd>{formatDate(correction.reviewedAt)}</dd></div>
              </dl>
              {correction.note && <p className="review-reason">{correction.note}</p>}
            </section>
          )}

          <form className="review-form" id="review-form" onSubmit={handleSubmit}>
            <h3>Apply correction</h3>
            <div className="review-form__grid">
              <div className="field">
                <label htmlFor="review-category">Category</label>
                <select id="review-category" value={category} onChange={(event) => setCategory(event.target.value)}>
                  {categoryOptions.map((item) => (
                    <option key={item} value={item}>{item}</option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label htmlFor="review-priority">Priority</label>
                <select id="review-priority" value={priority} onChange={(event) => setPriority(event.target.value)}>
                  {priorityOptions.map((item) => (
                    <option key={item} value={item}>{item}</option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label htmlFor="review-reviewer">Reviewer</label>
                <input
                  id="review-reviewer"
                  type="text"
                  value={reviewer}
                  onChange={(event) => setReviewer(event.target.value)}
                  placeholder="Reviewer name"
                />
              </div>
            </div>
            {error && <p className="form-error" role="alert">{error}</p>}
          </form>
        </div>

        <div className="modal__footer">
          <button type="button" className="btn btn--secondary" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" form="review-form" className="btn btn--primary" disabled={submitting}>
            {submitting ? 'Saving…' : 'Mark reviewed'}
          </button>
        </div>
      </div>
    </div>
  );
}
