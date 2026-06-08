import React, { useEffect } from 'react';
import { useStore } from '../store/useStore';
import { 
  Lightbulb, 
  Folder, 
  Brain, 
  Cpu, 
  Settings, 
  Video, 
  VideoOff, 
  MessageSquarePlus 
} from 'lucide-react';

const Sidebar: React.FC = () => {
  const { 
    isRecording, 
    currentPage, 
    setCurrentPage, 
    startRecording, 
    stopRecording, 
    fetchStatus,
    userName
  } = useStore();

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  const handleRecordingToggle = () => {
    if (isRecording) {
      stopRecording();
    } else {
      startRecording();
    }
  };

  const navItems = [
    { id: 'suggestions' as const, label: 'Suggestions', icon: Lightbulb, htmlId: 'tour-step-suggestions' },
    { id: 'projects' as const, label: 'Projects', icon: Folder, disabled: true },
    { id: 'memory' as const, label: 'Memory', icon: Brain, htmlId: 'tour-step-memory' },
    { id: 'agent' as const, label: 'Customize Agent', icon: Cpu, disabled: true },
    { id: 'settings' as const, label: 'Settings', icon: Settings, htmlId: 'tour-step-settings' },
  ];

  return (
    <aside className="w-64 bg-[#1e1e1e] border-r border-[#2d2d2d] flex flex-col justify-between p-4 select-none">
      <div>
        {/* App Logo/Header */}
        <div className="flex items-center space-x-3 mb-8 px-2">
          <div className="w-8 h-8 bg-gradient-to-tr from-amber-500 to-orange-600 rounded-lg flex items-center justify-center font-bold text-white shadow-md">
            G
          </div>
          <div>
            <span className="text-lg font-bold tracking-wide text-white block">Gumbo</span>
            <span className="text-[10px] text-gray-500 font-medium uppercase tracking-wider block">User: {userName}</span>
          </div>
        </div>

        {/* Main Navigation */}
        <nav className="space-y-1">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = currentPage === item.id;
            return (
              <button
                key={item.id}
                id={item.htmlId}
                disabled={item.disabled}
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                onClick={() => !item.disabled && setCurrentPage(item.id as any)}
                className={`w-full flex items-center space-x-3 px-3 py-2 rounded-lg text-sm font-medium transition-all ${
                  item.disabled
                    ? 'opacity-40 cursor-not-allowed text-gray-500'
                    : isActive
                    ? 'bg-[#2d2d2d] text-white shadow-sm'
                    : 'text-gray-400 hover:bg-[#252525] hover:text-white'
                }`}
              >
                <Icon size={18} className={isActive ? 'text-amber-500' : 'text-gray-400'} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>

        {/* Active Projects section */}
        <div className="mt-8 px-2">
          <h3 className="text-[10px] font-bold text-gray-500 uppercase tracking-widest mb-3">Active Projects</h3>
          <ul className="space-y-2 text-xs font-medium text-gray-400">
            <li className="flex items-center space-x-2 py-1 px-2 hover:bg-[#252525] hover:text-white rounded-md cursor-pointer transition-colors">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
              <span>General User Models Paper</span>
            </li>
            <li className="flex items-center space-x-2 py-1 px-2 hover:bg-[#252525] hover:text-white rounded-md cursor-pointer transition-colors">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-500"></span>
              <span>Apartment Decorating</span>
            </li>
          </ul>
        </div>

        {/* Recent Chats section */}
        <div className="mt-6 px-2">
          <h3 className="text-[10px] font-bold text-gray-500 uppercase tracking-widest mb-3">Recent Chats</h3>
          <ul className="space-y-2 text-xs font-medium text-gray-400">
            <li className="py-1 px-2 hover:bg-[#252525] hover:text-white rounded-md cursor-pointer transition-colors truncate">
              Improving GUM Figures
            </li>
            <li className="py-1 px-2 hover:bg-[#252525] hover:text-white rounded-md cursor-pointer transition-colors truncate">
              Buying a Sofa
            </li>
          </ul>
        </div>
      </div>

      {/* Footer Controls */}
      <div className="space-y-2 pt-4 border-t border-[#2d2d2d]">
        <button
          id="tour-step-record"
          onClick={handleRecordingToggle}
          className={`w-full flex items-center justify-center space-x-2 py-2.5 rounded-lg text-sm font-semibold transition-all shadow-md ${
            isRecording
              ? 'bg-red-600/20 text-red-400 border border-red-500/30 hover:bg-red-600/30'
              : 'bg-emerald-600/20 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-600/30'
          }`}
        >
          {isRecording ? (
            <>
              <VideoOff size={16} />
              <span>Stop Recording</span>
            </>
          ) : (
            <>
              <Video size={16} />
              <span>Start Recording</span>
            </>
          )}
        </button>
        
        <button className="w-full flex items-center justify-center space-x-2 py-2 bg-[#2a2a2a] text-gray-300 rounded-lg text-sm font-medium border border-[#3a3a3a] hover:bg-[#333] hover:text-white transition-all">
          <MessageSquarePlus size={16} />
          <span>Give Feedback</span>
        </button>
      </div>
    </aside>
  );
};

export default Sidebar;
