'use client';

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

export type InterfaceTheme = 'light' | 'dark' | 'system';
export type ResolvedInterfaceTheme = 'light' | 'dark';
export type InterfaceLanguage = 'zh-TW' | 'zh-CN' | 'en';
export type TranslationKey =
  | 'appearance'
  | 'theme.light'
  | 'theme.dark'
  | 'theme.system'
  | 'language'
  | 'language.zhTW'
  | 'language.zhCN'
  | 'language.en'
  | 'browseMemory'
  | 'editNickname'
  | 'feedback'
  | 'logout'
  | 'loginSignup'
  | 'loginSignupAreqa'
  | 'feedbackSent'
  | 'feedbackFailed'
  | 'nicknameUpdated'
  | 'updateFailed'
  | 'editNicknameTitle'
  | 'feedbackTitle'
  | 'submit'
  | 'cancel'
  | 'feedbackPlaceholder'
  | 'welcomeAreqa'
  | 'authPromptCopy'
  | 'login'
  | 'signup'
  | 'staySignedOut'
  | 'back'
  | 'askPlaceholder'
  | 'messageTooLong'
  | 'maxAttachments'
  | 'unsupportedAttachment'
  | 'emptyAttachment'
  | 'attachmentTooLarge'
  | 'attachmentsTooLarge'
  | 'cancelQuote'
  | 'pendingAttachments'
  | 'messageInputRow'
  | 'addAttachment'
  | 'messageTextarea'
  | 'stopGenerating'
  | 'sendMessage'
  | 'chooseAttachment'
  | 'latexPreview'
  | 'formulaPreview'
  | 'newChat'
  | 'mailbox'
  | 'noConversations'
  | 'today'
  | 'yesterday'
  | 'previousSevenDays'
  | 'older'
  | 'pinned'
  | 'rename'
  | 'unpin'
  | 'pin'
  | 'delete'
  | 'conversationMenu'
  | 'renameTitle'
  | 'save'
  | 'renamePlaceholder'
  | 'enterConversationName'
  | 'renameSuccess'
  | 'renameFailed'
  | 'closeSidebar'
  | 'tableActions'
  | 'copyTable'
  | 'downloadTableCsv'
  | 'expandTable'
  | 'scrollableTable'
  | 'table'
  | 'closeExpandedTable'
  | 'copyFormula'
  | 'feedbackThanks'
  | 'feedbackIncorrect'
  | 'feedbackNotWanted'
  | 'feedbackSlow'
  | 'feedbackStyle'
  | 'feedbackSafety'
  | 'feedbackOther';

interface UserPreferencesContextValue {
  theme: InterfaceTheme;
  resolvedTheme: ResolvedInterfaceTheme;
  language: InterfaceLanguage;
  setTheme: (theme: InterfaceTheme) => void;
  setLanguage: (language: InterfaceLanguage) => void;
  t: (key: TranslationKey, params?: Record<string, string | number>) => string;
}

interface UserPreferencesProviderProps {
  children: ReactNode;
}

const THEME_STORAGE_KEY = 'areqa:interface-theme';
const LANGUAGE_STORAGE_KEY = 'areqa:interface-language';
const SYSTEM_DARK_MEDIA_QUERY = '(prefers-color-scheme: dark)';

const SUPPORTED_THEMES: readonly InterfaceTheme[] = ['light', 'dark', 'system'];
const SUPPORTED_LANGUAGES: readonly InterfaceLanguage[] = ['zh-TW', 'zh-CN', 'en'];

const defaultPreferences: UserPreferencesContextValue = {
  theme: 'system',
  resolvedTheme: 'dark',
  language: 'zh-TW',
  setTheme: () => undefined,
  setLanguage: () => undefined,
  t: (key, params) => translate('zh-TW', key, params),
};

