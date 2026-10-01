'use client';

import React, { useState, useEffect, useCallback } from 'react';
import Image from 'next/image';
import { Modal, Input, Dropdown, MenuProps, message, Button } from 'antd';
import {
  BrainCircuit,
  Check,
  ChevronRight,
  Edit3,
  Languages,
  LogOut,
  MessageSquareText,
  Monitor,
  Moon,
  NotebookText,
  Sun,
  User,
} from 'lucide-react';
import { Auth as SupabaseAuth } from '@supabase/auth-ui-react';
import { ThemeSupa } from '@supabase/auth-ui-shared';
import { supabase } from '@/lib/supabase';
import { initializeAuth, useAuthStore } from '@/store/auth';
import {
  useUserPreferences,
  type InterfaceLanguage,
  type InterfaceTheme,
} from '@/contexts/UserPreferencesContext';

export interface UserAuthUIProps {
  /** Opens the learner memory panel from the authenticated avatar menu. */
  onOpenMemory?: () => void;
  /** Opens the saved notes panel from the authenticated avatar menu. */
  onOpenNotes?: () => void;
}

const THEME_OPTIONS: Array<{
  value: InterfaceTheme;
  label: string;
  icon: React.ReactNode;
}> = [
  { value: 'light', label: '明亮 Light', icon: <Sun size={14} /> },
  { value: 'dark', label: '黑夜 Dark', icon: <Moon size={14} /> },
  { value: 'system', label: '系統預設 Default', icon: <Monitor size={14} /> },
];

const LANGUAGE_OPTIONS: Array<{
  value: InterfaceLanguage;
  label: string;
}> = [
  { value: 'zh-TW', label: '繁體中文' },
  { value: 'zh-CN', label: '簡體中文' },
  { value: 'en', label: '英文' },
];

const AUTH_LOCALIZATIONS = {
  en: { variables: {} },
  'zh-TW': {
    variables: {
      sign_in: {
        email_label: '電子郵件', password_label: '密碼',
        email_input_placeholder: '您的電子郵件', password_input_placeholder: '您的密碼',
        button_label: '登入', loading_button_label: '登入中...',
        social_provider_text: '使用 {{provider}} 登入', link_text: '還沒有帳號嗎？註冊',
      },
      sign_up: {
        email_label: '電子郵件', password_label: '密碼',
        email_input_placeholder: '您的電子郵件', password_input_placeholder: '您的密碼',
        button_label: '註冊', loading_button_label: '註冊中...',
        social_provider_text: '使用 {{provider}} 註冊', link_text: '已經有帳號了嗎？登入',
        confirmation_text: '請檢查您的信箱以確認註冊。',
      },
      forgotten_password: {
        link_text: '忘記密碼？', email_label: '電子郵件',
        email_input_placeholder: '您的電子郵件', button_label: '發送密碼重設信',
        loading_button_label: '發送中...', confirmation_text: '請檢查您的信箱以重設密碼。',
      },
    },
  },
  'zh-CN': {
    variables: {
      sign_in: {
        email_label: '电子邮箱', password_label: '密码',
        email_input_placeholder: '您的电子邮箱', password_input_placeholder: '您的密码',
        button_label: '登录', loading_button_label: '登录中...',
        social_provider_text: '使用 {{provider}} 登录', link_text: '还没有账号？注册',
      },
      sign_up: {
        email_label: '电子邮箱', password_label: '密码',
        email_input_placeholder: '您的电子邮箱', password_input_placeholder: '您的密码',
        button_label: '注册', loading_button_label: '注册中...',
        social_provider_text: '使用 {{provider}} 注册', link_text: '已有账号？登录',
        confirmation_text: '请检查您的邮箱以确认注册。',
      },
      forgotten_password: {
        link_text: '忘记密码？', email_label: '电子邮箱',
        email_input_placeholder: '您的电子邮箱', button_label: '发送密码重置信',
        loading_button_label: '发送中...', confirmation_text: '请检查您的邮箱以重置密码。',
      },
    },
  },
};

