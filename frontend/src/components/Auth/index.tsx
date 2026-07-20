'use client';

import React, { useState, useEffect, useCallback } from 'react';
import Image from 'next/image';
import { Modal, Input, Dropdown, MenuProps, message, Button } from 'antd';
import { User, LogOut, Edit3, MessageSquareText } from 'lucide-react';
import { Auth as SupabaseAuth } from '@supabase/auth-ui-react';
import { ThemeSupa } from '@supabase/auth-ui-shared';
import { supabase } from '@/lib/supabase';
import { initializeAuth, useAuthStore } from '@/store/auth';

export function UserAuthUI() {
  const user = useAuthStore((state) => state.user);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [isFeedbackModalOpen, setIsFeedbackModalOpen] = useState(false);
  const [newUsername, setNewUsername] = useState('');
  const [feedbackText, setFeedbackText] = useState('');
  const [isSubmittingFeedback, setIsSubmittingFeedback] = useState(false);
  const authRedirectTo = typeof window !== 'undefined' ? window.location.origin : undefined;

  useEffect(() => {
    void initializeAuth();
  }, []);

  const handleLogout = async () => {
    await supabase.auth.signOut();
    setIsModalOpen(false);
  };

  const handleUpdateUsername = async () => {
    if (!newUsername.trim()) return;
    try {
      const { error } = await supabase.auth.updateUser({
        data: { 
          username: newUsername,
          full_name: newUsername, // Also update full_name for Supabase Dashboard 'Display Name' column
          name: newUsername
        }
      });
      if (error) throw error;
      message.success('使用者名稱更新成功！');
      setIsEditModalOpen(false);
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : '更新失敗');
    }
  };

  const handleSubmitFeedback = async () => {
    const content = feedbackText.trim();
    if (!user || !content || isSubmittingFeedback) return;

    setIsSubmittingFeedback(true);
    try {
      const { error } = await supabase.from('feedback_submissions').insert({
        user_id: user.id,
        email: user.email ?? null,
        display_name: displayName,
        content,
        page_path: typeof window !== 'undefined' ? window.location.pathname : null,
        user_agent: typeof navigator !== 'undefined' ? navigator.userAgent : null,
      });

      if (error) throw error;
      message.success('意見已送出，謝謝你的回饋。');
      setFeedbackText('');
      setIsFeedbackModalOpen(false);
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : '意見送出失敗');
    } finally {
      setIsSubmittingFeedback(false);
    }
  };

  const displayName = user?.user_metadata?.username || user?.user_metadata?.full_name || user?.user_metadata?.name || user?.email || '訪客';
  const avatarUrl = user?.user_metadata?.avatar_url || user?.user_metadata?.picture;

  const menuItems: MenuProps['items'] = [
    {
      key: 'edit',
      icon: <Edit3 size={16} />,
      label: '修改暱稱',
      onClick: () => {
        setNewUsername(displayName);
        setIsEditModalOpen(true);
      }
    },
    {
      key: 'feedback',
      icon: <MessageSquareText size={16} />,
      label: '聯繫我們/意見回饋',
      onClick: () => setIsFeedbackModalOpen(true)
    },
    {
      key: 'logout',
      icon: <LogOut size={16} />,
      label: '登出',
      danger: true,
      onClick: handleLogout
    }
  ];

  if (!user) {
    return (
      <>
        <div 
          onClick={() => setIsModalOpen(true)}
          style={{
            display: 'flex', alignItems: 'center', gap: '8px', padding: '12px',
            marginTop: 'auto', cursor: 'pointer', borderRadius: '8px',
            transition: 'background 0.2s', color: 'rgba(255, 255, 255, 0.7)'
          }}
          onMouseEnter={e => e.currentTarget.style.background = 'rgba(255, 255, 255, 0.05)'}
          onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
        >
          <div style={{
            width: '32px', height: '32px', borderRadius: '50%',
            background: 'rgba(255, 255, 255, 0.1)', display: 'flex',
            alignItems: 'center', justifyContent: 'center'
          }}>
            <User size={16} color="white" />
          </div>
          <span style={{ fontSize: '14px', fontWeight: 500 }}>登入 / 註冊</span>
        </div>

        <Modal
          open={isModalOpen}
          onCancel={() => setIsModalOpen(false)}
          footer={null}
          destroyOnClose
          width={400}
        >
          <div style={{ padding: '16px' }}>
            <div style={{ textAlign: 'center', marginBottom: '20px' }}>
              <h2 style={{ fontSize: '20px', fontWeight: 'bold', marginBottom: '12px', color: 'white' }}>
                登入 / 註冊 AREQA
              </h2>
              <Image 
                src="/icon/areqa_icon_v3.png" 
                alt="AREQA Logo" 
                width={80}
                height={80}
                style={{ objectFit: 'contain', margin: '0 auto', display: 'block' }} 
              />
            </div>
            <SupabaseAuth 
              supabaseClient={supabase}
              appearance={{ theme: ThemeSupa }}
              theme="dark"
              providers={['google']}
              redirectTo={authRedirectTo}
              localization={{
                variables: {
                  sign_in: {
                    email_label: '電子郵件',
                    password_label: '密碼',
                    email_input_placeholder: '您的電子郵件',
                    password_input_placeholder: '您的密碼',
                    button_label: '登入',
                    loading_button_label: '登入中...',
                    social_provider_text: '使用 {{provider}} 登入',
                    link_text: '已經有帳號了嗎？登入'
                  },
                  sign_up: {
                    email_label: '電子郵件',
                    password_label: '密碼',
                    email_input_placeholder: '您的電子郵件',
                    password_input_placeholder: '您的密碼',
                    button_label: '註冊',
                    loading_button_label: '註冊中...',
                    social_provider_text: '使用 {{provider}} 註冊',
                    link_text: '還沒有帳號嗎？註冊',
                    confirmation_text: '請檢查您的信箱以確認註冊。'
                  },
                  forgotten_password: {
                    link_text: '忘記密碼？',
                    email_label: '電子郵件',
                    email_input_placeholder: '您的電子郵件',
                    button_label: '發送密碼重設信',
                    loading_button_label: '發送中...',
                    confirmation_text: '請檢查您的信箱以重設密碼。'
                  }
                }
              }}
            />
          </div>
        </Modal>
      </>
    );
  }

  return (
    <>
      <Dropdown menu={{ items: menuItems }} placement="topLeft" trigger={['click']}>
        <div 
          style={{
            display: 'flex', alignItems: 'center', gap: '8px', padding: '12px',
            marginTop: 'auto', cursor: 'pointer', borderRadius: '8px',
            transition: 'background 0.2s', color: 'rgba(255, 255, 255, 0.7)'
          }}
          onMouseEnter={e => e.currentTarget.style.background = 'rgba(255, 255, 255, 0.05)'}
          onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
        >
          {avatarUrl ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img 
              src={avatarUrl} 
              alt={displayName} 
              style={{
                width: '32px', height: '32px', borderRadius: '50%',
                objectFit: 'cover'
              }}
              referrerPolicy="no-referrer"
            />
          ) : (
            <div style={{
              width: '32px', height: '32px', borderRadius: '50%',
              background: '#d8a25c', display: 'flex',
              alignItems: 'center', justifyContent: 'center'
            }}>
              <span style={{ color: 'black', fontWeight: 'bold', fontSize: '14px' }}>
                {displayName.charAt(0).toUpperCase()}
              </span>
            </div>
          )}
          <span style={{ fontSize: '14px', fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {displayName}
          </span>
        </div>
      </Dropdown>

      <Modal
        title="修改暱稱"
        open={isEditModalOpen}
        onOk={handleUpdateUsername}
        onCancel={() => setIsEditModalOpen(false)}
        okButtonProps={{ style: { backgroundColor: '#d8a25c', color: 'black' } }}
      >
        <Input 
          value={newUsername}
          onChange={e => setNewUsername(e.target.value)}
          placeholder="輸入新暱稱..."
          onPressEnter={handleUpdateUsername}
        />
      </Modal>

      <Modal
        title="聯繫我們/意見回饋"
        open={isFeedbackModalOpen}
        onOk={handleSubmitFeedback}
        onCancel={() => setIsFeedbackModalOpen(false)}
        okText="送出"
        cancelText="取消"
        centered
        confirmLoading={isSubmittingFeedback}
        okButtonProps={{
          disabled: !feedbackText.trim(),
          style: { backgroundColor: '#d8a25c', color: 'black' }
        }}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <Input.TextArea
            value={feedbackText}
            onChange={e => setFeedbackText(e.target.value)}
            placeholder="請輸入你的問題、建議或遇到的狀況..."
            autoSize={{ minRows: 4, maxRows: 8 }}
            maxLength={2000}
          />
          <div style={{ textAlign: 'right', color: 'rgba(255, 255, 255, 0.45)', fontSize: '12px', lineHeight: '16px' }}>
            {feedbackText.length} / 2000
          </div>
        </div>
      </Modal>
    </>
  );
}