const TRANSLATIONS: Record<InterfaceLanguage, Record<TranslationKey, string>> = {
  'zh-TW': {
    appearance: '介面外觀',
    'theme.light': '明亮',
    'theme.dark': '深色',
    'theme.system': '系統',
    language: '語言',
    'language.zhTW': '繁體中文',
    'language.zhCN': '簡體中文',
    'language.en': 'English',
    browseMemory: '瀏覽記憶',
    editNickname: '修改暱稱',
    feedback: '聯繫我們/意見回饋',
    logout: '登出',
    loginSignup: '登入 / 註冊',
    loginSignupAreqa: '登入 / 註冊 AREQA',
    feedbackSent: '意見已送出，謝謝你的回饋。',
    feedbackFailed: '意見送出失敗',
    nicknameUpdated: '使用者名稱更新成功！',
    updateFailed: '更新失敗',
    editNicknameTitle: '修改暱稱',
    feedbackTitle: '聯繫我們/意見回饋',
    submit: '送出',
    cancel: '取消',
    feedbackPlaceholder: '請輸入你的問題、建議或遇到的狀況...',
    welcomeAreqa: '歡迎來到 AREQA',
    authPromptCopy: '登入後即可同步您的對話與學習記憶。',
    login: '登入',
    signup: '註冊',
    staySignedOut: '維持登出狀態',
    back: '返回',
    askPlaceholder: '問我任何問題...',
    messageTooLong: '訊息過長。上限為 {maxLength} 個字元。',
    maxAttachments: '每次最多可附加 {count} 個檔案。',
    unsupportedAttachment: '僅支援 PNG、JPEG、WEBP、GIF、PDF、TXT 與 Markdown 檔案。',
    emptyAttachment: '不接受空白附件。',
    attachmentTooLarge: '單一附件不得超過 5 MB。',
    attachmentsTooLarge: '附件總大小不得超過 20 MB。',
    cancelQuote: '取消引用',
    pendingAttachments: '待送附件',
    messageInputRow: '訊息輸入列',
    addAttachment: '加入圖片或文件',
    messageTextarea: '訊息輸入框',
    stopGenerating: '停止生成',
    sendMessage: '發送訊息',
    chooseAttachment: '選擇附件',
    latexPreview: 'LaTeX 預覽',
    formulaPreview: '公式預覽',
    newChat: '新對話',
    mailbox: '信箱',
    noConversations: '尚無對話紀錄',
    today: '今天',
    yesterday: '昨天',
    previousSevenDays: '過去七天',
    older: '更早以前',
    pinned: '釘選',
    rename: '重新命名',
    unpin: '取消釘選',
    pin: '釘選聊天',
    delete: '刪除',
    conversationMenu: '對話選單',
    renameTitle: '重新命名對話',
    save: '儲存',
    renamePlaceholder: '輸入新的對話名稱',
    enterConversationName: '請輸入對話名稱',
    renameSuccess: '已重新命名對話',
    renameFailed: '重新命名失敗，請稍後再試',
    closeSidebar: '關閉側邊欄',
    tableActions: '表格操作',
    copyTable: '複製表格',
    downloadTableCsv: '下載表格為CSV',
    expandTable: '擴大顯示表格',
    scrollableTable: '可水平捲動的資料表',
    table: '表格',
    closeExpandedTable: '關閉放大表格',
    copyFormula: '複製公式',
    feedbackThanks: '感謝你的回饋',
    feedbackIncorrect: '不正確或不完整',
    feedbackNotWanted: '這不是我想要的',
    feedbackSlow: '緩慢或故障',
    feedbackStyle: '風格或語調',
    feedbackSafety: '安全性或法律疑慮',
    feedbackOther: '其他',
  },
  'zh-CN': {
    appearance: '界面外观',
    'theme.light': '明亮',
    'theme.dark': '深色',
    'theme.system': '系统',
    language: '语言',
    'language.zhTW': '繁体中文',
    'language.zhCN': '简体中文',
    'language.en': 'English',
    browseMemory: '浏览记忆',
    editNickname: '修改昵称',
    feedback: '联系我们/意见反馈',
    logout: '登出',
    loginSignup: '登入 / 注册',
    loginSignupAreqa: '登入 / 注册 AREQA',
    feedbackSent: '意见已送出，谢谢你的反馈。',
    feedbackFailed: '意见送出失败',
    nicknameUpdated: '用户名更新成功！',
    updateFailed: '更新失败',
    editNicknameTitle: '修改昵称',
    feedbackTitle: '联系我们/意见反馈',
    submit: '送出',
    cancel: '取消',
    feedbackPlaceholder: '请输入你的问题、建议或遇到的状况...',
    welcomeAreqa: '欢迎来到 AREQA',
    authPromptCopy: '登入后即可同步您的对话与学习记忆。',
    login: '登入',
    signup: '注册',
    staySignedOut: '维持登出状态',
    back: '返回',
    askPlaceholder: '问我任何问题...',
    messageTooLong: '讯息过长。上限为 {maxLength} 个字符。',
    maxAttachments: '每次最多可附加 {count} 个文件。',
    unsupportedAttachment: '仅支持 PNG、JPEG、WEBP、GIF、PDF、TXT 与 Markdown 文件。',
    emptyAttachment: '不接受空白附件。',
    attachmentTooLarge: '单一附件不得超过 5 MB。',
    attachmentsTooLarge: '附件总大小不得超过 20 MB。',
    cancelQuote: '取消引用',
    pendingAttachments: '待送附件',
    messageInputRow: '讯息输入列',
    addAttachment: '加入图片或文件',
    messageTextarea: '讯息输入框',
    stopGenerating: '停止生成',
    sendMessage: '发送讯息',
    chooseAttachment: '选择附件',
    latexPreview: 'LaTeX 预览',
    formulaPreview: '公式预览',
    newChat: '新对话',
    mailbox: '信箱',
    noConversations: '尚无对话纪录',
    today: '今天',
    yesterday: '昨天',
    previousSevenDays: '过去七天',
    older: '更早以前',
    pinned: '置顶',
    rename: '重新命名',
    unpin: '取消置顶',
    pin: '置顶聊天',
    delete: '删除',
    conversationMenu: '对话菜单',
    renameTitle: '重新命名对话',
    save: '保存',
    renamePlaceholder: '输入新的对话名称',
    enterConversationName: '请输入对话名称',
    renameSuccess: '已重新命名对话',
    renameFailed: '重新命名失败，请稍后再试',
    closeSidebar: '关闭侧边栏',
    tableActions: '表格操作',
    copyTable: '复制表格',
    downloadTableCsv: '下载表格为CSV',
    expandTable: '放大显示表格',
    scrollableTable: '可水平滚动的数据表',
    table: '表格',
    closeExpandedTable: '关闭放大表格',
    copyFormula: '复制公式',
    feedbackThanks: '感谢你的反馈',
    feedbackIncorrect: '不正确或不完整',
    feedbackNotWanted: '这不是我想要的',
    feedbackSlow: '缓慢或故障',
    feedbackStyle: '风格或语调',
    feedbackSafety: '安全性或法律疑虑',
    feedbackOther: '其他',
  },
  en: {
    appearance: 'Appearance',
    'theme.light': 'Light',
    'theme.dark': 'Dark',
    'theme.system': 'System',
    language: 'Language',
    'language.zhTW': 'Traditional Chinese',
    'language.zhCN': 'Simplified Chinese',
    'language.en': 'English',
    browseMemory: 'Memory',
    editNickname: 'Edit nickname',
    feedback: 'Contact / feedback',
    logout: 'Log out',
    loginSignup: 'Log in / Sign up',
    loginSignupAreqa: 'Log in / Sign up to AREQA',
    feedbackSent: 'Feedback sent. Thank you.',
    feedbackFailed: 'Failed to send feedback',
    nicknameUpdated: 'Username updated.',
    updateFailed: 'Update failed',
    editNicknameTitle: 'Edit nickname',
    feedbackTitle: 'Contact / feedback',
    submit: 'Submit',
    cancel: 'Cancel',
    feedbackPlaceholder: 'Describe your question, suggestion, or issue...',
    welcomeAreqa: 'Welcome to AREQA',
    authPromptCopy: 'Log in to sync conversations and learning memory.',
    login: 'Log in',
    signup: 'Sign up',
    staySignedOut: 'Stay signed out',
    back: 'Back',
    askPlaceholder: 'Ask me anything...',
    messageTooLong: 'Message is too long. Limit: {maxLength} characters.',
    maxAttachments: 'You can attach up to {count} files at a time.',
    unsupportedAttachment: 'Only PNG, JPEG, WEBP, GIF, PDF, TXT, and Markdown files are supported.',
    emptyAttachment: 'Empty attachments are not accepted.',
    attachmentTooLarge: 'Each attachment must be 5 MB or smaller.',
    attachmentsTooLarge: 'Total attachment size must be 20 MB or smaller.',
    cancelQuote: 'Cancel quote',
    pendingAttachments: 'Pending attachments',
    messageInputRow: 'Message input row',
    addAttachment: 'Add image or document',
    messageTextarea: 'Message input',
    stopGenerating: 'Stop generating',
    sendMessage: 'Send message',
    chooseAttachment: 'Choose attachment',
    latexPreview: 'LaTeX preview',
    formulaPreview: 'Formula preview',
    newChat: 'New chat',
    mailbox: 'Mailbox',
    noConversations: 'No conversations yet',
    today: 'Today',
    yesterday: 'Yesterday',
    previousSevenDays: 'Previous 7 days',
    older: 'Older',
    pinned: 'Pinned',
    rename: 'Rename',
    unpin: 'Unpin',
    pin: 'Pin chat',
    delete: 'Delete',
    conversationMenu: 'Conversation menu',
    renameTitle: 'Rename conversation',
    save: 'Save',
    renamePlaceholder: 'Enter a new conversation name',
    enterConversationName: 'Enter a conversation name',
    renameSuccess: 'Conversation renamed',
    renameFailed: 'Rename failed. Please try again later.',
    closeSidebar: 'Close sidebar',
    tableActions: 'Table actions',
    copyTable: 'Copy table',
    downloadTableCsv: 'Download table as CSV',
    expandTable: 'Expand table',
    scrollableTable: 'Horizontally scrollable data table',
    table: 'Table',
    closeExpandedTable: 'Close expanded table',
    copyFormula: 'Copy formula',
    feedbackThanks: 'Thanks for your feedback',
    feedbackIncorrect: 'Incorrect or incomplete',
    feedbackNotWanted: 'Not what I wanted',
    feedbackSlow: 'Slow or broken',
    feedbackStyle: 'Style or tone',
    feedbackSafety: 'Safety or legal concern',
    feedbackOther: 'Other',
  },
};