export function UserAuthUI({ onOpenMemory, onOpenNotes }: UserAuthUIProps) {
  const user = useAuthStore((state) => state.user);
  const {
    theme: interfaceTheme,
    resolvedTheme,
    language,
    setTheme,
    setLanguage,
    t,
  } = useUserPreferences();
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
      message.success(t('nicknameUpdated'));
      setIsEditModalOpen(false);
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : t('updateFailed'));
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
      message.success(t('feedbackSent'));
      setFeedbackText('');
      setIsFeedbackModalOpen(false);
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : t('feedbackFailed'));
    } finally {
      setIsSubmittingFeedback(false);
    }
  };

  const displayName = user?.user_metadata?.username || user?.user_metadata?.full_name || user?.user_metadata?.name || user?.email || '訪客';
  const avatarUrl = user?.user_metadata?.avatar_url || user?.user_metadata?.picture;
  const authTheme = resolvedTheme === 'dark' ? 'dark' : 'default';

  const menuItems: MenuProps['items'] = [
    ...(onOpenMemory
      ? [
          {
            key: 'memory',
            icon: <BrainCircuit size={16} />,
            label: t('browseMemory'),
            onClick: onOpenMemory,
          },
        ]
      : []),
    ...(onOpenNotes
      ? [
          {
            key: 'notes',
            icon: <NotebookText size={16} />,
            label: t('browseNotes'),
            onClick: onOpenNotes,
          },
        ]
      : []),
    {
      key: 'edit',
      icon: <Edit3 size={16} />,
      label: t('editNickname'),
      onClick: () => {
        setNewUsername(displayName);
        setIsEditModalOpen(true);
      }
    },
    {
      key: 'feedback',
      icon: <MessageSquareText size={16} />,
      label: t('feedback'),
      onClick: () => setIsFeedbackModalOpen(true)
    },
    {
      key: 'logout',
      icon: <LogOut size={16} />,
      label: t('logout'),
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
          <span style={{ fontSize: '14px', fontWeight: 500 }}>{t('loginSignup')}</span>
        </div>

        <Modal
          open={isModalOpen}
          onCancel={() => setIsModalOpen(false)}
          footer={null}
          destroyOnHidden
          width={400}
        >
          <div style={{ padding: '16px' }}>
            <div style={{ textAlign: 'center', marginBottom: '20px' }}>
              <h2 style={{ fontSize: '20px', fontWeight: 'bold', marginBottom: '12px', color: 'white' }}>
                {t('loginSignupAreqa')}
              </h2>
              <Image 
                src="/icon/areqa_icon_v4_circle.png" 
                alt="AREQA Logo" 
                width={80}
                height={80}
                unoptimized
                style={{ objectFit: 'contain', margin: '0 auto', display: 'block' }} 
              />
            </div>
            <SupabaseAuth 
              supabaseClient={supabase}
              appearance={{ theme: ThemeSupa }}
              theme={authTheme}
              providers={['google']}
              redirectTo={authRedirectTo}
              localization={AUTH_LOCALIZATIONS[language]}
            />
          </div>
        </Modal>
      </>
    );
  }

  return (
    <>
      <Dropdown
        menu={{ items: menuItems }}
        classNames={{ root: 'areqa-account-dropdown' }}
        placement="topLeft"
        popupRender={(menus) => (
          <div className="areqa-account-dropdown-panel">
            <AccountPreferenceControls
              selectedTheme={interfaceTheme}
              selectedLanguage={language}
              onThemeChange={setTheme}
              onLanguageChange={setLanguage}
            />
            <div className="areqa-account-dropdown-divider" />
            {menus}
          </div>
        )}
        trigger={['click']}
      >
        <div 
          style={{
            display: 'flex', alignItems: 'center', gap: '8px', padding: '12px',
            marginTop: 'auto', cursor: 'pointer', borderRadius: '8px',
            transition: 'background 0.2s', color: 'var(--areqa-account-muted-text)'
          }}
          onMouseEnter={e => e.currentTarget.style.background = 'var(--areqa-account-hover)'}
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
        title={t('editNicknameTitle')}
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
        title={t('feedbackTitle')}
        open={isFeedbackModalOpen}
        onOk={handleSubmitFeedback}
        onCancel={() => setIsFeedbackModalOpen(false)}
        okText={t('submit')}
        cancelText={t('cancel')}
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
            placeholder={t('feedbackPlaceholder')}
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

interface AccountPreferenceControlsProps {
  selectedTheme: InterfaceTheme;
  selectedLanguage: InterfaceLanguage;
  onThemeChange: (theme: InterfaceTheme) => void;
  onLanguageChange: (language: InterfaceLanguage) => void;
}

/**
 * Account menu preference controls rendered above the standard account actions.
 *
 * Args:
 *   selectedTheme: Currently selected persisted theme choice.
 *   selectedLanguage: Currently selected persisted language choice.
 *   onThemeChange: Callback that persists a sanitized theme choice.
 *   onLanguageChange: Callback that persists a sanitized language choice.
 *
 * Side effects:
 *   Stops pointer and click propagation so preference changes do not close the
 *   surrounding Ant Design dropdown before the user finishes selection.
 */
function AccountPreferenceControls({
  selectedTheme,
  selectedLanguage,
  onThemeChange,
  onLanguageChange,
}: AccountPreferenceControlsProps) {
  const { t } = useUserPreferences();
  const stopDropdownDismissal = (event: React.SyntheticEvent) => {
    event.stopPropagation();
  };
  const [activePanel, setActivePanel] = useState<'theme' | 'language' | null>(null);
  const themeLabelByValue: Record<InterfaceTheme, string> = {
    light: t('theme.light'),
    dark: t('theme.dark'),
    system: t('theme.system'),
  };
  const languageLabelByValue: Record<InterfaceLanguage, string> = {
    'zh-TW': t('language.zhTW'),
    'zh-CN': t('language.zhCN'),
    en: t('language.en'),
  };
  const selectedThemeLabel = themeLabelByValue[selectedTheme];
  const selectedLanguageLabel = languageLabelByValue[selectedLanguage];

  return (
    <div
      className="areqa-account-preferences"
      onClick={stopDropdownDismissal}
      onMouseDown={stopDropdownDismissal}
      onPointerDown={stopDropdownDismissal}
    >
      <PreferenceSubmenuRow
        icon={<Moon size={18} />}
        label={t('appearance')}
        summary={selectedTheme === 'system' ? `${t('theme.system')} (${selectedThemeLabel})` : selectedThemeLabel}
        onClick={() => setActivePanel(activePanel === 'theme' ? null : 'theme')}
        expanded={activePanel === 'theme'}
      />
      <PreferenceSubmenuRow
        icon={<Languages size={18} />}
        label={t('language')}
        summary={selectedLanguageLabel}
        onClick={() => setActivePanel(activePanel === 'language' ? null : 'language')}
        expanded={activePanel === 'language'}
      />
      {activePanel && (
        <PreferenceToggleGroup
          ariaLabel={activePanel === 'theme' ? t('appearance') : t('language')}
          placement={activePanel}
        >
          {activePanel === 'theme'
            ? THEME_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  className="areqa-account-toggle-option"
                  data-selected={selectedTheme === option.value}
                  aria-pressed={selectedTheme === option.value}
                  onClick={() => onThemeChange(option.value)}
                >
                  <span aria-hidden="true">{option.icon}</span>
                  <span>{themeLabelByValue[option.value]}</span>
                  {selectedTheme === option.value && <Check size={14} aria-hidden="true" />}
                </button>
              ))
            : LANGUAGE_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  className="areqa-account-toggle-option"
                  data-selected={selectedLanguage === option.value}
                  aria-pressed={selectedLanguage === option.value}
                  onClick={() => onLanguageChange(option.value)}
                >
                  <span>{languageLabelByValue[option.value]}</span>
                  {selectedLanguage === option.value && <Check size={14} aria-hidden="true" />}
                </button>
              ))}
        </PreferenceToggleGroup>
      )}
    </div>
  );
}