export interface AuthPromptProps {
  /** Whether the post-answer authentication prompt is visible. */
  open: boolean;
  /** Closes the prompt without changing the current authentication state. */
  onDismiss: () => void;
}

/**
 * Authentication prompt shown after a successful answer for guest users.
 * The prompt owns its session listener so it closes immediately after sign-in.
 */
export function AuthPrompt({ open, onDismiss }: AuthPromptProps) {
  const user = useAuthStore((state) => state.user);
  const [authView, setAuthView] = useState<'sign_in' | 'sign_up' | null>(null);
  const authRedirectTo = typeof window !== 'undefined' ? window.location.origin : undefined;
  const handleDismiss = useCallback(() => {
    setAuthView(null);
    onDismiss();
  }, [onDismiss]);

  useEffect(() => {
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => {
      if (session?.user) handleDismiss();
    });

    return () => subscription.unsubscribe();
  }, [handleDismiss]);

  if (!open || user) return null;

  return (
    <Modal
      open={open}
      onCancel={handleDismiss}
      footer={null}
      destroyOnHidden
      width={400}
      centered
      title="歡迎來到 AREQA"
    >
      {authView ? (
        <div style={{ paddingTop: '8px' }}>
          <Button type="link" onClick={() => setAuthView(null)}>
            返回
          </Button>
          <SupabaseAuth
            supabaseClient={supabase}
            view={authView}
            appearance={{ theme: ThemeSupa }}
            theme="dark"
            providers={['google']}
            redirectTo={authRedirectTo}
            localization={{
              variables: {
                sign_in: {
                  email_label: '電子郵件',
                  password_label: '密碼',
                  email_input_placeholder: '您的電子郵件',
                  password_input_placeholder: '您的密碼',
                  button_label: '登入',
                  loading_button_label: '登入中...',
                  social_provider_text: '使用 {{provider}} 登入',
                  link_text: '還沒有帳號嗎？註冊',
                },
                sign_up: {
                  email_label: '電子郵件',
                  password_label: '密碼',
                  email_input_placeholder: '您的電子郵件',
                  password_input_placeholder: '您的密碼',
                  button_label: '註冊',
                  loading_button_label: '註冊中...',
                  social_provider_text: '使用 {{provider}} 註冊',
                  link_text: '已經有帳號了嗎？登入',
                  confirmation_text: '請檢查您的信箱以確認註冊。',
                },
              },
            }}
          />
        </div>
      ) : (
        <div style={{ padding: '16px 8px 8px', display: 'grid', gap: '12px' }}>
          <p style={{ margin: 0, textAlign: 'center' }}>
            登入後即可同步您的對話與學習記憶。
          </p>
          <Button type="primary" aria-label="登入" onClick={() => setAuthView('sign_in')}>
            登入
          </Button>
          <Button aria-label="註冊" onClick={() => setAuthView('sign_up')}>
            註冊
          </Button>
          <Button type="text" onClick={handleDismiss}>
            維持登出狀態
          </Button>
        </div>
      )}
    </Modal>
  );
}
