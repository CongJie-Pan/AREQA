import React, { useEffect } from 'react';
import Sidebar from './components/Sidebar';
import TourGuide from './components/TourGuide';
import ScreenObserver from './components/ScreenObserver';
import Suggestions from './pages/Suggestions';
import Memory from './pages/Memory';
import SettingsPage from './pages/Settings';
import { useStore } from './store/useStore';

const App: React.FC = () => {
  const { currentPage, fetchStatus, error } = useStore();

  useEffect(() => {
    // Initial fetch to get recording status and config
    fetchStatus();
  }, [fetchStatus]);

  return (
    <div className="flex h-screen bg-[#121212] text-white font-sans overflow-hidden antialiased">
      <TourGuide />
      <ScreenObserver />
      {/* Left Sidebar Navigation */}
      <Sidebar />

      {/* Main Content Pane */}
      <main className="flex-1 overflow-y-auto p-8 bg-[#121212] relative">
        {/* Error Toast */}
        {error && (
          <div className="absolute top-4 right-4 z-50 bg-red-900/90 border border-red-500 text-red-100 px-4 py-3 rounded-lg shadow-lg flex items-center space-x-3">
            <span className="font-semibold text-sm">{error}</span>
            <button 
              onClick={() => useStore.setState({ error: null })}
              className="text-red-300 hover:text-white"
            >
              &times;
            </button>
          </div>
        )}

        <div className="max-w-5xl mx-auto h-full">
          {currentPage === 'suggestions' && <Suggestions />}
          {currentPage === 'memory' && <Memory />}
          {currentPage === 'settings' && <SettingsPage />}
        </div>
      </main>
    </div>
  );
};

export default App;
