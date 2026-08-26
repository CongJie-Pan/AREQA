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
  | 'closePanel'
  | 'memoryDeleteSelectedSuccess'
  | 'memoryDeleteFailed'
  | 'memoryContentRequired'
  | 'memoryUpdateSuccess'
  | 'memoryUpdateFailed'
  | 'memoryProfileTitle'
  | 'memorySummaryLoading'
  | 'memorySummaryEmpty'
  | 'memoryAssets'
  | 'memoryAssetCount'
  | 'memoryActiveTags'
  | 'memoryScopes'
  | 'memoryNodes'
  | 'memoryUnitItems'
  | 'memoryUnitEntries'
  | 'memoryTimeline'
  | 'selectAll'
  | 'memoryDeleteSelectedConfirm'
  | 'refresh'
  | 'memoryEmpty'
  | 'memoryJustNow'
  | 'memoryProfileRemembered'
  | 'memoryLongTerm'
  | 'memoryConfidence'
  | 'memoryDeleteConfirm'
  | 'memoryActiveTagsList'
  | 'memoryScopesList'
  | 'memoryNodesList'
  | 'suggestionsPanelTitle'
  | 'suggestionsPanelDescription'
  | 'suggestionsListTitle'
  | 'suggestionsEmpty'
  | 'suggestionItemTitle'
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
  | 'emptyStateGreeting'
  | 'emptyStateLearningPrompt'
  | 'emptyStateTutorPrompt'
  | 'textSelectionCopy'
  | 'textSelectionAskQuote'
  | 'textSelectionExplain'
  | 'textSelectionExplainPrompt'
  | 'quotedTextDefaultPrompt'
  | 'back'
  | 'askPlaceholder'
  | 'thinkingPlaceholder'
  | 'suggestedQuestionsTitle'
  | 'messageTooLong'
  | 'maxAttachments'
  | 'unsupportedAttachment'
  | 'emptyAttachment'
  | 'attachmentTooLarge'
  | 'attachmentsTooLarge'
  | 'dropFilesTitle'
  | 'dropFilesSubtitle'
  | 'attachmentImagePreview'
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
  | 'feedbackOther'
  | 'copyMessage'
  | 'editMessage'
  | 'helpfulReply'
  | 'notHelpfulReply'
  | 'regenerate'
  | 'regenerateMessage'
  | 'feedbackTitleShort'
  | 'feedbackIssue'
  | 'selectIssue'
  | 'feedbackDetailsPlaceholder'
  | 'feedbackPrivacy'
  | 'feedbackSubmit'
  | 'copyMessageSuccess'
  | 'copyMessageFailed'
  | 'saveFeedbackFailed'
  | 'openSidebar'
  | 'shareConversation'
  | 'shareConversationMenu'
  | 'shareLoginRequired'
  | 'shareNoConversation'
  | 'shareLinkCopied'
  | 'shareLinkCreated'
  | 'shareLinkFailed'
  | 'exportMarkdown'
  | 'exportPdf'
  | 'exportDocx'
  | 'exportConversation'
  | 'exportPdfLoading'
  | 'exportDocxLoading'
  | 'exportSuccess'
  | 'exportFailed'
  | 'pipeline.routing'
  | 'pipeline.retrieving'
  | 'pipeline.searchingDense'
  | 'pipeline.searchingSparse'
  | 'pipeline.reranking'
  | 'pipeline.sourcesReady'
  | 'pipeline.generating'
  | 'pipeline.done'
  | 'pipeline.defaultActive'
  | 'pipeline.sourceCount'
  | 'retry';

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
    closePanel: '關閉面板',
    memoryDeleteSelectedSuccess: '成功刪除 {count} 筆記憶',
    memoryDeleteFailed: '刪除記憶失敗',
    memoryContentRequired: '記憶內容不能為空',
    memoryUpdateSuccess: '記憶更新成功',
    memoryUpdateFailed: '記憶更新失敗',
    memoryProfileTitle: 'AREQA 眼中的你',
    memorySummaryLoading: '正在為您生成專屬記憶綜整...',
    memorySummaryEmpty: '目前還沒有足夠的記憶能為您生成總結。',
    memoryAssets: '記憶資產',
    memoryAssetCount: '({count}條)',
    memoryActiveTags: '活躍標籤',
    memoryScopes: '涉及領域',
    memoryNodes: '記憶節點',
    memoryUnitItems: '個',
    memoryUnitEntries: '條',
    memoryTimeline: '時間線',
    selectAll: '全選',
    memoryDeleteSelectedConfirm: '確定要刪除選取的 {count} 筆記憶嗎？',
    refresh: '重新整理',
    memoryEmpty: '目前還沒有任何記憶紀錄喔！開始與AREQA聊天吧。',
    memoryJustNow: '剛剛',
    memoryProfileRemembered: '已記住',
    memoryLongTerm: '長期記憶',
    memoryConfidence: '信心',
    memoryDeleteConfirm: '確定要刪除此記憶嗎？',
    memoryActiveTagsList: '活躍標籤列表',
    memoryScopesList: '涉及領域列表',
    memoryNodesList: '記憶節點列表',
    suggestionsPanelTitle: '您可能想知道？',
    suggestionsPanelDescription: 'AREQA 會根據您的記憶與歷史對話內容，主動推薦您可能感興趣的議題，幫助您探索更深度的知識。',
    suggestionsListTitle: '推薦話題列表',
    suggestionsEmpty: '目前沒有任何建議。您可以先累積一些對話記憶，再試試看！',
    suggestionItemTitle: '推薦話題 #{index}',
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
    emptyStateGreeting: '嗨! 我是 AREQA👋，你最好的學習夥伴。😊🌸',
    emptyStateLearningPrompt: '今天想學什麼呢？🤔',
    emptyStateTutorPrompt: '我也是一位 AI Tutor喔，可以與你一步步拆解難題！😎',
    textSelectionCopy: '複製',
    textSelectionAskQuote: '問AREQA(引用)',
    textSelectionExplain: '幫我解釋',
    textSelectionExplainPrompt: '請幫我解釋這段文字：\n\n{text}',
    quotedTextDefaultPrompt: '請回答這段引用內容。',
    back: '返回',
    askPlaceholder: '提問AREQA',
    thinkingPlaceholder: '正在努力思考...',
    suggestedQuestionsTitle: '您可能還想了解：',
    messageTooLong: '訊息過長。上限為 {maxLength} 個字元。',
    maxAttachments: '每次最多可附加 {count} 個檔案。',
    unsupportedAttachment: '僅支援 PNG、JPEG、WEBP、GIF、PDF、TXT 與 Markdown 檔案。',
    emptyAttachment: '不接受空白附件。',
    attachmentTooLarge: '單一附件不得超過 5 MB。',
    attachmentsTooLarge: '附件總大小不得超過 20 MB。',
    dropFilesTitle: '放開即可附加檔案',
    dropFilesSubtitle: '支援圖片、PDF、TXT 與 Markdown',
    attachmentImagePreview: '圖片附件預覽',
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
    copyMessage: '複製訊息',
    editMessage: '編輯訊息',
    helpfulReply: '這則回覆有幫助',
    notHelpfulReply: '這則回覆沒有幫助',
    regenerate: '重新生成',
    regenerateMessage: '重新生成訊息',
    feedbackTitleShort: '分享回饋',
    feedbackIssue: '問題',
    selectIssue: '選取問題',
    feedbackDetailsPlaceholder: '分享詳細資料（選填）',
    feedbackPrivacy: '你的回饋將包含你的對話，以協助我們改善 AREQA。',
    feedbackSubmit: '提交',
    copyMessageSuccess: '已複製到剪貼簿',
    copyMessageFailed: '複製失敗',
    saveFeedbackFailed: '儲存評價失敗',
    openSidebar: '打開選單',
    shareConversation: '分享',
    shareConversationMenu: '對話操作選單',
    shareLoginRequired: '請先登入後再分享對話。',
    shareNoConversation: '目前沒有可分享的對話。',
    shareLinkCopied: '已公開並複製分享連結',
    shareLinkCreated: '分享連結已建立：',
    shareLinkFailed: 'Failed to create share link. Please try again later.',
    exportMarkdown: '下載為 Markdown (.md)',
    exportPdf: '下載為 PDF (.pdf)',
    exportDocx: '下載為 Word (.docx)',
    exportConversation: '匯出對話',
    exportPdfLoading: '正在產生 PDF，請稍候...',
    exportDocxLoading: '正在產生 Word 文件，請稍候...',
    exportSuccess: '下載成功！',
    exportFailed: '下載失敗，請稍後再試',
    'pipeline.routing': '正在分析問題',
    'pipeline.retrieving': '正在整理檢索策略',
    'pipeline.searchingDense': '正在搜尋相關文獻',
    'pipeline.searchingSparse': '正在比對關鍵字線索',
    'pipeline.reranking': '正在排序最相關的資料',
    'pipeline.sourcesReady': '已完成文獻檢索',
    'pipeline.generating': '正在生成回答',
    'pipeline.done': '已完成',
    'pipeline.defaultActive': '正在處理對話狀態',
    'pipeline.sourceCount': '找到 {count} 筆文獻',
    retry: '重試',
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
    closePanel: '关闭面板',
    memoryDeleteSelectedSuccess: '成功删除 {count} 笔记忆',
    memoryDeleteFailed: '删除记忆失败',
    memoryContentRequired: '记忆内容不能为空',
    memoryUpdateSuccess: '记忆更新成功',
    memoryUpdateFailed: '记忆更新失败',
    memoryProfileTitle: 'AREQA 眼中的你',
    memorySummaryLoading: '正在为您生成专属记忆综整...',
    memorySummaryEmpty: '目前还没有足够的记忆能为您生成总结。',
    memoryAssets: '记忆资产',
    memoryAssetCount: '({count}条)',
    memoryActiveTags: '活跃标签',
    memoryScopes: '涉及领域',
    memoryNodes: '记忆节点',
    memoryUnitItems: '个',
    memoryUnitEntries: '条',
    memoryTimeline: '时间线',
    selectAll: '全选',
    memoryDeleteSelectedConfirm: '确定要删除选取的 {count} 笔记忆吗？',
    refresh: '重新整理',
    memoryEmpty: '目前还没有任何记忆纪录喔！开始与AREQA聊天吧。',
    memoryJustNow: '刚刚',
    memoryProfileRemembered: '已记住',
    memoryLongTerm: '长期记忆',
    memoryConfidence: '信心',
    memoryDeleteConfirm: '确定要删除此记忆吗？',
    memoryActiveTagsList: '活跃标签列表',
    memoryScopesList: '涉及领域列表',
    memoryNodesList: '记忆节点列表',
    suggestionsPanelTitle: '您可能想知道？',
    suggestionsPanelDescription: 'AREQA 会根据您的记忆与历史对话内容，主动推荐您可能感兴趣的议题，帮助您探索更深度的知识。',
    suggestionsListTitle: '推荐话题列表',
    suggestionsEmpty: '目前没有任何建议。您可以先累积一些对话记忆，再试试看！',
    suggestionItemTitle: '推荐话题 #{index}',
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
    emptyStateGreeting: '嗨！我是 AREQA，你最好的学习伙伴。',
    emptyStateLearningPrompt: '今天你想学什么？',
    emptyStateTutorPrompt: '我也是 AI Tutor，可以一步一步教你！',
    textSelectionCopy: '复制',
    textSelectionAskQuote: '问AREQA(引用)',
    textSelectionExplain: '帮我解释',
    textSelectionExplainPrompt: '请帮我解释这段文字：\n\n{text}',
    quotedTextDefaultPrompt: '请回答这段引用内容。',
    back: '返回',
    askPlaceholder: '提问AREQA',
    thinkingPlaceholder: '正在努力思考...',
    suggestedQuestionsTitle: '您可能还想了解：',
    messageTooLong: '讯息过长。上限为 {maxLength} 个字符。',
    maxAttachments: '每次最多可附加 {count} 个文件。',
    unsupportedAttachment: '仅支持 PNG、JPEG、WEBP、GIF、PDF、TXT 与 Markdown 文件。',
    emptyAttachment: '不接受空白附件。',
    attachmentTooLarge: '单一附件不得超过 5 MB。',
    attachmentsTooLarge: '附件总大小不得超过 20 MB。',
    dropFilesTitle: '放开即可附加文件',
    dropFilesSubtitle: '支持图片、PDF、TXT 与 Markdown',
    attachmentImagePreview: '图片附件预览',
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
    copyMessage: '复制讯息',
    editMessage: '编辑讯息',
    helpfulReply: '这则回复有帮助',
    notHelpfulReply: '这则回复没有帮助',
    regenerate: '重新生成',
    regenerateMessage: '重新生成讯息',
    feedbackTitleShort: '分享反馈',
    feedbackIssue: '问题',
    selectIssue: '选取问题',
    feedbackDetailsPlaceholder: '分享详细资料（选填）',
    feedbackPrivacy: '你的反馈将包含你的对话，以协助我们改善 AREQA。',
    feedbackSubmit: '提交',
    copyMessageSuccess: '已复制到剪贴簿',
    copyMessageFailed: '复制失败',
    saveFeedbackFailed: '储存评价失败',
    openSidebar: '打开菜单',
    shareConversation: '分享',
    shareConversationMenu: '对话操作菜单',
    shareLoginRequired: '请先登入后再分享对话。',
    shareNoConversation: '目前没有可分享的对话。',
    shareLinkCopied: '已公开并复制分享链接',
    shareLinkCreated: '分享链接已建立：',
    shareLinkFailed: 'Failed to create share link. Please try again later.',
    exportMarkdown: '下载为 Markdown (.md)',
    exportPdf: '下载为 PDF (.pdf)',
    exportDocx: '下载为 Word (.docx)',
    exportConversation: '汇出对话',
    exportPdfLoading: '正在生成 PDF，请稍候...',
    exportDocxLoading: '正在生成 Word 文件，请稍候...',
    exportSuccess: '下载成功！',
    exportFailed: '下载失败，请稍后再试',
    'pipeline.routing': '正在分析问题',
    'pipeline.retrieving': '正在整理检索策略',
    'pipeline.searchingDense': '正在搜索相关文献',
    'pipeline.searchingSparse': '正在比对关键词线索',
    'pipeline.reranking': '正在排序最相关的资料',
    'pipeline.sourcesReady': '已完成文献检索',
    'pipeline.generating': '正在生成回答',
    'pipeline.done': '已完成',
    'pipeline.defaultActive': '正在处理对话状态',
    'pipeline.sourceCount': '找到 {count} 篇文献',
    retry: '重试',
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
    closePanel: 'Close panel',
    memoryDeleteSelectedSuccess: 'Deleted {count} memories',
    memoryDeleteFailed: 'Failed to delete memory',
    memoryContentRequired: 'Memory content cannot be empty',
    memoryUpdateSuccess: 'Memory updated',
    memoryUpdateFailed: 'Failed to update memory',
    memoryProfileTitle: 'How AREQA sees you',
    memorySummaryLoading: 'Generating your memory summary...',
    memorySummaryEmpty: 'There is not enough memory yet to generate a summary.',
    memoryAssets: 'Memory assets',
    memoryAssetCount: '({count})',
    memoryActiveTags: 'Active tags',
    memoryScopes: 'Related domains',
    memoryNodes: 'Memory nodes',
    memoryUnitItems: 'items',
    memoryUnitEntries: 'entries',
    memoryTimeline: 'Timeline',
    selectAll: 'Select all',
    memoryDeleteSelectedConfirm: 'Delete the selected {count} memories?',
    refresh: 'Refresh',
    memoryEmpty: 'No memory records yet. Start chatting with AREQA.',
    memoryJustNow: 'Just now',
    memoryProfileRemembered: 'Remembered',
    memoryLongTerm: 'Long-term',
    memoryConfidence: 'Confidence',
    memoryDeleteConfirm: 'Delete this memory?',
    memoryActiveTagsList: 'Active tags',
    memoryScopesList: 'Related domains',
    memoryNodesList: 'Memory nodes',
    suggestionsPanelTitle: 'Suggestions',
    suggestionsPanelDescription: 'AREQA uses your memory and past conversations to recommend topics you may want to explore next.',
    suggestionsListTitle: 'Suggested topics',
    suggestionsEmpty: 'No suggestions yet. Build up more conversation memory and try again.',
    suggestionItemTitle: 'Suggested topic #{index}',
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
    emptyStateGreeting: "Hi ! I'm AREQA. Your Best Learning Partner.",
    emptyStateLearningPrompt: 'What do you want to learn today ?',
    emptyStateTutorPrompt: "I'm also an AI Tutor, can teach you step-by-step !",
    textSelectionCopy: 'Copy',
    textSelectionAskQuote: 'Ask AREQA (quote)',
    textSelectionExplain: 'Explain',
    textSelectionExplainPrompt: 'Please explain this passage:\n\n{text}',
    quotedTextDefaultPrompt: 'Please answer this quoted passage.',
    back: 'Back',
    askPlaceholder: 'Ask AREQA',
    thinkingPlaceholder: 'Thinking...',
    suggestedQuestionsTitle: 'You may also want to know:',
    messageTooLong: 'Message is too long. Limit: {maxLength} characters.',
    maxAttachments: 'You can attach up to {count} files at a time.',
    unsupportedAttachment: 'Only PNG, JPEG, WEBP, GIF, PDF, TXT, and Markdown files are supported.',
    emptyAttachment: 'Empty attachments are not accepted.',
    attachmentTooLarge: 'Each attachment must be 5 MB or smaller.',
    attachmentsTooLarge: 'Total attachment size must be 20 MB or smaller.',
    dropFilesTitle: 'Drop to attach files',
    dropFilesSubtitle: 'Images, PDF, TXT, and Markdown are supported',
    attachmentImagePreview: 'Image attachment preview',
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
    copyMessage: 'Copy message',
    editMessage: 'Edit message',
    helpfulReply: 'This reply was helpful',
    notHelpfulReply: 'This reply was not helpful',
    regenerate: 'Regenerate',
    regenerateMessage: 'Regenerate message',
    feedbackTitleShort: 'Share feedback',
    feedbackIssue: 'Issue',
    selectIssue: 'Select an issue',
    feedbackDetailsPlaceholder: 'Share details (optional)',
    feedbackPrivacy: 'Your feedback will include your conversation to help us improve AREQA.',
    feedbackSubmit: 'Submit',
    copyMessageSuccess: 'Copied to clipboard',
    copyMessageFailed: 'Copy failed',
    saveFeedbackFailed: 'Failed to save feedback',
    openSidebar: 'Open menu',
    shareConversation: 'Share',
    shareConversationMenu: 'Conversation actions',
    shareLoginRequired: 'Log in before sharing a conversation.',
    shareNoConversation: 'There is no conversation to share yet.',
    shareLinkCopied: 'Public share link copied',
    shareLinkCreated: 'Share link created: ',
    shareLinkFailed: 'Failed to create share link. Please try again later.',
    exportMarkdown: 'Download as Markdown (.md)',
    exportPdf: 'Download as PDF (.pdf)',
    exportDocx: 'Download as Word (.docx)',
    exportConversation: 'Export conversation',
    exportPdfLoading: 'Creating PDF...',
    exportDocxLoading: 'Creating Word document...',
    exportSuccess: 'Download complete.',
    exportFailed: 'Download failed. Please try again later.',
    'pipeline.routing': 'Analyzing the question',
    'pipeline.retrieving': 'Preparing the retrieval strategy',
    'pipeline.searchingDense': 'Searching related sources',
    'pipeline.searchingSparse': 'Matching keyword signals',
    'pipeline.reranking': 'Ranking the most relevant material',
    'pipeline.sourcesReady': 'Source retrieval complete',
    'pipeline.generating': 'Generating the answer',
    'pipeline.done': 'Complete',
    'pipeline.defaultActive': 'Processing the conversation state',
    'pipeline.sourceCount': 'Found {count} sources',
    retry: 'Retry',
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