function translate(
  language: InterfaceLanguage,
  key: TranslationKey,
  params?: Record<string, string | number>,
): string {
  const template = TRANSLATIONS[language][key] ?? TRANSLATIONS['zh-TW'][key] ?? key;
  if (!params) return template;

  return Object.entries(params).reduce(
    (text, [paramKey, value]) => text.replaceAll(`{${paramKey}}`, String(value)),
    template,
  );
}

const UserPreferencesContext = createContext<UserPreferencesContextValue>(defaultPreferences);

/**
 * Checks whether a stored value is one of the supported interface themes.
 *
 * Args:
 *   value: Unknown value read from browser storage.
 *
 * Returns:
 *   True when the value can be safely used as an InterfaceTheme.
 */
function isInterfaceTheme(value: unknown): value is InterfaceTheme {
  return typeof value === 'string' && SUPPORTED_THEMES.includes(value as InterfaceTheme);
}

/**
 * Checks whether a stored value is one of the supported interface languages.
 *
 * Args:
 *   value: Unknown value read from browser storage.
 *
 * Returns:
 *   True when the value can be safely used as an InterfaceLanguage.
 */
function isInterfaceLanguage(value: unknown): value is InterfaceLanguage {
  return typeof value === 'string' && SUPPORTED_LANGUAGES.includes(value as InterfaceLanguage);
}

