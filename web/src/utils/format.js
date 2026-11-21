import { CATEGORIES, PRIORITIES } from './constants.js';

/** Return the first defined, non-null value at any of the given dot paths. */
export function pick(obj, keys, fallback = undefined) {
  if (!obj || typeof obj !== 'object') return fallback;
  for (const key of keys) {
    const value = key.split('.').reduce(
      (acc, part) => (acc == null ? undefined : acc[part]),
      obj
    );
    if (value !== undefined && value !== null) return value;
  }
  return fallback;
}

export function toNumber(value, fallback = 0) {
  const n = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(n) ? n : fallback;
}

export function formatNumber(value) {
  return new Intl.NumberFormat('en-US').format(toNumber(value, 0));
}

export function percentage(part, total, digits = 1) {
  const t = toNumber(total, 0);
  if (t <= 0) return '0%';
  return `${((toNumber(part, 0) / t) * 100).toFixed(digits)}%`;
}

export function safeRate(part, total) {
  const t = toNumber(total, 0);
  return t > 0 ? (toNumber(part, 0) / t) * 100 : 0;
}

/** Accept 0.42 or 42 and return a 0–100 number. */
export function percentValue(value) {
  let n = toNumber(value, 0);
  if (n > 0 && n <= 1) n *= 100;
  return Math.max(0, Math.min(100, n));
}

export function formatConfidence(value) {
  if (value === undefined || value === null || value === '') return '—';
  const n = toNumber(value, NaN);
  return Number.isFinite(n) ? n.toFixed(2) : String(value);
}

export function formatDate(value) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function text(value, fallback = '—') {
  return value === undefined || value === null || value === '' ? fallback : String(value);
}

function extractCorrection(raw) {
  if (!raw || typeof raw !== 'object') return null;
  const dedicated = raw.correction && typeof raw.correction === 'object' ? raw.correction : null;

  const category = pick(
    dedicated || raw,
    dedicated
      ? ['category', 'corrected_category', 'human_category', 'final_category']
      : ['corrected_category', 'human_category', 'final_category'],
    null
  );
  const priority = pick(
    dedicated || raw,
    dedicated
      ? ['priority', 'corrected_priority', 'human_priority', 'final_priority']
      : ['corrected_priority', 'human_priority', 'final_priority'],
    null
  );
  const reviewer = pick(dedicated || raw, ['reviewer', 'reviewed_by'], null);
  const reviewedAt = pick(dedicated || raw, ['reviewed_at', 'reviewedAt'], null);
  const note = pick(dedicated || raw, ['review_note', 'note', 'comment'], null);

  if (category == null && priority == null && reviewer == null) return null;
  return { category, priority, reviewer, reviewedAt, note };
}

/** Defensively normalise any ticket/prediction record coming from the API. */
export function normalizeTicket(raw = {}) {
  const reasons = Array.isArray(raw?.reasons) ? raw.reasons.join('; ') : null;
  return {
    id: text(pick(raw, ['ticket_id', 'id', 'ID']), '—'),
    // The API stores immutable original predictions in `original_*` fields and
    // keeps corrected values in `category`/`priority`. Prefer the originals so
    // the review modal never presents a correction as a prediction.
    category: text(pick(raw, ['original_category', 'category', 'predicted_category']), 'Other'),
    priority: text(pick(raw, ['original_priority', 'priority', 'predicted_priority']), 'Medium'),
    categoryConfidence: pick(
      raw,
      ['original_category_confidence', 'category_confidence', 'categoryConfidence'],
      null
    ),
    priorityConfidence: pick(
      raw,
      ['original_priority_confidence', 'priority_confidence', 'priorityConfidence'],
      null
    ),
    requiresReview: Boolean(pick(raw, ['requires_human_review', 'needs_review', 'requiresReview'], false)),
    reviewReason: text(pick(raw, ['review_reason', 'reviewReason', 'reason']) || reasons, '—'),
    status: text(pick(raw, ['status']), 'unknown'),
    subject: text(pick(raw, ['subject']), '(no subject)'),
    body: text(pick(raw, ['body', 'text']), ''),
    customer: text(pick(raw, ['customer', 'customer_name']), '—'),
    receivedAt: pick(raw, ['received_at', 'receivedAt', 'timestamp'], null),
    correction: extractCorrection(raw),
    raw,
  };
}

function toCountMap(source, orderedKeys) {
  const result = {};
  orderedKeys.forEach((key) => {
    result[key] = 0;
  });
  if (!source) return result;

  if (Array.isArray(source)) {
    source.forEach((item) => {
      if (item == null) return;
      if (typeof item === 'string') {
        result[item] = (result[item] || 0) + 1;
        return;
      }
      const key = pick(item, ['name', 'category', 'priority', 'label', 'key'], null);
      const count = toNumber(pick(item, ['count', 'value', 'total'], 0), 0);
      if (key != null) result[String(key)] = (result[String(key)] || 0) + count;
    });
  } else if (typeof source === 'object') {
    Object.entries(source).forEach(([key, value]) => {
      result[key] = toNumber(value, 0);
    });
  }
  return result;
}

