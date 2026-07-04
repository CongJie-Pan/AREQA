import React, { useEffect, useState, useMemo } from 'react';
import { X, BrainCircuit, Sparkles, RefreshCw, Trash2, Edit2, Clock, FolderHeart } from 'lucide-react';
import type { CheckboxChangeEvent } from 'antd/es/checkbox';
import { useGumStore } from '@/store/gum';
import { useStyles } from './styles';
import { Spin, Checkbox, Input, message, Button, Space, Popconfirm, Modal, List, Tag } from 'antd';
import { SidePanelType } from '@/types/panel';

const cleanMemoryText = (text: string) => {
  if (text.startsWith('【使用者畫像】')) {
    const match = text.match(/【.*?】.*?: (.*)/);
    if (match) {
      let inner = match[1];
      if (inner.startsWith("['") && inner.endsWith("']")) {
        inner = inner.slice(2, -2).replace(/', '/g, '、');
      }
      return inner;
    }
  }
  return text;
};

interface GumPanelProps {
  open: boolean;
  type: SidePanelType;
  onClose: () => void;
}

export function GumPanel({ open, type, onClose }: GumPanelProps) {
  const { styles } = useStyles();
  const { propositions, suggestions, summary, loading, loadingSummary, fetchMemory, fetchSuggestions, fetchSummary, deleteMemory, deleteMemories, editMemory } = useGumStore();

  const [selectedIds, setSelectedIds] = useState<Set<number | string>>(new Set());
  const [editingId, setEditingId] = useState<number | string | null>(null);
  const [editText, setEditText] = useState('');
  const [assetModalVisible, setAssetModalVisible] = useState(false);
  const [assetModalType, setAssetModalType] = useState<'tags' | 'scopes' | 'nodes'>('tags');

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
        fetchSummary();
      } else if (type === 'suggestions') {
        fetchSuggestions();
      }
    }
  }, [open, type, fetchMemory, fetchSuggestions, fetchSummary]);

  // Filter out short-term memory (hot memory and scroll records)
  const longTermProps = useMemo(() => {
    return propositions.filter(p => {
      const isHot = String(p.id).startsWith('hot:');
      const isScroll = p.text.includes('Type: scroll') || p.text.includes('User Action: scroll');
      return !isHot && !isScroll;
    });
  }, [propositions]);

  // 整理與計算資產數據
  const { groupedMemories, uniqueScopes, uniqueTags } = useMemo(() => {
    const groups: Record<string, typeof longTermProps> = {};
    const scopes = new Set<string>();
    const tags = new Set<string>();

    // Sort propositions by updated_at descending before grouping
    const sortedProps = [...longTermProps].sort((a, b) => {
      const dateA = a.updated_at ? new Date(a.updated_at).getTime() : 0;
      const dateB = b.updated_at ? new Date(b.updated_at).getTime() : 0;
      return dateB - dateA;
    });

    sortedProps.forEach(p => {
      if (p.context_scope) scopes.add(p.context_scope);
      if (p.event_types) p.event_types.forEach(e => tags.add(e));
      if (p.functional_type_seeds) p.functional_type_seeds.forEach(f => tags.add(f));

      const dateObj = p.updated_at ? new Date(p.updated_at) : new Date();
      const dateStr = `${dateObj.getFullYear()}年${dateObj.getMonth() + 1}月${dateObj.getDate()}日`;
      
      if (!groups[dateStr]) groups[dateStr] = [];
      groups[dateStr].push(p);
    });

    return { 
      groupedMemories: groups, 
      uniqueScopes: Array.from(scopes), 
      uniqueTags: Array.from(tags) 
    };
  }, [longTermProps]);

  if (!open || !type) return null;

  const isMemory = type === 'memory';

  const handleToggleSelect = (id: number | string) => {
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
      setSelectedIds(new Set(longTermProps.map(p => p.id)));
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

  const handleSaveEdit = async (id: string | number) => {
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
      <button className={styles.closeBtnFixed} onClick={onClose} title="關閉面板">
        <X size={20} />
      </button>

      <div className={styles.content}>
        {isMemory ? (
          <>
            {/* Top Section: Hero Card */}
            <div className={styles.heroSection}>
              <div className={styles.heroTitleRow}>
                <BrainCircuit size={28} style={{ color: '#d4af37' }} />
                <h2>AREQA 眼中的你</h2>
              </div>
              <div className={styles.heroSummaryBox}>
                {loadingSummary ? (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#aaa' }}>
                    <Spin size="small" /> 正在為您生成專屬記憶綜整...
                  </div>
                ) : summary ? (
                  <>
                    <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.8, marginBottom: 8 }}>{summary.sentence1}</div>
                    <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.8, color: 'rgba(255,255,255,0.7)' }}>{summary.sentence2}</div>
                    {summary.hashtags && summary.hashtags.length > 0 && (
                      <div style={{ marginTop: 4 }}>
                        {summary.hashtags.map((tag, idx) => (
                          <span key={idx} className={styles.heroHashtag}>{tag.startsWith('#') ? tag : `#${tag}`}</span>
                        ))}
                      </div>
                    )}
                  </>
                ) : (
                  <div>目前還沒有足夠的記憶能為您生成總結。</div>
                )}
              </div>
            </div>

            {/* Middle Section: Assets */}
            <div>
              <div className={styles.sectionHeader}>
                <FolderHeart size={18} style={{ color: '#d4af37' }} />
                <h3>記憶資產 <span>({longTermProps.length}條)</span></h3>
              </div>
              <div className={styles.assetsGrid}>
                <div className={styles.assetCard} onClick={() => { setAssetModalType('tags'); setAssetModalVisible(true); }} style={{ cursor: 'pointer' }}>
                  <div className={styles.assetLabel}>活躍標籤</div>
                  <div className={styles.assetValue}>{uniqueTags.length} <span>個</span></div>
                </div>
                <div className={styles.assetCard} onClick={() => { setAssetModalType('scopes'); setAssetModalVisible(true); }} style={{ cursor: 'pointer' }}>
                  <div className={styles.assetLabel}>涉及領域</div>
                  <div className={styles.assetValue}>{uniqueScopes.length} <span>個</span></div>
                </div>
                <div className={styles.assetCard} onClick={() => { setAssetModalType('nodes'); setAssetModalVisible(true); }} style={{ cursor: 'pointer' }}>
                  <div className={styles.assetLabel}>記憶節點</div>
                  <div className={styles.assetValue}>{longTermProps.length} <span>條</span></div>
                </div>
              </div>
            </div>

            {/* Bottom Section: Timeline */}
            <div className={styles.timelineSection}>
              <div className={styles.timelineHeaderRow}>
                <div className={styles.sectionHeader} style={{ marginBottom: 0 }}>
                  <Clock size={18} style={{ color: '#d4af37' }} />
                  <h3>時間線</h3>
                </div>
                
                <div className={styles.timelineActions}>
                  <Checkbox 
                    onChange={handleSelectAll} 
                    checked={longTermProps.length > 0 && selectedIds.size === longTermProps.length}
                    indeterminate={selectedIds.size > 0 && selectedIds.size < longTermProps.length}
                  >
                    全選
                  </Checkbox>
                  {selectedIds.size > 0 && (
                    <Popconfirm title={`確定要刪除選取的 ${selectedIds.size} 筆記憶嗎？`} onConfirm={handleDeleteSelected}>
                      <Button danger size="small" icon={<Trash2 size={14} />}>
                        刪除
                      </Button>
                    </Popconfirm>
                  )}
                  <button className={styles.refreshBtn} onClick={() => fetchMemory()} disabled={loading}>
                    <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
                    重新整理
                  </button>
                </div>
              </div>

              {loading ? (
                <div style={{ display: 'flex', justifyContent: 'center', padding: '40px' }}>
                  <Spin size="large" />
                </div>
              ) : longTermProps.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '40px', color: '#888' }}>
                  目前還沒有任何記憶紀錄喔！開始與AREQA聊天吧。
                </div>
              ) : (
                <div className={styles.timelineItems}>
                  {Object.entries(groupedMemories).map(([dateStr, items]) => (
                    <div key={dateStr} className={styles.timelineGroup}>
                      <div className={styles.timelineDate}>{dateStr}</div>
                      
                      {items.map(p => {
                        const timeStr = p.updated_at ? new Date(p.updated_at).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}) : '剛剛';
                        return (
                          <div key={p.id} className={styles.timelineItem} style={{ backgroundColor: selectedIds.has(p.id) ? 'rgba(216, 162, 92, 0.05)' : undefined }}>
                            <div style={{ marginTop: 4 }}>
                              <Checkbox 
                                checked={selectedIds.has(p.id)} 
                                onChange={() => handleToggleSelect(p.id)} 
                              />
                            </div>
                            <div className={styles.timelineTimeBox}>
                              <div className={styles.timelineTime}>{timeStr}</div>
                              <div className={styles.timelineTag}>記錄</div>
                            </div>
                            
                            <div className={styles.timelineContent}>
                              {editingId === p.id ? (
                                <div style={{ display: 'flex', flexDirection: 'column', gap: 8, paddingRight: 16 }}>
                                  <Input.TextArea 
                                    value={editText}
                                    onChange={e => setEditText(e.target.value)}
                                    autoSize={{ minRows: 2, maxRows: 6 }}
                                  />
                                  <Space style={{ alignSelf: 'flex-end' }}>
                                    <Button size="small" onClick={() => setEditingId(null)}>取消</Button>
                                    <Button size="small" type="primary" onClick={() => handleSaveEdit(p.id)}>儲存</Button>
                                  </Space>
                                </div>
                              ) : (
                                <>
                                  <div className={styles.timelineText}>{cleanMemoryText(p.text)}</div>
                                </>
                              )}
                            </div>
                            
                            {editingId !== p.id && (
                              <div className={`timelineTools ${styles.timelineTools}`}>
                                {p.confidence != null && !isNaN(p.confidence) && (
                                  <span className={styles.confidenceBadge}>
                                    信心: {Number(p.confidence).toFixed(2)}
                                  </span>
                                )}
                                <Button size="small" type="text" icon={<Edit2 size={14} />} onClick={() => { setEditingId(p.id); setEditText(p.text); }} style={{ color: '#aaa' }} />
                                <Popconfirm title="確定要刪除此記憶嗎？" onConfirm={() => deleteMemory(p.id)}>
                                  <Button size="small" type="text" danger icon={<Trash2 size={14} />} />
                                </Popconfirm>
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  ))}
                </div>
              )}
            </div>

            <Modal
              title={
                assetModalType === 'tags' ? '活躍標籤列表' :
                assetModalType === 'scopes' ? '涉及領域列表' : '記憶節點列表'
              }
              open={assetModalVisible}
              onCancel={() => setAssetModalVisible(false)}
              footer={null}
              bodyStyle={{ maxHeight: '60vh', overflowY: 'auto' }}
            >
              {assetModalType === 'tags' && (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                  {uniqueTags.map(t => <Tag key={t} color="cyan">{t}</Tag>)}
                </div>
              )}
              {assetModalType === 'scopes' && (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                  {uniqueScopes.map(s => <Tag key={s} color="blue">{s}</Tag>)}
                </div>
              )}
              {assetModalType === 'nodes' && (
                <List
                  dataSource={longTermProps}
                  renderItem={item => (
                    <List.Item>
                      <List.Item.Meta description={cleanMemoryText(item.text)} />
                    </List.Item>
                  )}
                />
              )}
            </Modal>
          </>
        ) : (
          /* Suggestions View */
          <>
            <div className={styles.heroSection} style={{ marginBottom: 24 }}>
              <div className={styles.heroTitleRow}>
                <Sparkles size={28} style={{ color: '#d4af37' }} />
                <h2>您可能想知道？ (Suggestions)</h2>
              </div>
              <div className={styles.heroSummaryBox}>
                AREQA 會根據您的記憶與歷史對話內容，主動推薦您可能感興趣的議題，幫助您探索更深度的知識。
              </div>
            </div>

            <div className={styles.timelineHeaderRow}>
              <div className={styles.sectionHeader} style={{ marginBottom: 0 }}>
                <Sparkles size={18} style={{ color: '#d4af37' }} />
                <h3>推薦話題列表</h3>
              </div>
              <button className={styles.refreshBtn} onClick={() => fetchSuggestions()} disabled={loading}>
                <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
                重新整理
              </button>
            </div>

            {loading ? (
              <div style={{ display: 'flex', justifyContent: 'center', padding: '40px' }}>
                <Spin size="large" />
              </div>
            ) : suggestions.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '40px', color: '#888' }}>
                目前沒有任何建議。您可以先累積一些對話記憶，再試試看！
              </div>
            ) : (
              <div className={styles.timelineItems}>
                {suggestions.map((s, idx) => (
                  <div key={idx} className={styles.suggestionCard}>
                    <div className={styles.suggestionTitle}>推薦話題 #{idx + 1}</div>
                    <div className={styles.timelineText}>{s}</div>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