/**
 * Resolves the effective color theme for the current browser environment.
 *
 * Args:
 *   selectedTheme: User-selected theme mode.
 *   prefersDark: Current operating-system dark-mode preference.
 *
 * Returns:
 *   The concrete light or dark theme that should be applied to the UI.
 */
function resolveInterfaceTheme(
  selectedTheme: InterfaceTheme,
  prefersDark: boolean,
): ResolvedInterfaceTheme {
  if (selectedTheme === 'system') {
    return prefersDark ? 'dark' : 'light';
  }

  return selectedTheme;
}

/**
 * Reads persisted preferences without trusting arbitrary localStorage values.
 *
 * Returns:
 *   Sanitized preference values with safe defaults.
 *
 * Side effects:
 *   Reads localStorage when running in a browser.
 */
function readStoredPreferences(): Pick<UserPreferencesContextValue, 'theme' | 'language'> {
  if (typeof window === 'undefined') {
    return { theme: defaultPreferences.theme, language: defaultPreferences.language };
  }

  try {
    const storedTheme = window.localStorage.getItem(THEME_STORAGE_KEY);
    const storedLanguage = window.localStorage.getItem(LANGUAGE_STORAGE_KEY);

    return {
      theme: isInterfaceTheme(storedTheme) ? storedTheme : defaultPreferences.theme,
      language: isInterfaceLanguage(storedLanguage) ? storedLanguage : defaultPreferences.language,
    };
  } catch {
    // Browser privacy modes can deny storage access. Falling back keeps the app usable.
    return { theme: defaultPreferences.theme, language: defaultPreferences.language };
  }
}

