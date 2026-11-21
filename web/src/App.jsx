import { useEffect, useState } from 'react';
import Header from './components/Header/Header.jsx';
import Sidebar from './components/Sidebar/Sidebar.jsx';
import { DataProvider } from './context/DataContext.jsx';
import Overview from './sections/Overview/Overview.jsx';
import NewTicket from './sections/NewTicket/NewTicket.jsx';
import Analytics from './sections/Analytics/Analytics.jsx';
import ReviewQueue from './sections/ReviewQueue/ReviewQueue.jsx';
import Reports from './sections/Reports/Reports.jsx';
import './components/Header/Header.css';
import './components/Sidebar/Sidebar.css';

const SECTIONS = [
  {
    id: 'overview',
    label: 'Overview',
    title: 'Overview',
    description: 'Processing status and outcomes across the ticket dataset.',
  },
  {
    id: 'new',
    label: 'New Ticket',
    title: 'New Ticket',
    description: 'Create one ticket and see the first-pass triage decision immediately.',
  },
  {
    id: 'analytics',
    label: 'Analytics',
    title: 'Analytics',
    description: 'Priority and category distributions computed from stored tickets.',
  },
  {
    id: 'review',
    label: 'Review Queue',
    title: 'Human Review Queue',
    description: 'Inspect escalated tickets, see why they were routed, and record corrections.',
  },
  {
    id: 'reports',
    label: 'Reports',
    title: 'Reports',
    description: 'Processing summary, quality rates, escalation reasons and CSV exports.',
  },
];

function sectionFromHash() {
  const hash = window.location.hash.replace(/^#/, '');
  return SECTIONS.some((section) => section.id === hash) ? hash : 'overview';
}

function App() {
  const [active, setActive] = useState(sectionFromHash);

  useEffect(() => {
    function handleHashChange() {
      setActive(sectionFromHash());
    }
    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, []);

  function selectSection(id) {
    window.location.hash = id;
    setActive(id);
    window.scrollTo({ top: 0, behavior: 'auto' });
  }

  const current = SECTIONS.find((section) => section.id === active) || SECTIONS[0];

  return (
    <DataProvider>
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <div className="app-shell">
        <Header />
        <div className="app-body">
          <Sidebar
            items={SECTIONS.map(({ id, label }) => ({ id, label }))}
            active={active}
            onSelect={selectSection}
          />
          <main className="app-main" id="main-content" tabIndex={-1}>
            <div className="page">
              <div className="page__head">
                <h1>{current.title}</h1>
                <p>{current.description}</p>
              </div>
              {active === 'overview' && <Overview />}
              {active === 'new' && <NewTicket />}
              {active === 'analytics' && <Analytics />}
              {active === 'review' && <ReviewQueue />}
              {active === 'reports' && <Reports />}
            </div>
          </main>
        </div>
      </div>
    </DataProvider>
  );
}

export default App;
