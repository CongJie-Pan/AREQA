import React, { useEffect } from 'react';
import Sidebar from './components/Sidebar';
import Suggestions from './pages/Suggestions';
import Memory from './pages/Memory';
import SettingsPage from './pages/Settings';
import { useStore } from './store/useStore';

const App: React.FC = () => {
  const { currentPage, fetchStatus } = useStore();

  useEffect(() => {
    // Initial fetch to get recording status and config
    fetchStatus();
  }, []);

  return (
    <div className="flex h-screen bg-[#121212] text-white font-sans overflow-hidden antialiased">
      {/* Left Sidebar Navigation */}
      <Sidebar />

      {/* Main Content Pane */}
      <main className="flex-1 overflow-y-auto p-8 bg-[#121212]">
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
