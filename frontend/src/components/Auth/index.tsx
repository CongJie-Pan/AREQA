'use client';

import React, { useState, useEffect } from 'react';
import Image from 'next/image';
import { Modal, Input, Dropdown, MenuProps, message } from 'antd';
import { User, LogOut, Edit3 } from 'lucide-react';
import { Auth as SupabaseAuth } from '@supabase/auth-ui-react';
import { ThemeSupa } from '@supabase/auth-ui-shared';
import { supabase } from '@/lib/supabase';
import { User as SupabaseUser } from '@supabase/supabase-js';
import { syncService } from '@/services/syncService';
import { conversationRepo } from '@/database/repositories/conversationRepo';

export function UserAuthUI() {
  const [user, setUser] = useState<SupabaseUser | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [newUsername, setNewUsername] = useState('');

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      setUser(session?.user ?? null);
      if (session?.user) {
        syncService.pullFromCloud(session.user.id);
      }
    });

    const { data: { subscription } } = supabase.auth.onAuthStateChange((event, session) => {
      setUser(session?.user ?? null);
      if (session?.user) {
        setIsModalOpen(false);
        if (event === 'SIGNED_IN' || event === 'INITIAL_SESSION') {
          syncService.pullFromCloud(session.user.id);
        }
      }
    });

    return () => subscription.unsubscribe();
  }, []);

  const handleLogout = async () => {
    await supabase.auth.signOut();
    await conversationRepo.clearAll();
    window.location.reload(); 
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
                src="/icon/logo_icon_v2.png" 
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
    </>
  );
}
