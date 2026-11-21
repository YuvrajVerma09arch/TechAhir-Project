import { useState } from 'react';
import api from '../../api.js';
import { useData } from '../../context/DataContext.jsx';
import { SAMPLE_SIZE } from '../../utils/constants.js';
import './SeedButton.css';

export default function SeedButton({
  label = `Process sample dataset (${SAMPLE_SIZE} tickets)`,
  variant = 'primary',
  size = 'md',
  onSuccess,
}) {
  const { bump } = useData();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function handleClick() {
    setBusy(true);
    setError(null);
    try {
      await api.seed();
      bump();
      if (onSuccess) onSuccess();
    } catch (requestError) {
      setError(requestError.message || 'Processing failed. Please try again.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="seed-action">
      <button
        type="button"
        className={`btn btn--${variant}${size === 'sm' ? ' btn--sm' : ''}`}
        onClick={handleClick}
        disabled={busy}
        aria-busy={busy}
      >
        {busy ? 'Processing tickets…' : label}
      </button>
      {error && (
        <p className="seed-action__error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