function toReasonList(source) {
  if (!source) return [];
  if (Array.isArray(source)) {
    return source
      .map((item) => {
        if (typeof item === 'string') return { reason: item, count: 1 };
        return {
          reason: text(pick(item, ['reason', 'name', 'label', 'key'], 'Other')),
          count: toNumber(pick(item, ['count', 'value', 'total'], 0), 0),
        };
      })
      .filter((item) => item.reason && item.reason !== '—');
  }
  if (typeof source === 'object') {
    return Object.entries(source).map(([reason, count]) => ({
      reason,
      count: toNumber(count, 0),
    }));
  }
  return [];
}

/** Defensively normalise the report endpoint across reasonable response shapes. */
export function normalizeReport(raw = {}) {
  const counts = {
    total: toNumber(pick(raw, ['total', 'total_input', 'total_tickets', 'counts.total', 'summary.total'])),
    processed: toNumber(pick(raw, ['processed', 'processed_count', 'counts.processed', 'summary.processed'])),
    autoClassified: toNumber(
      pick(raw, ['auto_classified', 'autoClassified', 'counts.auto_classified', 'summary.auto_classified'])
    ),
    pendingReview: toNumber(
      pick(raw, [
        'pending_review',
        'sent_for_review',
        'review_queue',
        'needs_review',
        'counts.pending_review',
        'summary.pending_review',
      ])
    ),
    humanReviewed: toNumber(
      pick(raw, ['human_reviewed', 'reviewed', 'counts.human_reviewed', 'summary.human_reviewed'])
    ),
    failed: toNumber(pick(raw, ['failed', 'failed_count', 'counts.failed', 'summary.failed'])),
  };

  const coverageRaw = pick(raw, ['automation_coverage', 'automation_rate', 'auto_rate', 'coverage'], null);
  const coverage =
    coverageRaw != null
      ? percentValue(
          coverageRaw && typeof coverageRaw === 'object'
            ? pick(coverageRaw, ['rate', 'value', 'pct', 'percentage'], 0)
            : coverageRaw
        )
      : safeRate(counts.autoClassified, counts.processed || counts.total);

  const reviewRaw = pick(raw, ['review_rate', 'escalation_rate'], null);
  const failureRaw = pick(raw, ['failure_rate'], null);

  return {
    counts,
    categories: toCountMap(
      pick(raw, ['category_distribution', 'categories', 'category_counts', 'distribution.categories']),
      CATEGORIES
    ),
    priorities: toCountMap(
      pick(raw, ['priority_distribution', 'priorities', 'priority_counts', 'distribution.priorities']),
      PRIORITIES
    ),
    escalationReasons: toReasonList(
      pick(raw, ['escalation_reasons', 'review_reasons', 'reasons', 'escalations'])
    ),
    coverage,
    reviewRate: reviewRaw != null ? percentValue(reviewRaw) : safeRate(counts.pendingReview + counts.humanReviewed, counts.total),
    failureRate: failureRaw != null ? percentValue(failureRaw) : safeRate(counts.failed, counts.total),
    raw,
  };
}

/** Compute distributions directly from real stored ticket records. */
export function buildDistributions(tickets = []) {
  const categories = {};
  const priorities = {};
  const matrix = {};
  CATEGORIES.forEach((category) => {
    categories[category] = 0;
    matrix[category] = {};
    PRIORITIES.forEach((priority) => {
      matrix[category][priority] = 0;
    });
  });
  PRIORITIES.forEach((priority) => {
    priorities[priority] = 0;
  });

  tickets.forEach((ticket) => {
    const category = CATEGORIES.includes(ticket.category) ? ticket.category : 'Other';
    const priority = PRIORITIES.includes(ticket.priority) ? ticket.priority : 'Medium';
    categories[category] += 1;
    priorities[priority] += 1;
    matrix[category][priority] += 1;
  });

  return { categories, priorities, matrix, total: tickets.length };
}

export function toCsv(rows, columns) {
  const escape = (value) => {
    if (value === undefined || value === null) return '';
    const str = String(value);
    return /[",\r\n]/.test(str) ? `"${str.replace(/"/g, '""')}"` : str;
  };
  const header = columns.map((column) => escape(column.label)).join(',');
  const body = rows
    .map((row) =>
      columns
        .map((column) => escape(typeof column.get === 'function' ? column.get(row) : row[column.key]))
        .join(',')
    )
    .join('\r\n');
  return `${header}\r\n${body}\r\n`;
}

export function downloadCsv(filename, csv) {
  const blob = new Blob(['\uFEFF', csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}
