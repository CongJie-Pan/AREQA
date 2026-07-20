import React, { useEffect, useState, useMemo } from 'react';
import { useMailboxStore, Mail } from '@/store/mailbox';
import { useStyles } from './styles';
import { X, Mail as MailIcon, Send, Inbox, ArrowLeft } from 'lucide-react';
import { Input, Button, message } from 'antd';
import { formatUserDate } from '@/utils/dateTime';

export interface MailboxPanelProps {
  onClose?: () => void;
}

// Helper to format date like Gmail (e.g. "6月30日" or "13:09")
const formatMailDate = (timestamp: number) => {
  const date = new Date(timestamp * 1000);
  const now = new Date();
  const dateKeyOptions: Intl.DateTimeFormatOptions = { year: 'numeric', month: 'numeric', day: 'numeric' };
  const isToday = formatUserDate(date, dateKeyOptions) === formatUserDate(now, dateKeyOptions);
  if (isToday) {
    return formatUserDate(date, { hour: '2-digit', minute: '2-digit', hour12: false });
  }
  return formatUserDate(date, { month: 'numeric', day: 'numeric' });
};

export const MailboxPanel: React.FC<MailboxPanelProps> = ({ onClose }) => {
  const { styles, cx } = useStyles();
  const { mails, loading, fetchMails, markAsRead, sendReply, sendingReply } = useMailboxStore();
  const [selectedAvatar, setSelectedAvatar] = useState<string | null>(null);
  const [replyContent, setReplyContent] = useState('');

  useEffect(() => {
    fetchMails();
  }, [fetchMails]);

  // Group mails by avatar (the other person)
  const threads = useMemo(() => {
    const groups = new Map<string, Mail[]>();
    mails.forEach(mail => {
      const avatarName = mail.sender === 'User' ? mail.recipient : mail.sender;
      if (!groups.has(avatarName)) {
        groups.set(avatarName, []);
      }
      groups.get(avatarName)!.push(mail);
    });

    // Sort threads by the latest mail's timestamp
    const sortedGroups = Array.from(groups.entries()).map(([avatar, threadMails]) => {
      // Mails are already sorted descending in store, so index 0 is the latest
      const latestMail = threadMails[0];
      const hasUnread = threadMails.some(m => !m.is_read && m.sender !== 'User');
      return {
        avatar,
        mails: threadMails.reverse(), // Reverse so chronological order for reading
        latestMail,
        hasUnread
      };
    });

    return sortedGroups.sort((a, b) => b.latestMail.timestamp - a.latestMail.timestamp);
  }, [mails]);

  const handleThreadClick = async (avatar: string, threadMails: Mail[]) => {
    setSelectedAvatar(avatar);
    // Mark all unread mails in this thread as read
    let hasUnread = false;
    for (const m of threadMails) {
      if (!m.is_read && m.sender !== 'User') {
        hasUnread = true;
        await markAsRead(m.mail_id);
      }
    }
    if (hasUnread) {
      fetchMails(); // Ensure server syncs the unread count properly
    }
  };

  const handleSendReply = async () => {
    if (!selectedAvatar || !replyContent.trim()) return;
    const success = await sendReply(replyContent, selectedAvatar);
    if (success) {
      setReplyContent('');
      message.success('信件已寄出！');
    } else {
      message.error('發送信件失敗');
    }
  };

  const currentThread = threads.find(t => t.avatar === selectedAvatar);
  // User cannot reply if the latest mail in the thread is from "User"
  const userHasReplied = currentThread && currentThread.mails.length > 0 && currentThread.mails[currentThread.mails.length - 1].sender === 'User';

  return (
    <div className={styles.panel}>
      {/* Header */}
      <div className={styles.header}>
        <div className={styles.titleWrapper}>
          <MailIcon size={28} className="text-amber-500" style={{ color: '#d8a25c' }} />
          <div>
            <h2>信箱</h2>
          </div>
        </div>
        {onClose && (
          <button className={styles.closeBtn} onClick={onClose} title="關閉信箱">
            <X size={20} />
          </button>
        )}
      </div>

      {/* Content */}
      <div className={styles.content} style={{ padding: selectedAvatar ? '24px 32px' : '0' }}>
        {loading && mails.length === 0 ? (
          <div className={styles.emptyState} style={{ padding: '60px 20px' }}>
            <span>載入信件中...</span>
          </div>
        ) : mails.length === 0 ? (
          <div className={styles.emptyState} style={{ padding: '60px 20px' }}>
            <Inbox size={48} style={{ opacity: 0.5 }} />
            <p>目前沒有任何信件，請先在左側開啟歷史對話，人物可能會主動寫信給您喔！</p>
          </div>
        ) : !selectedAvatar ? (
          /* List View */
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            {threads.map(thread => (
              <div 
                key={thread.avatar} 
                className={cx(styles.listRow, thread.hasUnread && 'unread')}
                onClick={() => handleThreadClick(thread.avatar, thread.mails)}
              >
                <div className={styles.rowSender}>
                  {thread.avatar}
                </div>
                <div className={styles.rowSnippet}>
                  {thread.latestMail.sender === 'User' && <span style={{ opacity: 0.5 }}>已回覆：</span>}
                  <span style={{ fontWeight: 600, color: '#fff', marginRight: 8 }}>
                    {thread.latestMail.subject || '來自遠方的信'}
                  </span>
                  <span style={{ opacity: 0.7 }}>
                    - {String(thread.latestMail.content || '').substring(0, 50).replace(/\n/g, ' ')}...
                  </span>
                </div>
                <div className={styles.rowDate}>
                  {formatMailDate(thread.latestMail.timestamp)}
                </div>
              </div>
            ))}
          </div>
        ) : (
          /* Thread Detail View */
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            <div className={styles.threadHeader}>
              <button className={styles.backBtn} onClick={() => setSelectedAvatar(null)}>
                <ArrowLeft size={20} />
              </button>
              <div style={{ display: 'flex', flexDirection: 'column' }}>
                <div className={styles.threadTitle}>與 {selectedAvatar} 的通信</div>
                {currentThread?.latestMail.subject && (
                  <div style={{ fontSize: '0.9rem', color: 'rgba(255,255,255,0.6)', marginTop: 4 }}>
                    主題：{currentThread.latestMail.subject}
                  </div>
                )}
              </div>
            </div>
            
            {currentThread?.mails.map(mail => {
              const isUser = mail.sender === 'User';
              return (
                <div key={mail.mail_id} className={cx(styles.messageItem, isUser && 'user')}>
                  <div className={styles.messageMeta}>
                    <span>{isUser ? '我' : mail.sender}</span>
                    <span>•</span>
                    <span>{formatUserDate(mail.timestamp * 1000, {
                      year: 'numeric',
                      month: 'numeric',
                      day: 'numeric',
                      hour: '2-digit',
                      minute: '2-digit',
                      hour12: false
                    })}</span>
                  </div>
                  <div className={styles.messageBubble}>
                    {mail.content}
                  </div>
                </div>
              );
            })}
            
            {/* Reply Section */}
            <div className={styles.replyBox}>
              {userHasReplied ? (
                <div style={{ color: '#aaa', fontSize: '0.9rem', fontStyle: 'italic', textAlign: 'center' }}>
                  您已回信給 {selectedAvatar}，請靜候對方的回音。
                </div>
              ) : (
                <>
                  <Input.TextArea
                    value={replyContent}
                    onChange={(e) => setReplyContent(e.target.value)}
                    placeholder={`寫信回覆給 ${selectedAvatar}...`}
                    autoSize={{ minRows: 4, maxRows: 8 }}
                    disabled={sendingReply}
                    style={{
                      background: 'rgba(0,0,0,0.2)',
                      color: '#fff',
                      border: '1px solid rgba(255,255,255,0.1)'
                    }}
                  />
                  <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 8 }}>
                    <Button
                      type="primary"
                      icon={<Send size={16} />}
                      onClick={handleSendReply}
                      loading={sendingReply}
                      disabled={!replyContent.trim()}
                      style={{
                        background: replyContent.trim() ? '#d8a25c' : undefined,
                        borderColor: replyContent.trim() ? '#d8a25c' : undefined
                      }}
                    >
                      發送信件
                    </Button>
                  </div>
                </>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
