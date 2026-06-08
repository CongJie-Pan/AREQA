import React, { useEffect, useState } from 'react';
import { useStore } from '../store/useStore';
import MemoryTable from '../components/MemoryTable';
import { Search, RefreshCw, BrainCircuit } from 'lucide-react';

const Memory: React.FC = () => {
  const { propositions, fetchMemory, loading } = useStore();
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    fetchMemory();
  }, []);

  const handleRefresh = () => {
    fetchMemory();
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

        <button
          onClick={handleRefresh}
          disabled={loading}
          className="flex items-center space-x-2 px-3 py-1.5 bg-[#1e1e1e] border border-[#2d2d2d] rounded-lg text-xs font-semibold text-gray-300 hover:bg-[#252525] hover:text-white transition-all"
        >
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          <span>Refresh</span>
        </button>
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
