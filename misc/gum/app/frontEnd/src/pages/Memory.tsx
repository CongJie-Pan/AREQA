import React, { useEffect, useState } from 'react';
import { useStore } from '../store/useStore';
import MemoryTable from '../components/MemoryTable';
import { Search, RefreshCw, BrainCircuit, Trash2 } from 'lucide-react';

const Memory: React.FC = () => {
  const { propositions, fetchMemory, deleteAllMemory, loading } = useStore();
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    fetchMemory();
  }, [fetchMemory]);

  const handleRefresh = () => {
    fetchMemory();
  };

  const handleDeleteAll = async () => {
    if (window.confirm('Are you sure you want to delete ALL memory propositions? This cannot be undone.')) {
      await deleteAllMemory();
    }
  };

  const filteredPropositions = propositions.filter((p) =>
    p.text.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight flex items-center space-x-2">
            <BrainCircuit size={24} className="text-amber-500" />
            <span>Memory Propositions</span>
          </h1>
          <p className="text-xs text-gray-500 mt-1">
            GUM builds these propositions dynamically based on your recorded computer activities. You can edit or delete them to maintain data control.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={handleDeleteAll}
            disabled={loading || propositions.length === 0}
            className="flex items-center space-x-2 px-3 py-1.5 bg-red-900/20 border border-red-900/50 rounded-lg text-xs font-semibold text-red-400 hover:bg-red-900/40 hover:text-red-300 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
          >
            <Trash2 size={14} />
            <span>Delete All</span>
          </button>
          
          <button
            onClick={handleRefresh}
            disabled={loading}
            className="flex items-center space-x-2 px-3 py-1.5 bg-[#1e1e1e] border border-[#2d2d2d] rounded-lg text-xs font-semibold text-gray-300 hover:bg-[#252525] hover:text-white transition-all"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Search Input */}
      <div className="relative">
        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
        <input
          type="text"
          placeholder="Search propositions..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="w-full bg-[#1e1e1e] border border-[#2d2d2d] rounded-lg pl-10 pr-4 py-2 text-sm text-white focus:outline-none focus:border-amber-500/50 placeholder-gray-500"
        />
      </div>

      {/* Table Section */}
      {loading && filteredPropositions.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20">
          <div className="w-8 h-8 border-4 border-amber-500/20 border-t-amber-500 rounded-full animate-spin mb-4"></div>
          <span className="text-xs text-gray-500">Loading Memory Propositions...</span>
        </div>
      ) : (
        <MemoryTable propositions={filteredPropositions} />
      )}
    </div>
  );
};

export default Memory;
