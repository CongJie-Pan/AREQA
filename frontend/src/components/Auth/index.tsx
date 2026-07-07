'use client';

import React, { useState, useEffect } from 'react';
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
    });

    const { data: { subscription } } = supabase.auth.onAuthStateChange((event, session) => {
      setUser(session?.user ?? null);
      if (session?.user) {
        setIsModalOpen(false);
        if (event === 'SIGNED_IN') {
          syncService.pullFromCloud();
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
        data: { username: newUsername }
      });
      if (error) throw error;
      message.success('使用者名稱更新成功！');
      setIsEditModalOpen(false);
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : '更新失敗');
    }
  };

  const displayName = user?.user_metadata?.username || user?.user_metadata?.full_name || user?.email || '訪客';

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
            <h2 style={{ fontSize: '20px', fontWeight: 'bold', marginBottom: '16px', textAlign: 'center', color: 'white' }}>
              登入 AREQA
            </h2>
            <SupabaseAuth 
              supabaseClient={supabase}
              appearance={{ theme: ThemeSupa }}
              theme="dark"
              providers={['google']}
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
          <div style={{
            width: '32px', height: '32px', borderRadius: '50%',
            background: '#d8a25c', display: 'flex',
            alignItems: 'center', justifyContent: 'center'
          }}>
            <span style={{ color: 'black', fontWeight: 'bold', fontSize: '14px' }}>
              {displayName.charAt(0).toUpperCase()}
            </span>
          </div>
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
