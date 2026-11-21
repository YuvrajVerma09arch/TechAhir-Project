// Taxonomy is fixed by the provided dataset (see AGENTHANDOFF.md §2.1 / §2.6).
// Keep these values in sync with app/triage/types.py — the shared contract.
export const CATEGORIES = ['Billing', 'Technical', 'Account', 'Shipping', 'Other'];
export const PRIORITIES = ['Low', 'Medium', 'High', 'Urgent'];

export const STATUS_OPTIONS = [
  { value: 'auto_classified', label: 'Auto-classified' },
  { value: 'pending_review', label: 'Pending review' },
  { value: 'human_reviewed', label: 'Human-reviewed' },
  { value: 'failed', label: 'Failed' },
];

export const STATUS_LABELS = STATUS_OPTIONS.reduce((acc, item) => {
  acc[item.value] = item.label;
  return acc;
}, {});

export const PRIORITY_RANK = { Low: 0, Medium: 1, High: 2, Urgent: 3 };

export const SAMPLE_SIZE = 300;
