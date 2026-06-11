import React, { useEffect } from 'react';
import { X, BrainCircuit, Sparkles, RefreshCw } from 'lucide-react';
import { useGumStore } from '@/store/gum';
import { useStyles } from './styles';
import { Spin } from 'antd';

interface GumPanelProps {
  open: boolean;
  type: 'memory' | 'suggestions' | null;
  onClose: () => void;
}

export function GumPanel({ open, type, onClose }: GumPanelProps) {
  const { styles, cx } = useStyles();
  const { propositions, suggestions, loading, fetchMemory, fetchSuggestions } = useGumStore();

  useEffect(() => {
    if (open) {
      if (type === 'memory') {
        fetchMemory();
      } else if (type === 'suggestions') {
        fetchSuggestions();
      }
    }
  }, [open, type, fetchMemory, fetchSuggestions]);

  if (!open || !type) return null;

  const isMemory = type === 'memory';

  return (
    <div className={styles.panel}>
      {/* Header */}
        <div className={styles.header}>
          <div className={styles.titleWrapper}>
            {isMemory ? (
              <BrainCircuit size={28} className="text-amber-500" style={{ color: '#f59e0b' }} />
            ) : (
              <Sparkles size={28} className="text-amber-500" style={{ color: '#f59e0b' }} />
            )}
            <div>
              <h2>{isMemory ? '瀏覽記憶 (Memory)' : '您可能想知道？ (Suggestions)'}</h2>
              <p>
                {isMemory
                  ? 'AREQA 會透過您的對話行為自動整理記憶與偏好。'
                  : 'AREQA 會根據您的記憶與對話內容，主動推薦您可能感興趣的議題。'}
              </p>
            </div>
          </div>
          <button className={styles.closeBtn} onClick={onClose} title="關閉面板">
            <X size={20} />
          </button>
        </div>

        {/* Content */}
        <div className={styles.content}>
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 8 }}>
            <button
              className={styles.refreshBtn}
              onClick={() => (isMemory ? fetchMemory() : fetchSuggestions())}
              disabled={loading}
            >
              <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
              <span>重新整理</span>
            </button>
          </div>

          {loading ? (
            <div style={{ display: 'flex', justifyContent: 'center', padding: '40px' }}>
              <Spin size="large" />
            </div>
          ) : isMemory ? (
            propositions.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '40px', color: '#888' }}>
                目前還沒有任何記憶紀錄喔！開始與AREQA聊天吧。
              </div>
            ) : (
              propositions.map((p) => (
                <div key={p.id} className={styles.card}>
                  <div className={styles.cardText}>{p.text}</div>
                  <div className={styles.cardMeta}>
                    <span className={styles.confidenceBadge}>
                      信心指數: {p.confidence.toFixed(2)}
                    </span>
                    <span>
                      {p.updated_at ? new Date(p.updated_at).toLocaleString() : '最近更新'}
                    </span>
                  </div>
                </div>
              ))
            )
          ) : (
            suggestions.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '40px', color: '#888' }}>
                目前沒有任何建議。您可以先累積一些對話記憶，再試試看！
              </div>
            ) : (
              suggestions.map((s, idx) => (
                <div key={idx} className={styles.card}>
                  <div className={styles.suggestionTitle}>推薦話題 #{idx + 1}</div>
                  <div className={styles.cardText}>{s}</div>
                </div>
              ))
            )
          )}
        </div>
    </div>
  );
}