/**
 * Reads the current system color preference.
 *
 * Returns:
 *   True when the browser currently prefers dark mode.
 *
 * Side effects:
 *   Reads matchMedia when running in a browser.
 */
function readSystemPrefersDark(): boolean {
  if (typeof window === 'undefined') {
    return true;
  }

  try {
    return window.matchMedia(SYSTEM_DARK_MEDIA_QUERY).matches;
  } catch {
    return true;
  }
}

/**
 * Stores a user preference while keeping storage failures non-fatal.
 *
 * Args:
 *   key: localStorage key owned by the preferences module.
 *   value: Sanitized preference value.
 *
 * Side effects:
 *   Writes localStorage when available.
 */
function persistPreference(key: string, value: string): void {
  if (typeof window === 'undefined') return;

  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Preference persistence is best-effort and must never block the chat UI.
  }
}

/**
 * Provides persisted user interface preferences to client components.
 *
 * Args:
 *   children: React subtree that can read and update preferences.
 *
 * Side effects:
 *   Persists preference changes, listens to system theme changes, and writes
 *   `data-interface-theme`, `data-interface-theme-choice`, and `lang` on the
 *   root document element for CSS and browser language integration.
 */
export function UserPreferencesProvider({ children }: UserPreferencesProviderProps) {
  const [theme, setThemeState] = useState<InterfaceTheme>(() => readStoredPreferences().theme);
  const [language, setLanguageState] = useState<InterfaceLanguage>(
    () => readStoredPreferences().language,
  );
  const [prefersDark, setPrefersDark] = useState(readSystemPrefersDark);

  useEffect(() => {
    if (typeof window === 'undefined') return;

    const mediaQueryList = window.matchMedia(SYSTEM_DARK_MEDIA_QUERY);
    const handleSystemThemeChange = (event: MediaQueryListEvent) => {
      setPrefersDark(event.matches);
    };

    mediaQueryList.addEventListener?.('change', handleSystemThemeChange);

    return () => {
      mediaQueryList.removeEventListener?.('change', handleSystemThemeChange);
    };
  }, []);

  const resolvedTheme = useMemo(
    () => resolveInterfaceTheme(theme, prefersDark),
    [prefersDark, theme],
  );

  useEffect(() => {
    if (typeof document === 'undefined') return;

    document.documentElement.dataset.interfaceTheme = resolvedTheme;
    document.documentElement.dataset.interfaceThemeChoice = theme;
    document.documentElement.lang = language;
  }, [language, resolvedTheme, theme]);

  const setTheme = useCallback((nextTheme: InterfaceTheme) => {
    setThemeState(nextTheme);
    persistPreference(THEME_STORAGE_KEY, nextTheme);
  }, []);

  const setLanguage = useCallback((nextLanguage: InterfaceLanguage) => {
    setLanguageState(nextLanguage);
    persistPreference(LANGUAGE_STORAGE_KEY, nextLanguage);
  }, []);

  const t = useCallback(
    (key: TranslationKey, params?: Record<string, string | number>) => (
      translate(language, key, params)
    ),
    [language],
  );

  const contextValue = useMemo<UserPreferencesContextValue>(
    () => ({
      theme,
      resolvedTheme,
      language,
      setTheme,
      setLanguage,
      t,
    }),
    [language, resolvedTheme, setLanguage, setTheme, t, theme],
  );

  return (
    <UserPreferencesContext.Provider value={contextValue}>
      {children}
    </UserPreferencesContext.Provider>
  );
}

/**
 * Returns the current persisted user interface preferences.
 *
 * Returns:
 *   Theme, resolved theme, language, and setter callbacks.
 */
export function useUserPreferences(): UserPreferencesContextValue {
  return useContext(UserPreferencesContext);
}
