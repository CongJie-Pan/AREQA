import React, { useEffect, useState } from 'react';
import { useStore } from '../store/useStore';
import SuggestionCard from '../components/SuggestionCard';
import { Search, ArrowUpDown, RefreshCw, Sparkles } from 'lucide-react';

const Suggestions: React.FC = () => {
  const { suggestions, fetchSuggestions, loading, isRecording } = useStore();
  const [searchQuery, setSearchQuery] = useState('');
  const [sortBy, setSortBy] = useState<'benefit' | 'confidence'>('benefit');

  useEffect(() => {
    fetchSuggestions();
  }, []);

  const handleRefresh = () => {
    fetchSuggestions();
  };

  const filteredSuggestions = suggestions
    .filter((s) => 
      s.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      s.description.toLowerCase().includes(searchQuery.toLowerCase())
    )
    .sort((a, b) => b[sortBy] - a[sortBy]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight flex items-center space-x-2">
            <span>Suggestions</span>
          </h1>
          <p className="text-xs text-amber-500/80 font-medium mt-1">
            Suggestions are AI-generated based on GUM propositions and may be inaccurate.
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

      {/* Search & Sort Panel */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
          <input
            type="text"
            placeholder="Search suggestions..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-[#1e1e1e] border border-[#2d2d2d] rounded-lg pl-10 pr-4 py-2 text-sm text-white focus:outline-none focus:border-amber-500/50 placeholder-gray-500"
          />
        </div>

        <button
          onClick={() => setSortBy(sortBy === 'benefit' ? 'confidence' : 'benefit')}
          className="flex items-center justify-center space-x-2 px-4 py-2 bg-[#1e1e1e] border border-[#2d2d2d] rounded-lg text-sm text-gray-300 hover:bg-[#252525] hover:text-white transition-all"
        >
          <ArrowUpDown size={14} />
          <span>Sort by: {sortBy === 'benefit' ? 'Benefit' : 'Confidence'}</span>
        </button>
      </div>

      {/* Recording warning info if not recording */}
      {!isRecording && suggestions.length === 0 && (
        <div className="bg-amber-900/10 border border-amber-500/20 p-4 rounded-xl flex items-start space-x-3">
          <Sparkles className="text-amber-500 shrink-0 mt-0.5" size={16} />
          <div>
            <h4 className="text-xs font-bold text-amber-500 uppercase tracking-wider">Start Recording to see suggestions</h4>
            <p className="text-xs text-gray-400 mt-1 leading-relaxed">
              Enable background recording in the sidebar to feed observations into GUM. GUM will analyze your activity and compile propositions to generate proactive recommendations here.
            </p>
          </div>
        </div>
      )}

      {/* Grid List */}
      {loading && filteredSuggestions.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20">
          <div className="w-8 h-8 border-4 border-amber-500/20 border-t-amber-500 rounded-full animate-spin mb-4"></div>
          <span className="text-xs text-gray-500">Generating Gumbo Suggestions...</span>
        </div>
      ) : filteredSuggestions.length === 0 ? (
        <div className="text-center py-20 bg-[#1e1e1e] border border-[#2d2d2d] rounded-xl">
          <p className="text-sm text-gray-500">No suggestions match your search query.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {filteredSuggestions.map((suggestion) => (
            <SuggestionCard key={suggestion.id} suggestion={suggestion} />
          ))}
        </div>
      )}
    </div>
  );
};

export default Suggestions;
