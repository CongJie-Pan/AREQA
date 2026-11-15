'use client';

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from 'react';

import {
  DEFAULT_INTERFACE_PREFERENCES,
  THEME_STORAGE_KEY,
  LANGUAGE_STORAGE_KEY,
  readBrowserPreferences,
  writePreferenceCookies,
  type InterfacePreferences,
  type InterfaceTheme,
  type ResolvedInterfaceTheme,
  type InterfaceLanguage,
} from '@/lib/interfacePreferences';
export type { InterfaceTheme, ResolvedInterfaceTheme, InterfaceLanguage } from '@/lib/interfacePreferences';

// React uses the server snapshot through hydration, then exposes browser choices.
const subscribeHydration = () => () => {};
const getClientHydrationSnapshot = () => true;
const getServerHydrationSnapshot = () => false;

export type TranslationKey =
  | 'citationSources'
  | 'citationSourceFallback'
  | 'citationShowSources'
  | 'citationHideSources'
  | 'citationDetails'
  | 'citationOpenSource'
  | 'citationSourceUrl'
  | 'citationIdentifier'
  | 'citationExcerptNote'
  | 'appearance'
  | 'theme.light'
  | 'theme.dark'
  | 'theme.system'
  | 'language'
  | 'language.zhTW'
  | 'language.zhCN'
  | 'language.en'
  | 'browseMemory'
  | 'browseNotes'
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
  | 'messageAttachments'
  | 'attachmentListLabel'
  | 'attachmentItemLabel'
  | 'pdfAttachmentSource'
  | 'uploadedAttachmentBadge'
  | 'responseStoppedByUser'
  | 'attachmentOpenPreview'
  | 'attachmentDownload'
  | 'attachmentClosePreview'
  | 'attachmentOriginalUnavailable'
  | 'pdfPageAttribution'
  | 'messageInputRow'
  | 'addAttachment'
  | 'messageTextarea'
  | 'stopGenerating'
  | 'sendMessage'
  | 'chooseAttachment'
  | 'latexPreview'
  | 'formulaPreview'
  | 'newChat'
  | 'longConversationTitle'
  | 'longConversationDescription'
  | 'longConversationBranchDescription'
  | 'longConversationContinue'
  | 'mailbox'
  | 'noConversations'
  | 'today'
  | 'yesterday'
  | 'previousSevenDays'
  | 'older'
  | 'pinned'
  | 'conversationHome'
  | 'conversationSearch'
  | 'conversationSearchPlaceholder'
  | 'conversationSearchEmpty'
  | 'conversationRecents'
  | 'noPinnedConversations'
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
  | 'resizeSidebar'
  | 'tableActions'
  | 'copyTable'
  | 'downloadTableCsv'
  | 'expandTable'
  | 'scrollableTable'
  | 'table'
  | 'closeExpandedTable'
  | 'copyFormula'
  | 'copyFormulaSuccess'
  | 'copyFormulaFailed'
  | 'feedbackThanks'
  | 'feedbackIncorrect'
  | 'feedbackNotWanted'
  | 'feedbackSlow'
  | 'feedbackStyle'
  | 'feedbackSafety'
  | 'feedbackOther'
  | 'copyMessage'
  | 'readAloud'
  | 'stopReadAloud'
  | 'readAloudStarted'
  | 'readAloudFailed'
  | 'addToNotes'
  | 'savedToNotes'
  | 'addedToNotes'
  | 'addNoteFailed'
  | 'notesTitle'
  | 'notesSearchPlaceholder'
  | 'notesEmpty'
  | 'notesUntitledConversation'
  | 'openSourceConversation'
  | 'notesOpenSourceFailed'
  | 'notesAllSources'
  | 'notesAllTags'
  | 'notesPinnedGroup'
  | 'notesAddTagPlaceholder'
  | 'notesExpand'
  | 'notesCollapse'
  | 'notesPin'
  | 'notesUnpin'
  | 'notesTagLabel'
  | 'notesUpdateFailed'
  | 'deleteNoteConfirm'
  | 'noteDeleted'
  | 'noteDeleteFailed'
  | 'expandImage'
  | 'editMessage'
  | 'helpfulReply'
  | 'notHelpfulReply'
  | 'regenerate'
  | 'regenerateMessage'
  | 'deleteLatestConversationTurn'
  | 'createConversationBranch'
  | 'moreReplyActions'
  | 'conversationBranches'
  | 'conversationBranchTitle'
  | 'conversationBranchFrom'
  | 'conversationBranchTo'
  | 'conversationBranchReturn'
  | 'conversationBranchFailed'
  | 'deleteLatestConversationTurnSuccess'
  | 'deleteLatestConversationTurnFailed'
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
  | 'downloadConversation'
  | 'shareLoginRequired'
  | 'shareNoConversation'
  | 'shareLinkCopied'
  | 'composerLineCount'
  | 'composerLowRes'
  | 'composerActiveModes'
  | 'onboardingFeaturesTitle'
  | 'onboardingFeaturesBody'
  | 'onboardingFeaturesStart'
  | 'onboardingFeaturesOfferTitle'
  | 'onboardingFeaturesOfferBody'
  | 'onboardingFeaturesOfferAccept'
  | 'onboardingFeaturesOfferDismiss'
  | 'onboardingWelcomeTitle'
  | 'onboardingPitch'
  | 'onboardingStart'
  | 'onboardingSkip'
  | 'onboardingNext'
  | 'onboardingGotIt'
  | 'onboardingDone'
  | 'onboardingAskTitle'
  | 'onboardingAskBody'
  | 'onboardingExample1'
  | 'onboardingExample2'
  | 'onboardingExample3'
  | 'onboardingNoteTitle'
  | 'onboardingNoteBody'
  | 'onboardingBranchTitle'
  | 'onboardingBranchBody'
  | 'onboardingPlusTitle'
  | 'onboardingPlusBody'
  | 'onboardingFinishTitle'
  | 'onboardingFinishBody'
  | 'onboardingReplay'
  | 'shareDialogTitle'
  | 'shareDialogClose'
  | 'shareSnapshotNotice'
  | 'shareWhoHasAccess'
  | 'shareAnyoneWithLink'
  | 'shareAnyoneWithLinkHint'
  | 'shareYou'
  | 'shareOwnerRole'
  | 'shareCopyLink'
  | 'shareLinkAccessNote'
  | 'shareReadOnlyOwnerNotice'
  | 'shareOpenOriginal'
  | 'shareUnavailable'
  | 'shareLinkCreated'
  | 'shareLinkFailed'
  | 'historySyncPending'
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
  | 'progress.uploading'
  | 'progress.readingAttachments'
  | 'progress.readingAttachmentsCount'
  | 'progress.analyzing'
  | 'progress.recallingMemory'
  | 'progress.planning'
  | 'progress.webSearch'
  | 'progress.visualPlanning'
  | 'progress.visualUnderstanding'
  | 'progress.readingDocuments'
  | 'progress.readingDocumentsCount'
  | 'progress.composing'
  | 'progress.elapsed'
  | 'progress.showSteps'
  | 'progress.hideSteps'
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
  initialPreferences?: InterfacePreferences;
}

