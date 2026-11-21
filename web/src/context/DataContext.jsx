import { createContext, useCallback, useContext, useState } from 'react';

const DataContext = createContext(null);

/** Tracks a data version so mutations (seed, review) refetch every open section. */
export function DataProvider({ children }) {
  const [version, setVersion] = useState(0);
  const bump = useCallback(() => setVersion((current) => current + 1), []);
  return <DataContext.Provider value={{ version, bump }}>{children}</DataContext.Provider>;
}

export function useData() {
  const context = useContext(DataContext);
  if (!context) throw new Error('useData must be used inside a DataProvider');
  return context;
}