interface PreferenceSubmenuRowProps {
  icon: React.ReactNode;
  label: string;
  summary: string;
  expanded: boolean;
  onClick: () => void;
}

function PreferenceSubmenuRow({
  icon,
  label,
  summary,
  expanded,
  onClick,
}: PreferenceSubmenuRowProps) {
  return (
    <button
      aria-expanded={expanded}
      className="areqa-account-preference-row"
      onClick={onClick}
      type="button"
    >
      <span className="areqa-account-preference-row-main">
        <span className="areqa-account-preference-icon" aria-hidden="true">
          {icon}
        </span>
        <span>
          <span className="areqa-account-preference-label">{label}</span>
          <span className="areqa-account-preference-summary">{summary}</span>
        </span>
      </span>
      <ChevronRight className="areqa-account-preference-chevron" size={18} aria-hidden="true" />
    </button>
  );
}

interface PreferenceToggleGroupProps {
  ariaLabel: string;
  placement: 'theme' | 'language';
  children: React.ReactNode;
}

function PreferenceToggleGroup({
  ariaLabel,
  placement,
  children,
}: PreferenceToggleGroupProps) {
  return (
    <div
      className="areqa-account-toggle-list"
      data-placement={placement}
      role="group"
      aria-label={ariaLabel}
    >
      {children}
    </div>
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
  const { resolvedTheme, language, t } = useUserPreferences();
  const [authView, setAuthView] = useState<'sign_in' | 'sign_up' | null>(null);
  const authRedirectTo = typeof window !== 'undefined' ? window.location.origin : undefined;
  const authTheme = resolvedTheme === 'dark' ? 'dark' : 'default';
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
      title={t('welcomeAreqa')}
    >
      {authView ? (
        <div style={{ paddingTop: '8px' }}>
          <Button type="link" onClick={() => setAuthView(null)}>
            {t('back')}
          </Button>
          <SupabaseAuth
            supabaseClient={supabase}
            view={authView}
            appearance={{ theme: ThemeSupa }}
            theme={authTheme}
            providers={['google']}
            redirectTo={authRedirectTo}
            localization={AUTH_LOCALIZATIONS[language]}
          />
        </div>
      ) : (
        <div style={{ padding: '16px 8px 8px', display: 'grid', gap: '12px' }}>
          <p style={{ margin: 0, textAlign: 'center' }}>
            {t('authPromptCopy')}
          </p>
          <Button type="primary" aria-label={t('login')} onClick={() => setAuthView('sign_in')}>
            {t('login')}
          </Button>
          <Button aria-label={t('signup')} onClick={() => setAuthView('sign_up')}>
            {t('signup')}
          </Button>
          <Button type="text" onClick={handleDismiss}>
            {t('staySignedOut')}
          </Button>
        </div>
      )}
    </Modal>
  );
}