const SYSTEM_DARK_MEDIA_QUERY = '(prefers-color-scheme: dark)';

const defaultPreferences: UserPreferencesContextValue = {
  theme: 'system',
  resolvedTheme: 'dark',
  language: 'en',
  setTheme: () => undefined,
  setLanguage: () => undefined,
  t: (key, params) => translate('en', key, params),
};

const TRANSLATIONS: Record<InterfaceLanguage, Record<TranslationKey, string>> = {
  'zh-TW': {
    citationSources: '文獻來源',
    citationSourceFallback: '文獻來源',
    citationShowSources: '顯示 {count} 個文獻來源',
    citationHideSources: '隱藏 {count} 個文獻來源',
    citationDetails: '文獻原文詳情',
    citationOpenSource: '在新分頁開啟原文',
    citationSourceUrl: '來源: {url}',
    citationIdentifier: '識別碼: {id}',
    citationExcerptNote: '* 以上內容為 RAG 檢索之原文片段',
    appearance: '介面外觀',
    'theme.light': '明亮',
    'theme.dark': '深色',
    'theme.system': '系統',
    language: '語言',
    'language.zhTW': '繁體中文',
    'language.zhCN': '簡體中文',
    'language.en': 'English',
    browseMemory: '瀏覽記憶',
    browseNotes: '瀏覽筆記',
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
    attachmentTooLarge: '單一附件不得超過 40 MB。',
    attachmentsTooLarge: '附件總大小不得超過 40 MB。',
    dropFilesTitle: '放開即可附加檔案',
    dropFilesSubtitle: '支援圖片、PDF、TXT 與 Markdown',
    attachmentImagePreview: '圖片附件預覽',
    cancelQuote: '取消引用',
    pendingAttachments: '待送附件',
    messageAttachments: '{count} 個附件',
    attachmentListLabel: '附件清單',
    attachmentItemLabel: '附件 {name}',
    pdfAttachmentSource: '上傳 PDF',
    uploadedAttachmentBadge: '上傳附件',
    responseStoppedByUser: "你停止了 AREQA 的回應",
    attachmentOpenPreview: '預覽 {name}',
    attachmentDownload: '下載',
    attachmentClosePreview: '關閉預覽',
    attachmentOriginalUnavailable: '這裡只保留預覽縮圖，無法下載原始檔案。',
    pdfPageAttribution: '{filename}，第 {page} 頁',
    messageInputRow: '訊息輸入列',
    addAttachment: '加入圖片或文件',
    messageTextarea: '訊息輸入框',
    stopGenerating: '停止生成',
    sendMessage: '發送訊息',
    chooseAttachment: '選擇附件',
    latexPreview: 'LaTeX 預覽',
    formulaPreview: '公式預覽',
    newChat: '新對話',
    longConversationTitle: '這段對話已經很長',
    longConversationDescription: 'AI 已回覆 {count} 則。你可以開啟新對話，原對話仍會保留。',
    longConversationBranchDescription: 'AI 已回覆 {count} 則。你可以從先前某則回覆的「⋯」選單建立分支，沿用到那則回覆為止的內容，或開啟新對話。原對話仍會保留。',
    longConversationContinue: '繼續目前對話',
    mailbox: '信箱',
    noConversations: '尚無對話紀錄',
    today: '今天',
    yesterday: '昨天',
    previousSevenDays: '過去七天',
    older: '更早以前',
    pinned: '釘選',
    conversationHome: 'AREQA 首頁（新增對話）',
    conversationSearch: '搜尋對話',
    conversationSearchPlaceholder: '搜尋標題或對話摘要',
    conversationSearchEmpty: '找不到符合的對話',
    conversationRecents: '最近',
    noPinnedConversations: '尚無置頂對話',
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
    resizeSidebar: '調整側邊欄寬度',
    tableActions: '表格操作',
    copyTable: '複製表格',
    downloadTableCsv: '下載表格為CSV',
    expandTable: '擴大顯示表格',
    scrollableTable: '可水平捲動的資料表',
    table: '表格',
    closeExpandedTable: '關閉放大表格',
    copyFormula: '複製公式',
    copyFormulaSuccess: '已複製公式到剪貼簿',
    copyFormulaFailed: '複製公式失敗',
    feedbackThanks: '感謝你的回饋',
    feedbackIncorrect: '不正確或不完整',
    feedbackNotWanted: '這不是我想要的',
    feedbackSlow: '緩慢或故障',
    feedbackStyle: '風格或語調',
    feedbackSafety: '安全性或法律疑慮',
    feedbackOther: '其他',
    copyMessage: '複製訊息',
    readAloud: '朗讀回覆',
    stopReadAloud: '停止朗讀',
    readAloudStarted: '正在朗讀。此聲音為 AI 生成。',
    readAloudFailed: '朗讀失敗，請稍後再試',
    addToNotes: '加入筆記',
    savedToNotes: '已在筆記中',
    addedToNotes: '已加入筆記',
    addNoteFailed: '加入筆記失敗，請稍後再試',
    notesTitle: '筆記',
    notesSearchPlaceholder: '搜尋筆記',
    notesEmpty: '目前還沒有筆記',
    notesUntitledConversation: '未命名對話',
    openSourceConversation: '開啟來源位置',
    notesOpenSourceFailed: '無法開啟來源位置',
    notesAllSources: '所有來源',
    notesAllTags: '所有標籤',
    notesPinnedGroup: '釘選筆記',
    notesAddTagPlaceholder: '新增標籤',
    notesExpand: '展開',
    notesCollapse: '收合',
    notesPin: '釘選筆記',
    notesUnpin: '取消釘選',
    notesTagLabel: '標籤',
    notesUpdateFailed: '更新筆記失敗，請稍後再試',
    deleteNoteConfirm: '確定要刪除此筆記嗎？',
    noteDeleted: '已刪除筆記',
    noteDeleteFailed: '刪除筆記失敗',
    expandImage: '放大檢視圖片：{caption}',
    editMessage: '編輯訊息',
    helpfulReply: '這則回覆有幫助',
    notHelpfulReply: '這則回覆沒有幫助',
    regenerate: '重新生成',
    regenerateMessage: '重新生成訊息',
    deleteLatestConversationTurn: '刪除對話',
    createConversationBranch: '建立新對話分支',
    moreReplyActions: '更多回覆操作',
    conversationBranches: '對話分支',
    conversationBranchTitle: '分支',
    conversationBranchFrom: '從',
    conversationBranchTo: '到分支',
    conversationBranchReturn: '返回來源',
    conversationBranchFailed: '無法建立對話分支，請再試一次。',
    deleteLatestConversationTurnSuccess: '已刪除這輪對話',
    deleteLatestConversationTurnFailed: '刪除對話失敗，請稍後再試',
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
    downloadConversation: '下載對話',
    shareLoginRequired: '請先登入後再分享對話。',
    shareNoConversation: '目前沒有可分享的對話。',
    shareLinkCopied: '已公開並複製分享連結',
    composerLineCount: "{count} 行",
    composerLowRes: "解析度低",
    composerActiveModes: "已啟用的模式",
    onboardingFeaturesTitle: "你可能還沒用過這些功能",
    onboardingFeaturesBody: "花 30 秒認識 {count} 個能讓學習更順手的功能，隨時可以略過。",
    onboardingFeaturesStart: "看看",
    onboardingFeaturesOfferTitle: "AREQA 有幾個你可能還沒用過的功能",
    onboardingFeaturesOfferBody: "例如把重點存進筆記、從某個回答另開對話分支，或上傳 PDF 提問。",
    onboardingFeaturesOfferAccept: "看看（約 30 秒）",
    onboardingFeaturesOfferDismiss: "不用了",
    onboardingWelcomeTitle: "歡迎來到 AREQA：懂你所學，伴你所讀",
    onboardingPitch: "我可以把學習材料和觀念講解易懂清楚，再陪你延伸發想思考的學習夥伴！您需要導覽嗎？",
    onboardingStart: "開始（約 1 分鐘）",
    onboardingSkip: "略過引導",
    onboardingNext: "下一步",
    onboardingGotIt: "知道了",
    onboardingDone: "完成",
    onboardingAskTitle: "你可以先問一個學習上的問題",
    onboardingAskBody: "在下方輸入你最近在學、還不太懂的東西，或直接點一個範例。AREQA 回答完後會繼續帶你認識其他功能。",
    onboardingExample1: "什麼是梯度下降？",
    onboardingExample2: "用白話解釋貝氏定理",
    onboardingExample3: "中國文學史精簡說明？",
    onboardingNoteTitle: "把重點存進筆記",
    onboardingNoteBody: "覺得這段回答很好？按這裡就能存進筆記，在側欄的「筆記」區域裡查看。",
    onboardingBranchTitle: "對話滿了嗎？或是想開新對話？",
    onboardingBranchBody: "回答旁的「⋯」選單可以「建立新對話分支」：從這一點另開一段對話，保持上下文的同時，繼續對話。",
    onboardingPlusTitle: "更多工具都在「＋」裡",
    onboardingPlusBody: "按「＋」可以上傳 PDF 或圖片一起提問，也能「產生圖片」，例如把一個概念畫成圖解。",
    onboardingFinishTitle: "準備好了！",
    onboardingFinishBody: "你還可以用麥克風跟 AREQA 語音對話、把對話分享給別人，或在帳號選單裡查看筆記與 AREQA 對你的記憶。想再看一次這個導覽，到帳號選單點「觀看功能導覽」。",
    onboardingReplay: "觀看功能導覽",
    shareDialogTitle: "分享對話",
    shareDialogClose: "關閉",
    shareSnapshotNotice: "只會分享到目前為止的訊息",
    shareWhoHasAccess: "誰可以存取",
    shareAnyoneWithLink: "擁有連結的任何人",
    shareAnyoneWithLinkHint: "可以唯讀檢視這段對話",
    shareYou: "(你)",
    shareOwnerRole: "擁有者",
    shareCopyLink: "複製連結",
    shareLinkAccessNote: "擁有連結的人都能開啟，但無法修改這段對話。",
    shareReadOnlyOwnerNotice: "這是你分享的對話的唯讀副本。",
    shareOpenOriginal: "開啟原始對話",
    shareUnavailable: "這個分享連結無法開啟，或已停止分享。",
    shareLinkCreated: '分享連結已建立：',
    shareLinkFailed: 'Failed to create share link. Please try again later.',
    historySyncPending: '部分訊息尚未備份至雲端。請保留此瀏覽器資料，連線恢復後將自動重試。',
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
    'progress.uploading': '正在上傳並讀取附件',
    'progress.readingAttachments': '正在讀取附件',
    'progress.readingAttachmentsCount': '正在讀取 {count} 份附件',
    'progress.analyzing': '正在分析問題',
    'progress.recallingMemory': '正在回顧你的學習紀錄',
    'progress.planning': '正在規劃教學策略',
    'progress.webSearch': '正在搜尋網路資料',
    'progress.visualPlanning': '正在挑選附件中的關鍵圖表',
    'progress.visualUnderstanding': '正在分析圖表內容',
    'progress.readingDocuments': '正在閱讀附件並撰寫回答',
    'progress.readingDocumentsCount': '正在閱讀 {count} 份附件並撰寫回答',
    'progress.composing': '正在撰寫回答',
    'progress.elapsed': '{seconds} 秒',
    'progress.showSteps': '顯示處理步驟',
    'progress.hideSteps': '隱藏處理步驟',
    retry: '重試',
  },
  'zh-CN': {
    citationSources: '文献来源',
    citationSourceFallback: '文献来源',
    citationShowSources: '显示 {count} 个文献来源',
    citationHideSources: '隐藏 {count} 个文献来源',
    citationDetails: '文献原文详情',
    citationOpenSource: '在新分页打开原文',
    citationSourceUrl: '来源: {url}',
    citationIdentifier: '标识符: {id}',
    citationExcerptNote: '* 以上内容为 RAG 检索的原文片段',
    appearance: '界面外观',
    'theme.light': '明亮',
    'theme.dark': '深色',
    'theme.system': '系统',
    language: '语言',
    'language.zhTW': '繁体中文',
    'language.zhCN': '简体中文',
    'language.en': 'English',
    browseMemory: '浏览记忆',
    browseNotes: '浏览笔记',
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
    attachmentTooLarge: '单一附件不得超过 40 MB。',
    attachmentsTooLarge: '附件总大小不得超过 40 MB。',
    dropFilesTitle: '放开即可附加文件',
    dropFilesSubtitle: '支持图片、PDF、TXT 与 Markdown',
    attachmentImagePreview: '图片附件预览',
    cancelQuote: '取消引用',
    pendingAttachments: '待送附件',
    messageAttachments: '{count} 个附件',
    attachmentListLabel: '附件清单',
    attachmentItemLabel: '附件 {name}',
    pdfAttachmentSource: '上传 PDF',
    uploadedAttachmentBadge: '上传附件',
    responseStoppedByUser: "你停止了 AREQA 的回应",
    attachmentOpenPreview: '预览 {name}',
    attachmentDownload: '下载',
    attachmentClosePreview: '关闭预览',
    attachmentOriginalUnavailable: '这里只保留预览缩略图，无法下载原始文件。',
    pdfPageAttribution: '{filename}，第 {page} 页',
    messageInputRow: '讯息输入列',
    addAttachment: '加入图片或文件',
    messageTextarea: '讯息输入框',
    stopGenerating: '停止生成',
    sendMessage: '发送讯息',
    chooseAttachment: '选择附件',
    latexPreview: 'LaTeX 预览',
    formulaPreview: '公式预览',
    newChat: '新对话',
    longConversationTitle: '这段对话已经很长',
    longConversationDescription: 'AI 已回复 {count} 条。你可以开启新对话，原对话仍会保留。',
    longConversationBranchDescription: 'AI 已回复 {count} 条。你可以从之前某条回复的「⋯」菜单创建分支，沿用到那条回复为止的内容，或开启新对话。原对话仍会保留。',
    longConversationContinue: '继续当前对话',
    mailbox: '信箱',
    noConversations: '尚无对话纪录',
    today: '今天',
    yesterday: '昨天',
    previousSevenDays: '过去七天',
    older: '更早以前',
    pinned: '置顶',
    conversationHome: 'AREQA 主页（新对话）',
    conversationSearch: '搜索对话',
    conversationSearchPlaceholder: '搜索标题或对话摘要',
    conversationSearchEmpty: '找不到匹配的对话',
    conversationRecents: '最近',
    noPinnedConversations: '暂无置顶对话',
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
    resizeSidebar: '调整侧边栏宽度',
    tableActions: '表格操作',
    copyTable: '复制表格',
    downloadTableCsv: '下载表格为CSV',
    expandTable: '放大显示表格',
    scrollableTable: '可水平滚动的数据表',
    table: '表格',
    closeExpandedTable: '关闭放大表格',
    copyFormula: '复制公式',
    copyFormulaSuccess: '已复制公式到剪贴簿',
    copyFormulaFailed: '复制公式失败',
    feedbackThanks: '感谢你的反馈',
    feedbackIncorrect: '不正确或不完整',
    feedbackNotWanted: '这不是我想要的',
    feedbackSlow: '缓慢或故障',
    feedbackStyle: '风格或语调',
    feedbackSafety: '安全性或法律疑虑',
    feedbackOther: '其他',
    copyMessage: '复制讯息',
    readAloud: '朗读回复',
    stopReadAloud: '停止朗读',
    readAloudStarted: '正在朗读。此声音为 AI 生成。',
    readAloudFailed: '朗读失败，请稍后再试',
    addToNotes: '加入笔记',
    savedToNotes: '已在笔记中',
    addedToNotes: '已加入笔记',
    addNoteFailed: '加入笔记失败，请稍后再试',
    notesTitle: '笔记',
    notesSearchPlaceholder: '搜索笔记',
    notesEmpty: '目前还没有笔记',
    notesUntitledConversation: '未命名对话',
    openSourceConversation: '打开来源位置',
    notesOpenSourceFailed: '无法打开来源位置',
    notesAllSources: '所有来源',
    notesAllTags: '所有标签',
    notesPinnedGroup: '置顶笔记',
    notesAddTagPlaceholder: '新增标签',
    notesExpand: '展开',
    notesCollapse: '收合',
    notesPin: '置顶笔记',
    notesUnpin: '取消置顶',
    notesTagLabel: '标签',
    notesUpdateFailed: '更新笔记失败，请稍后再试',
    deleteNoteConfirm: '确定要删除此笔记吗？',
    noteDeleted: '已删除笔记',
    noteDeleteFailed: '删除笔记失败',
    expandImage: '放大查看图片：{caption}',
    editMessage: '编辑讯息',
    helpfulReply: '这则回复有帮助',
    notHelpfulReply: '这则回复没有帮助',
    regenerate: '重新生成',
    regenerateMessage: '重新生成讯息',
    deleteLatestConversationTurn: '删除对话',
    createConversationBranch: '建立新对话分支',
    conversationBranches: '对话分支',
    moreReplyActions: '更多回复操作',
    conversationBranchTitle: '分支',
    conversationBranchFrom: '从',
    conversationBranchTo: '到分支',
    conversationBranchReturn: '返回来源',
    conversationBranchFailed: '无法建立对话分支，请重试。',
    deleteLatestConversationTurnSuccess: '已删除这轮对话',
    deleteLatestConversationTurnFailed: '删除对话失败，请稍后再试',
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
    downloadConversation: '下载对话',
    shareLoginRequired: '请先登入后再分享对话。',
    shareNoConversation: '目前没有可分享的对话。',
    shareLinkCopied: '已公开并复制分享链接',
    composerLineCount: "{count} 行",
    composerLowRes: "分辨率低",
    composerActiveModes: "已启用的模式",
    onboardingFeaturesTitle: "你可能还没用过这些功能",
    onboardingFeaturesBody: "花 30 秒认识 {count} 个能让学习更顺手的功能，随时可以跳过。",
    onboardingFeaturesStart: "看看",
    onboardingFeaturesOfferTitle: "AREQA 有几个你可能还没用过的功能",
    onboardingFeaturesOfferBody: "例如把重点存进笔记、从某个回答另开对话分支，或上传 PDF 提问。",
    onboardingFeaturesOfferAccept: "看看（约 30 秒）",
    onboardingFeaturesOfferDismiss: "不用了",
    onboardingWelcomeTitle: "欢迎来到 AREQA：懂你所学，伴你所读",
    onboardingPitch: "我可以把学习材料和观念讲解得易懂清楚，再陪你延伸发想思考的学习伙伴！你需要导览吗？",
    onboardingStart: "开始（约 1 分钟）",
    onboardingSkip: "跳过引导",
    onboardingNext: "下一步",
    onboardingGotIt: "知道了",
    onboardingDone: "完成",
    onboardingAskTitle: "你可以先问一个学习上的问题",
    onboardingAskBody: "在下方输入你最近在学、还不太懂的东西，或直接点一个示例。AREQA 回答完后会继续带你认识其他功能。",
    onboardingExample1: "什么是梯度下降？",
    onboardingExample2: "用白话解释贝叶斯定理",
    onboardingExample3: "中国文学史精简说明？",
    onboardingNoteTitle: "把重点存进笔记",
    onboardingNoteBody: "觉得这段回答很好？按这里就能存进笔记，在侧栏的「笔记」区域里查看。",
    onboardingBranchTitle: "对话满了吗？或是想开新对话？",
    onboardingBranchBody: "回答旁的「⋯」菜单可以「建立新对话分支」：从这一点另开一段对话，保持上下文的同时，继续对话。",
    onboardingPlusTitle: "更多工具都在「＋」里",
    onboardingPlusBody: "按「＋」可以上传 PDF 或图片一起提问，也能「生成图片」，例如把一个概念画成图解。",
    onboardingFinishTitle: "准备好了！",
    onboardingFinishBody: "你还可以用麦克风跟 AREQA 语音对话、把对话分享给别人，或在账号菜单里查看笔记与 AREQA 对你的记忆。想再看一次这个导览，到账号菜单点「观看功能导览」。",
    onboardingReplay: "观看功能导览",
    shareDialogTitle: "分享对话",
    shareDialogClose: "关闭",
    shareSnapshotNotice: "只会分享到目前为止的消息",
    shareWhoHasAccess: "谁可以访问",
    shareAnyoneWithLink: "拥有链接的任何人",
    shareAnyoneWithLinkHint: "可以只读查看这段对话",
    shareYou: "(你)",
    shareOwnerRole: "所有者",
    shareCopyLink: "复制链接",
    shareLinkAccessNote: "拥有链接的人都能打开，但无法修改这段对话。",
    shareReadOnlyOwnerNotice: "这是你分享的对话的只读副本。",
    shareOpenOriginal: "打开原始对话",
    shareUnavailable: "这个分享链接无法打开，或已停止分享。",
    shareLinkCreated: '分享链接已建立：',
    shareLinkFailed: 'Failed to create share link. Please try again later.',
    historySyncPending: '部分消息尚未备份到云端。请保留此浏览器数据，连接恢复后将自动重试。',
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
    'progress.uploading': '正在上传并读取附件',
    'progress.readingAttachments': '正在读取附件',
    'progress.readingAttachmentsCount': '正在读取 {count} 份附件',
    'progress.analyzing': '正在分析问题',
    'progress.recallingMemory': '正在回顾你的学习记录',
    'progress.planning': '正在规划教学策略',
    'progress.webSearch': '正在搜索网络资料',
    'progress.visualPlanning': '正在挑选附件中的关键图表',
    'progress.visualUnderstanding': '正在分析图表内容',
    'progress.readingDocuments': '正在阅读附件并撰写回答',
    'progress.readingDocumentsCount': '正在阅读 {count} 份附件并撰写回答',
    'progress.composing': '正在撰写回答',
    'progress.elapsed': '{seconds} 秒',
    'progress.showSteps': '显示处理步骤',
    'progress.hideSteps': '隐藏处理步骤',
    retry: '重试',
  },
  en: {
    citationSources: 'Sources',
    citationSourceFallback: 'Source',
    citationShowSources: 'Show {count} sources',
    citationHideSources: 'Hide {count} sources',
    citationDetails: 'Source details',
    citationOpenSource: 'Open source in a new tab',
    citationSourceUrl: 'Source: {url}',
    citationIdentifier: 'Identifier: {id}',
    citationExcerptNote: '* This is an original excerpt retrieved by RAG.',
    appearance: 'Appearance',
    'theme.light': 'Light',
    'theme.dark': 'Dark',
    'theme.system': 'System',
    language: 'Language',
    'language.zhTW': 'Traditional Chinese',
    'language.zhCN': 'Simplified Chinese',
    'language.en': 'English',
    browseMemory: 'Memory',
    browseNotes: 'Notes',
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
    attachmentTooLarge: 'Each attachment must be 40 MB or smaller.',
    attachmentsTooLarge: 'Total attachment size must be 40 MB or smaller.',
    dropFilesTitle: 'Drop to attach files',
    dropFilesSubtitle: 'Images, PDF, TXT, and Markdown are supported',
    attachmentImagePreview: 'Image attachment preview',
    cancelQuote: 'Cancel quote',
    pendingAttachments: 'Pending attachments',
    messageAttachments: '{count} attachments',
    attachmentListLabel: 'Attachment list',
    attachmentItemLabel: 'Attachment {name}',
    pdfAttachmentSource: 'Uploaded PDF',
    uploadedAttachmentBadge: 'Uploaded attachment',
    responseStoppedByUser: "You stopped AREQA's response",
    attachmentOpenPreview: 'Preview {name}',
    attachmentDownload: 'Download',
    attachmentClosePreview: 'Close preview',
    attachmentOriginalUnavailable: 'Only a preview thumbnail is kept here; the original file cannot be downloaded.',
    pdfPageAttribution: '{filename}, page {page}',
    messageInputRow: 'Message input row',
    addAttachment: 'Add image or document',
    messageTextarea: 'Message input',
    stopGenerating: 'Stop generating',
    sendMessage: 'Send message',
    chooseAttachment: 'Choose attachment',
    latexPreview: 'LaTeX preview',
    formulaPreview: 'Formula preview',
    newChat: 'New chat',
    longConversationTitle: 'This conversation is getting long',
    longConversationDescription: 'This conversation has {count} AI replies. You can start a new chat. This chat will remain saved.',
    longConversationBranchDescription: 'This conversation has {count} AI replies. Use the ⋯ menu on an earlier reply to branch from that point, or start a new chat. This chat will remain saved.',
    longConversationContinue: 'Continue this chat',
    mailbox: 'Mailbox',
    noConversations: 'No conversations yet',
    today: 'Today',
    yesterday: 'Yesterday',
    previousSevenDays: 'Previous 7 days',
    older: 'Older',
    pinned: 'Pinned',
    conversationHome: 'AREQA home (New chat)',
    conversationSearch: 'Search chats',
    conversationSearchPlaceholder: 'Search titles or previews',
    conversationSearchEmpty: 'No matching chats',
    conversationRecents: 'Recents',
    noPinnedConversations: 'No pinned chats',
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
    resizeSidebar: 'Resize sidebar',
    tableActions: 'Table actions',
    copyTable: 'Copy table',
    downloadTableCsv: 'Download table as CSV',
    expandTable: 'Expand table',
    scrollableTable: 'Horizontally scrollable data table',
    table: 'Table',
    closeExpandedTable: 'Close expanded table',
    copyFormula: 'Copy formula',
    copyFormulaSuccess: 'Formula copied to clipboard',
    copyFormulaFailed: 'Failed to copy formula',
    feedbackThanks: 'Thanks for your feedback',
    feedbackIncorrect: 'Incorrect or incomplete',
    feedbackNotWanted: 'Not what I wanted',
    feedbackSlow: 'Slow or broken',
    feedbackStyle: 'Style or tone',
    feedbackSafety: 'Safety or legal concern',
    feedbackOther: 'Other',
    copyMessage: 'Copy message',
    readAloud: 'Read aloud',
    stopReadAloud: 'Stop reading',
    readAloudStarted: 'Reading aloud. This voice is AI-generated.',
    readAloudFailed: 'Read aloud failed. Please try again later.',
    addToNotes: 'Add to notes',
    savedToNotes: 'Saved to notes',
    addedToNotes: 'Added to notes',
    addNoteFailed: 'Could not add this note. Please try again later.',
    notesTitle: 'Notes',
    notesSearchPlaceholder: 'Search notes',
    notesEmpty: 'No notes yet',
    notesUntitledConversation: 'Untitled conversation',
    openSourceConversation: 'Open source location',
    notesOpenSourceFailed: 'Could not open the source location',
    notesAllSources: 'All sources',
    notesAllTags: 'All tags',
    notesPinnedGroup: 'Pinned notes',
    notesAddTagPlaceholder: 'Add tag',
    notesExpand: 'Expand',
    notesCollapse: 'Collapse',
    notesPin: 'Pin note',
    notesUnpin: 'Unpin note',
    notesTagLabel: 'Tags',
    notesUpdateFailed: 'Could not update this note. Please try again later.',
    deleteNoteConfirm: 'Delete this note?',
    noteDeleted: 'Note deleted',
    noteDeleteFailed: 'Could not delete this note',
    expandImage: 'Open image preview: {caption}',
    editMessage: 'Edit message',
    helpfulReply: 'This reply was helpful',
    notHelpfulReply: 'This reply was not helpful',
    regenerate: 'Regenerate',
    regenerateMessage: 'Regenerate message',
    deleteLatestConversationTurn: 'Delete conversation',
    createConversationBranch: 'Create conversation branch',
    moreReplyActions: 'More reply actions',
    conversationBranches: 'Conversation branches',
    conversationBranchTitle: 'Branch',
    conversationBranchFrom: 'From',
    conversationBranchTo: 'To branch',
    conversationBranchReturn: 'Return to source',
    conversationBranchFailed: 'Could not create the conversation branch. Try again.',
    deleteLatestConversationTurnSuccess: 'Conversation turn deleted',
    deleteLatestConversationTurnFailed: 'Could not delete this conversation turn. Please try again later.',
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
    downloadConversation: 'Download conversation',
    shareLoginRequired: 'Log in before sharing a conversation.',
    shareNoConversation: 'There is no conversation to share yet.',
    shareLinkCopied: 'Public share link copied',
    composerLineCount: "{count} lines",
    composerLowRes: "Low res",
    composerActiveModes: "Active modes",
    onboardingFeaturesTitle: "Features you may not have tried",
    onboardingFeaturesBody: "Take 30 seconds to see {count} features that make studying easier. You can skip anytime.",
    onboardingFeaturesStart: "Show me",
    onboardingFeaturesOfferTitle: "AREQA has a few features you may not have tried",
    onboardingFeaturesOfferBody: "For example saving key points to notes, branching a new conversation from an answer, or asking about an uploaded PDF.",
    onboardingFeaturesOfferAccept: "Show me (30 s)",
    onboardingFeaturesOfferDismiss: "No thanks",
    onboardingWelcomeTitle: "Welcome to AREQA: understands what you learn, reads alongside you",
    onboardingPitch: "I'm a learning partner that makes your study materials and concepts clear and easy to follow, then helps you explore and think further. Would you like a quick tour?",
    onboardingStart: "Start (about 1 min)",
    onboardingSkip: "Skip tour",
    onboardingNext: "Next",
    onboardingGotIt: "Got it",
    onboardingDone: "Done",
    onboardingAskTitle: "Start by asking a learning question",
    onboardingAskBody: "Type something you are learning and do not fully understand yet, or pick an example. After AREQA answers, the tour continues.",
    onboardingExample1: "What is gradient descent?",
    onboardingExample2: "Explain Bayes' theorem in plain words",
    onboardingExample3: "A brief overview of Chinese literary history?",
    onboardingNoteTitle: "Save key points to notes",
    onboardingNoteBody: "Like this answer? Save it here and find it under Notes in the sidebar.",
    onboardingBranchTitle: "Conversation getting full, or want a fresh one?",
    onboardingBranchBody: "The ⋯ menu next to an answer can create a new conversation branch: start a new conversation from this point and keep going with the context carried over.",
    onboardingPlusTitle: "More tools live under +",
    onboardingPlusBody: "Use + to upload a PDF or image to ask about, or to create an image, for example a diagram of a concept.",
    onboardingFinishTitle: "You're ready!",
    onboardingFinishBody: "You can also talk to AREQA by voice, share a conversation, or open your notes and what AREQA remembers about you from the account menu. To see this tour again, choose \"Feature tour\" in the account menu.",
    onboardingReplay: "Feature tour",
    shareDialogTitle: "Share conversation",
    shareDialogClose: "Close",
    shareSnapshotNotice: "Only messages up until now will be shared",
    shareWhoHasAccess: "Who has access",
    shareAnyoneWithLink: "Anyone with the link",
    shareAnyoneWithLinkHint: "Can view this conversation read-only",
    shareYou: "(you)",
    shareOwnerRole: "Owner",
    shareCopyLink: "Copy link",
    shareLinkAccessNote: "Anyone with the link can open it but cannot change the conversation.",
    shareReadOnlyOwnerNotice: "This is the read-only copy that you shared of your chat.",
    shareOpenOriginal: "Open original chat",
    shareUnavailable: "This share link is unavailable or no longer shared.",
    shareLinkCreated: 'Share link created: ',
    shareLinkFailed: 'Failed to create share link. Please try again later.',
    historySyncPending: 'Some messages are not backed up yet. Keep this browser data; sync will retry automatically.',
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
    'progress.uploading': 'Uploading and reading attachments',
    'progress.readingAttachments': 'Reading attachments',
    'progress.readingAttachmentsCount': 'Reading {count} attachments',
    'progress.analyzing': 'Analyzing the question',
    'progress.recallingMemory': 'Reviewing your learning history',
    'progress.planning': 'Planning the teaching approach',
    'progress.webSearch': 'Searching the web',
    'progress.visualPlanning': 'Picking key figures from the attachments',
    'progress.visualUnderstanding': 'Analyzing figures',
    'progress.readingDocuments': 'Reading the attachments and writing',
    'progress.readingDocumentsCount': 'Reading {count} attachments and writing',
    'progress.composing': 'Writing the answer',
    'progress.elapsed': '{seconds}s',
    'progress.showSteps': 'Show steps',
    'progress.hideSteps': 'Hide steps',
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
 *   initialPreferences: Validated server cookie snapshot used throughout hydration.
 *
 * Side effects:
 *   Persists preference changes, listens to system theme changes, and writes
 *   `data-interface-theme`, `data-interface-theme-choice`, and `lang` on the
 *   root document element for CSS and browser language integration.
 */
export function UserPreferencesProvider({
  children,
  initialPreferences = DEFAULT_INTERFACE_PREFERENCES,
}: UserPreferencesProviderProps) {
  const hydrated = useSyncExternalStore(
    subscribeHydration, getClientHydrationSnapshot, getServerHydrationSnapshot,
  );
  const [storedTheme, setThemeState] = useState<InterfaceTheme>(
    () => readBrowserPreferences(initialPreferences).theme,
  );
  const [storedLanguage, setLanguageState] = useState<InterfaceLanguage>(
    () => readBrowserPreferences(initialPreferences).language,
  );
  const [prefersDark, setPrefersDark] = useState(readSystemPrefersDark);
  const theme = hydrated ? storedTheme : initialPreferences.theme;
  const language = hydrated ? storedLanguage : initialPreferences.language;

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
    () => resolveInterfaceTheme(theme, hydrated ? prefersDark : true),
    [hydrated, prefersDark, theme],
  );

  useEffect(() => {
    if (!hydrated || typeof document === 'undefined') return;

    document.documentElement.dataset.interfaceTheme = resolvedTheme;
    document.documentElement.dataset.interfaceThemeChoice = theme;
    document.documentElement.lang = language;
    writePreferenceCookies({ theme, language });
  }, [hydrated, language, resolvedTheme, theme]);

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
