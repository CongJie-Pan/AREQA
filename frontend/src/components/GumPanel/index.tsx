import React, { useEffect, useState } from 'react';
import { X, BrainCircuit, Sparkles, RefreshCw, Trash2, Edit2, Check, X as XIcon } from 'lucide-react';
import type { CheckboxChangeEvent } from 'antd/es/checkbox';
import { useGumStore } from '@/store/gum';
import { useStyles } from './styles';
import { Spin, Checkbox, Input, message, Button, Space, Popconfirm } from 'antd';

interface GumPanelProps {
  open: boolean;
  type: 'memory' | 'suggestions' | null;
  onClose: () => void;
}

export function GumPanel({ open, type, onClose }: GumPanelProps) {
  const { styles } = useStyles();
  const { propositions, suggestions, loading, fetchMemory, fetchSuggestions, deleteMemory, deleteMemories, editMemory } = useGumStore();

  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editText, setEditText] = useState('');

  const [prevOpen, setPrevOpen] = useState(open);
  if (open !== prevOpen) {
    setPrevOpen(open);
    if (!open) {
      setSelectedIds(new Set());
      setEditingId(null);
    }
  }

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

  const handleToggleSelect = (id: number) => {
    const newSelected = new Set(selectedIds);
    if (newSelected.has(id)) {
      newSelected.delete(id);
    } else {
      newSelected.add(id);
    }
    setSelectedIds(newSelected);
  };

  const handleSelectAll = (e: CheckboxChangeEvent) => {
    if (e.target.checked) {
      setSelectedIds(new Set(propositions.map(p => p.id)));
    } else {
      setSelectedIds(new Set());
    }
  };

  const handleDeleteSelected = async () => {
    if (selectedIds.size === 0) return;
    try {
      const ids = Array.from(selectedIds);
      await deleteMemories(ids);
      message.success(`成功刪除 ${ids.length} 筆記憶`);
      setSelectedIds(new Set());
    } catch {
      message.error('刪除記憶失敗');
    }
  };

  const handleSaveEdit = async (id: number) => {
    if (!editText.trim()) {
      message.warning('記憶內容不能為空');
      return;
    }
    try {
      await editMemory(id, editText);
      message.success('記憶更新成功');
      setEditingId(null);
    } catch {
      message.error('記憶更新失敗');
    }
  };

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
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            {isMemory ? (
              <Space>
                <Checkbox 
                  onChange={handleSelectAll} 
                  checked={propositions.length > 0 && selectedIds.size === propositions.length}
                  indeterminate={selectedIds.size > 0 && selectedIds.size < propositions.length}
                >
                  全選
                </Checkbox>
                {selectedIds.size > 0 && (
                  <Popconfirm title={`確定要刪除選取的 ${selectedIds.size} 筆記憶嗎？`} onConfirm={handleDeleteSelected}>
                    <Button danger size="small" icon={<Trash2 size={14} />}>
                      刪除選取記憶
                    </Button>
                  </Popconfirm>
                )}
              </Space>
            ) : <div />}
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
                <div key={p.id} className={`${styles.card} ${selectedIds.has(p.id) ? 'selected' : ''}`} style={{ position: 'relative' }}>
                  {editingId === p.id ? (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                      <Input.TextArea 
                        value={editText}
                        onChange={e => setEditText(e.target.value)}
                        autoSize={{ minRows: 2, maxRows: 6 }}
                      />
                      <Space style={{ alignSelf: 'flex-end' }}>
                        <Button size="small" icon={<XIcon size={14} />} onClick={() => setEditingId(null)}>取消</Button>
                        <Button size="small" type="primary" icon={<Check size={14} />} onClick={() => handleSaveEdit(p.id)}>儲存</Button>
                      </Space>
                    </div>
                  ) : (
                    <>
                      <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
                        <Checkbox 
                          checked={selectedIds.has(p.id)} 
                          onChange={() => handleToggleSelect(p.id)} 
                          style={{ marginTop: 2 }}
                        />
                        <div className={styles.cardText} style={{ flex: 1, minWidth: 0, paddingRight: 8 }}>
                          {p.text}
                        </div>
                        <div style={{ opacity: 1, display: 'flex', gap: 4, marginTop: -4, alignItems: 'center' }}>
                          <span className={styles.confidenceBadge} style={{ marginRight: 8 }}>
                            信心指數: {p.confidence.toFixed(2)}
                          </span>
                          <Button size="small" type="text" icon={<Edit2 size={14} />} onClick={() => { setEditingId(p.id); setEditText(p.text); }} title="編輯記憶" style={{ color: '#aaa' }} />
                          <Popconfirm title="確定要刪除此記憶嗎？" onConfirm={() => deleteMemory(p.id)}>
                            <Button size="small" type="text" danger icon={<Trash2 size={14} />} title="刪除記憶" />
                          </Popconfirm>
                        </div>
                      </div>
                      <div className={styles.cardMeta} style={{ marginTop: 8, paddingLeft: 28 }}>
                        <span style={{ marginLeft: 'auto' }}>
                          {p.updated_at ? new Date(p.updated_at).toLocaleString() : '最近更新'}
                        </span>
                      </div>
                    </>
                  )}
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
