import React, { useState, useEffect } from 'react';
import { useStore } from '../store/useStore';
import { Save, Settings, Shield, Key } from 'lucide-react';

const SettingsPage: React.FC = () => {
  const { 
    userName, 
    modelName, 
    llmApiKey, 
    enableScreenCapture, 
    saveSettings, 
    loading, 
    error 
  } = useStore();

  const [localUser, setLocalUser] = useState(userName);
  const [localApiKey, setLocalApiKey] = useState(llmApiKey);
  const [localModel, setLocalModel] = useState(modelName);
  const [localScreenCap, setLocalScreenCap] = useState(enableScreenCapture);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Sync state if store updates (e.g. on load)
  useEffect(() => {
    /* eslint-disable react-hooks/set-state-in-effect */
    setLocalUser(userName);
    setLocalApiKey(llmApiKey);
    setLocalModel(modelName);
    setLocalScreenCap(enableScreenCapture);
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [userName, modelName, llmApiKey, enableScreenCapture]);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSuccessMsg(null);
    try {
      await saveSettings(localUser, localApiKey, localScreenCap, localModel);
      setSuccessMsg('Settings updated and saved successfully.');
      setTimeout(() => setSuccessMsg(null), 3000);
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div className="space-y-6 max-w-2xl">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white tracking-tight flex items-center space-x-2">
          <Settings size={24} className="text-amber-500" />
          <span>System Settings</span>
        </h1>
        <p className="text-xs text-gray-500 mt-1">
          Configure API credentials, model choice, and privacy settings for Gumbo.
        </p>
      </div>

      <form onSubmit={handleSave} className="bg-[#1e1e1e] border border-[#2d2d2d] rounded-xl p-6 shadow-lg space-y-6">
        {successMsg && (
          <div className="bg-emerald-900/20 border border-emerald-500/20 text-emerald-400 p-3 rounded-lg text-xs font-semibold">
            {successMsg}
          </div>
        )}

        {error && (
          <div className="bg-red-900/20 border border-red-500/20 text-red-400 p-3 rounded-lg text-xs font-semibold">
            {error}
          </div>
        )}

        {/* User Configuration */}
        <div className="space-y-4">
          <h3 className="text-xs font-bold text-gray-400 uppercase tracking-wider flex items-center space-x-2 pb-2 border-b border-[#2d2d2d]">
            <Shield size={14} className="text-gray-500" />
            <span>Profile Configuration</span>
          </h3>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1.5">User Name</label>
              <input
                type="text"
                value={localUser}
                onChange={(e) => setLocalUser(e.target.value)}
                required
                className="w-full bg-[#151515] border border-[#2d2d2d] rounded-lg px-3.5 py-2 text-sm text-white focus:outline-none focus:border-amber-500/50"
                placeholder="e.g. John Doe"
              />
            </div>
            
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1.5">LLM Model Name</label>
              <select
                value={localModel}
                onChange={(e) => setLocalModel(e.target.value)}
                className="w-full bg-[#151515] border border-[#2d2d2d] rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-amber-500/50"
              >
                <option value="openai/gpt-4o-mini">GPT-4o Mini (Vision + JSON Schema)</option>
                <option value="qwen/qwen3-vl-235b-a22b-instruct">Qwen3 VL 235B (Vision)</option>
                <option value="gpt-4o-mini">gpt-4o-mini</option>
                <option value="gpt-4o">gpt-4o</option>
              </select>
            </div>
          </div>
        </div>

        {/* API Credentials */}
        <div className="space-y-4">
          <h3 className="text-xs font-bold text-gray-400 uppercase tracking-wider flex items-center space-x-2 pb-2 border-b border-[#2d2d2d]">
            <Key size={14} className="text-gray-500" />
            <span>API Credentials</span>
          </h3>

          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1.5">OpenRouter API Key</label>
            <input
              type="password"
              value={localApiKey}
              onChange={(e) => setLocalApiKey(e.target.value)}
              required
              className="w-full bg-[#151515] border border-[#2d2d2d] rounded-lg px-3.5 py-2 text-sm text-white focus:outline-none focus:border-amber-500/50 font-mono"
              placeholder="sk-or-v1-..."
            />
            <p className="text-[10px] text-gray-500 mt-1.5 leading-relaxed">
              Required for reasoning and proposition generation. Stored locally in backend memory.
            </p>
          </div>
        </div>

        {/* Privacy Settings */}
        <div className="space-y-4">
          <h3 className="text-xs font-bold text-gray-400 uppercase tracking-wider pb-2 border-b border-[#2d2d2d]">
            Privacy & Recording
          </h3>

          <div className="flex items-start space-x-3">
            <input
              type="checkbox"
              id="screenCap"
              checked={localScreenCap}
              onChange={(e) => setLocalScreenCap(e.target.checked)}
              className="mt-1 bg-[#151515] border-[#2d2d2d] text-amber-600 rounded focus:ring-amber-500/30"
            />
            <div>
              <label htmlFor="screenCap" className="block text-sm font-semibold text-white">Enable Screen Capture</label>
              <p className="text-xs text-gray-500 mt-1 leading-relaxed">
                If checked, GUM will ask for browser permission to capture your screen. This is REQUIRED for Gumbo to see your activities. Mock tracking has been completely removed.
              </p>
            </div>
          </div>
        </div>

        {/* Save Button */}
        <div className="pt-4 border-t border-[#2d2d2d] flex justify-end">
          <button
            type="submit"
            disabled={loading}
            className="flex items-center space-x-2 px-5 py-2.5 bg-amber-600 text-white rounded-lg text-sm font-semibold hover:bg-amber-500 transition-all shadow-md"
          >
            <Save size={16} />
            <span>{loading ? 'Saving...' : 'Save Settings'}</span>
          </button>
        </div>
      </form>
    </div>
  );
};

export default SettingsPage;
