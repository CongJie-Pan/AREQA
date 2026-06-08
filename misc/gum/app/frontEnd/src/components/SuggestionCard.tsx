import React, { useState } from 'react';
import { Suggestion, useStore } from '../store/useStore';
import { ThumbsUp, ThumbsDown, Play, CheckCircle } from 'lucide-react';

interface SuggestionCardProps {
  suggestion: Suggestion;
}

const SuggestionCard: React.FC<SuggestionCardProps> = ({ suggestion }) => {
  const { submitFeedback } = useStore();
  const [feedback, setFeedback] = useState<'liked' | 'disliked' | null>(null);
  const [feedbackText, setFeedbackText] = useState('');
  const [showFeedbackInput, setShowFeedbackInput] = useState(false);
  const [isExecuting, setIsExecuting] = useState(false);
  const [hasExecuted, setHasExecuted] = useState(false);

  const handleFeedback = async (isPositive: boolean) => {
    if (isPositive) {
      setFeedback('liked');
      await submitFeedback(suggestion.id, true);
    } else {
      setFeedback('disliked');
      setShowFeedbackInput(true);
    }
  };

  const submitTextFeedback = async () => {
    await submitFeedback(suggestion.id, false, feedbackText);
    setShowFeedbackInput(false);
  };

  const handleExecute = () => {
    setIsExecuting(true);
    // Simulate GUM executing the suggestion (as in Gumbo "execution is everything")
    setTimeout(() => {
      setIsExecuting(false);
      setHasExecuted(true);
    }, 2500);
  };

  return (
    <div className="bg-[#1e1e1e] border border-[#2d2d2d] rounded-xl p-5 shadow-lg flex flex-col justify-between hover:border-[#3d3d3d] transition-all">
      <div>
        <div className="flex justify-between items-start mb-3">
          <h3 className="text-base font-semibold text-white tracking-wide">{suggestion.title}</h3>
          <div className="flex space-x-1.5 text-xs text-gray-500 font-bold bg-[#151515] px-2 py-1 rounded-md border border-[#222]">
            <span>Benefit: {suggestion.benefit}/10</span>
          </div>
        </div>
        
        <p className="text-sm text-gray-400 mb-6 leading-relaxed">
          {suggestion.description}
        </p>
      </div>

      <div className="space-y-3">
        {/* Actions Row */}
        <div className="flex justify-between items-center pt-3 border-t border-[#2d2d2d]/50">
          <button
            onClick={handleExecute}
            disabled={isExecuting || hasExecuted}
            className={`flex items-center space-x-2 px-4 py-2 rounded-lg text-xs font-semibold shadow-sm transition-all ${
              hasExecuted 
                ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' 
                : 'bg-amber-600 text-white hover:bg-amber-500 hover:shadow-amber-500/10'
            }`}
          >
            {isExecuting ? (
              <>
                <span className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin"></span>
                <span>Executing...</span>
              </>
            ) : hasExecuted ? (
              <>
                <CheckCircle size={14} />
                <span>Action Completed</span>
              </>
            ) : (
              <>
                <Play size={14} fill="white" />
                <span>Start Chat / Run</span>
              </>
            )}
          </button>

          {/* Feedback buttons */}
          <div className="flex items-center space-x-1">
            <button
              onClick={() => handleFeedback(true)}
              className={`p-2 rounded-lg transition-colors ${
                feedback === 'liked'
                  ? 'bg-emerald-600/20 text-emerald-400 border border-emerald-500/20'
                  : 'text-gray-500 hover:bg-[#252525] hover:text-gray-300'
              }`}
              title="Helpful"
            >
              <ThumbsUp size={14} />
            </button>
            <button
              onClick={() => handleFeedback(false)}
              className={`p-2 rounded-lg transition-colors ${
                feedback === 'disliked'
                  ? 'bg-red-600/20 text-red-400 border border-red-500/20'
                  : 'text-gray-500 hover:bg-[#252525] hover:text-gray-300'
              }`}
              title="Not helpful"
            >
              <ThumbsDown size={14} />
            </button>
          </div>
        </div>

        {/* Text Feedback Panel (Disliked) */}
        {showFeedbackInput && (
          <div className="mt-3 bg-[#151515] p-3 rounded-lg border border-[#2d2d2d] space-y-2">
            <label className="text-[10px] text-gray-500 font-bold uppercase tracking-wider">Provide details to improve GUM:</label>
            <textarea
              value={feedbackText}
              onChange={(e) => setFeedbackText(e.target.value)}
              className="w-full bg-[#252525] border border-[#353535] rounded-md p-2 text-xs text-white focus:outline-none focus:border-amber-500/50 placeholder-gray-600 resize-none h-16"
              placeholder="Tell Gumbo why this isn't helpful..."
            />
            <div className="flex justify-end space-x-2">
              <button
                onClick={() => setShowFeedbackInput(false)}
                className="px-2.5 py-1 text-[11px] text-gray-400 hover:text-white font-medium"
              >
                Cancel
              </button>
              <button
                onClick={submitTextFeedback}
                className="bg-amber-600 hover:bg-amber-500 px-3 py-1 rounded text-[11px] text-white font-semibold transition-colors"
              >
                Submit
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default SuggestionCard;
