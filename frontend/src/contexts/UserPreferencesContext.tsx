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
  | 'workspaceSwitch'
  | 'workspaceChat'
  | 'workspaceTopicFinder'
  | 'workspaceChatTooltip'
  | 'workspaceTopicFinderTooltip'
  | 'workspaceBeta'
  | 'topicFinderEmptyGreeting'
  | 'topicFinderEmptyPainPrompt'
  | 'topicFinderEmptyMethodPrompt'
  | 'topicFinderPlaceholder'
  | 'topicCardTitle'
  | 'topicCardNextStage'
  | 'topicCardGoToStage'
  | 'topicCardAdopted'
  | 'topicCardStageFailed'
  | 'topicCardDoneSub'
  | 'topicStageTitle1'
  | 'topicStageTitle2'
  | 'topicStageTitle3'
  | 'topicStageTitle4'
  | 'topicStageTitle5'
  | 'topicStageSub1'
  | 'topicStageSub2'
  | 'topicStageSub3'
  | 'topicStageSub4'
  | 'topicStageSub5'
  | 'topicCardSuggestions'
  | 'topicCardKeywords'
  | 'topicCardKeywordCopy'
  | 'topicCardKeywordCopied'
  | 'topicCardGaps'
  | 'topicCardRelated'
  | 'topicCardFeasibility'
  | 'topicFeasTime'
  | 'topicFeasData'
  | 'topicFeasAdvisor'
  | 'topicFeasPriorWork'
  | 'topicFeasEthics'
  | 'topicCardAiProposed'
  | 'topicCardAiProposedHint'
  | 'topicFeasOk'
  | 'topicFeasUnsure'
  | 'topicFeasBlocked'
  | 'topicFeasMissing'
  | 'topicCardStageFilter'
  | 'topicCardStageDone'
  | 'topicCardDraftQuestion'
  | 'topicCardDraftCandidatesQuestion'
  | 'topicCardDraftYes'
  | 'topicCardDraftNo'
  | 'topicCardRejected'
  | 'topicCardCurrentTopic'
  | 'topicCardPainPoint'
  | 'topicCardMotherQuestion'
  | 'topicCardCandidates'
  | 'topicCardProgress'
  | 'topicCardOperationalization'
  | 'topicCardMeasureMissing'
  | 'topicStageMoveButton'
  | 'topicStageMoveMessage'
  | 'topicStageFinishButton'
  | 'topicStageFinishMessage'
  | 'topicCardFocusLabel'
  | 'topicCardFocusSkip'
  | 'topicCardFocusSkipHint'
  | 'topicCardFocusSkipFailed'
  | 'topicCardReviewNote'
  | 'topicCardStageSeparator'
  | 'topicFocusPainPoint'
  | 'topicFocusCandidates'
  | 'topicFocusOwnCandidate'
  | 'topicFocusMotherQuestion'
  | 'topicFocusOperationalization'
  | 'topicFocusMeasure'
  | 'topicFocusFeasibilityMissing'
  | 'topicFocusFeasibilityUnsure'
  | 'topicCardDiscarded'
  | 'topicCardDiscardedBy'
  | 'topicCardCanReturn'
  | 'topicCardObjections'
  | 'topicCardPending'
  | 'topicCardConfirmHint'
  | 'topicCardDone'
  | 'topicCardEmpty'
  | 'topicCardUnavailable'
  | 'topicCardNotSynced'
  | 'topicCardConfirmFailed'
  | 'topicCardStale'
  | 'topicCardVersion'
  | 'topicCardOpen'
  | 'topicCardClose'
  | 'topicCardHistory'
  | 'topicCardExport'
  | 'topicCardExplore'
  | 'topicCardExploreMessage'
  | 'topicCardBranchTitle'
  | 'topicCardBranchFailed'
  | 'topicTourIntroTitle'
  | 'topicTourStart'
  | 'topicTourIntroBody'
  | 'topicTourIntroPoint3'
  | 'topicTourAskTitle'
  | 'topicTourAskBody'
  | 'topicTourExample1'
  | 'topicTourExample2'
  | 'topicTourCardTitle'
  | 'topicTourCardBody'
  | 'topicTourCardPoint1'
  | 'topicTourCardPoint2'
  | 'topicTourCardPoint3'
  | 'topicTourCardPoint4'
  | 'topicTourFinishTitle'
  | 'topicTourFinishBody'
  | 'textSelectionCopy'
  | 'textSelectionAskQuote'
  | 'textSelectionExplain'
  | 'textSelectionExplainPrompt'
  | 'quotedTextDefaultPrompt'
  | 'back'
  | 'askPlaceholder'
  | 'replyPlaceholder'
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
  | 'responseInterruptedByUser'
  | 'requestModeCreateImage'
  | 'requestModeEnglishTutor'
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
  | 'onboardingOpenForMe'
  | 'onboardingBackToChat'
  | 'onboardingNotesEntryTitle'
  | 'onboardingNotesEntryBody'
  | 'onboardingNotesFiltersTitle'
  | 'onboardingNotesFiltersBody'
  | 'onboardingNoteActionsTitle'
  | 'onboardingNoteActionsBody'
  | 'onboardingNoteActionTag'
  | 'onboardingNoteActionEdit'
  | 'onboardingNoteActionPin'
  | 'onboardingNoteActionSource'
  | 'onboardingNoteActionDelete'
  | 'onboardingBranchTry'
  | 'onboardingBranchSidebarTitle'
  | 'onboardingBranchSidebarBody'
  | 'onboardingBranchInsideTitle'
  | 'onboardingBranchInsideAbove'
  | 'onboardingBranchInsideBelow'
  | 'onboardingBranchInsideReturn'
  | 'shareDialogTitle'
  | 'shareDialogClose'
  | 'shareSnapshotNotice'
  | 'shareWhoHasAccess'
  | 'shareAnyoneWithLink'
  | 'shareAnyoneWithLinkHint'
  | 'shareYou'
  | 'shareOwnerRole'
  | 'shareCopyLink'
  | 'shareReadOnlyOwnerNotice'
  | 'shareOpenOriginal'
  | 'shareUnavailable'
  | 'shareLinkCreated'
  | 'shareLinkFailed'
  | 'shareAccessLabel'
  | 'shareAccessView'
  | 'shareAccessViewHint'
  | 'shareAccessEdit'
  | 'shareAccessEditHint'
  | 'shareMembers'
  | 'shareMemberUnnamed'
  | 'shareEditorRole'
  | 'shareMemberRemove'
  | 'shareMemberRemoveFailed'
  | 'collabMemoryNotice'
  | 'collabLoginToJoin'
  | 'collabNoAccess'
  | 'collabBack'
  | 'shareAccessUpdated'
  | 'shareReadOnlyViewerNotice'
  | 'collabJoinFailed'
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
    workspaceSwitch: "工作區",
    workspaceChat: "對話",
    workspaceTopicFinder: "選題",
    workspaceChatTooltip: "一般對話",
    workspaceTopicFinderTooltip: "選題：找出適合你的研究題目",
    workspaceBeta: "測試版",
    topicFinderEmptyGreeting: "一起找出適合你的研究題目 🔭",
    topicFinderEmptyPainPrompt: "你最近卡在什麼問題上？",
    topicFinderPlaceholder: "說說你最近卡住的問題……",
    topicCardTitle: "題目卡",
    topicFinderEmptyMethodPrompt: "從你的痛點出發，我會陪你一個階段一個階段找題目，也可以跳著走。",
    topicCardStageFilter: "第 {n} 階段",
    topicCardNextStage: "下一階段 →",
    topicCardGoToStage: "切換到第 {n} 階段：{title}",
    topicCardAdopted: "已採用，存成新版本。",
    topicCardStageFailed: "切換階段失敗，請稍後再試。",
    topicCardConfirmHint: "要不要採用、何時換階段都由你決定；AI 只負責整理和提出疑問。",
    topicCardDone: "你已走完五個階段",
    topicCardDoneSub: "可以匯出題目卡，或點上方的數字回到任何一個階段。",
    topicCardDiscardedBy: "第 {n} 階段淘汰",
    topicCardConfirmFailed: "儲存失敗，請稍後再試。",
    topicCardStale: "題目卡已有更新，請看過最新內容後再採用一次。",
    topicStageTitle1: "觀察痛點，先發散",
    topicStageTitle2: "有沒有很簡單的解法？",
    topicStageTitle3: "你真正想知道的是什麼？",
    topicStageTitle4: "幫候選題目找「看得見的證據」",
    topicStageTitle5: "做得到嗎？",
    topicStageSub1: "從生活中的痛點或研究的缺口出發，先發想幾個想解決的問題。",
    topicStageSub2: "一個現成工具、現有論文或研究成果，現在就能解決它嗎？想出最偷懶的解法，再說明它夠不夠。",
    topicStageSub3: "拿掉工具和案例，把具體題目往上抽一層，寫出你的「母問題」。",
    topicStageSub4: "題目裡的每一個關鍵詞，必須要能具體解釋，而且，有沒有可能找到證據證明「自己原本的想法其實是錯的」？",
    topicStageSub5: "以你現在的時間、資源、場域和指導教授，做得到嗎？有人做過了嗎？合乎研究倫理嗎？",
    topicCardSuggestions: "AI 建議（參考用，請自己查證）",
    topicCardKeywords: "可以搜尋的關鍵字",
    topicCardKeywordCopy: "複製關鍵字：{keyword}",
    topicCardKeywordCopied: "已複製，可以貼到 Google Scholar 搜尋。",
    topicCardGaps: "可能的研究缺口",
    topicCardRelated: "相關議題",
    topicCardFeasibility: "可行性檢查",
    topicFeasTime: "時間",
    topicFeasData: "資料與場域",
    topicFeasAdvisor: "指導教授與方法",
    topicFeasPriorWork: "有沒有人做過",
    topicFeasEthics: "研究倫理",
    topicCardAiProposed: "AI 提議",
    topicCardAiProposedHint: "這個候選是 AI 列出的；用你自己的話改寫後，就會變成你的想法。",
    topicFeasOk: "可以",
    topicFeasUnsure: "還不確定",
    topicFeasBlocked: "有困難",
    topicFeasMissing: "還沒討論",
    topicTourIntroBody: "這裡不會直接給你題目，而是像指導教授一樣，分 5 個階段陪你找題目，可以跳著走：",
    topicTourIntroPoint3: "AI 只負責整理和提出疑問，要不要採用、何時換階段由你決定。",
    topicTourCardBody: "上方的 1～5 可以直接切換階段，不用照順序。AI 會把對話整理成草稿；你覺得對，就按「採用這份整理」，想往下走再按「下一階段 →」。",
    topicCardStageDone: "完成",
    topicCardDraftQuestion: "AI 幫你整理了以下內容，要更新到下方「目前的題目」嗎？",
    topicCardDraftCandidatesQuestion: "AI 幫你整理了以下候選題目，要列入下方「目前的題目」的候選清單嗎？",
    topicCardDraftYes: "需要",
    topicCardDraftNo: "不需要",
    topicCardRejected: "已略過，題目卡沒有變動。",
    topicCardCurrentTopic: "目前的題目",
    topicCardPainPoint: "你卡住的問題",
    topicCardMotherQuestion: "你真正想知道的（母問題）",
    topicCardCandidates: "候選題目",
    topicCardProgress: "進度",
    topicCardOperationalization: "怎麼證明（每個關鍵詞用什麼證據看）",
    topicCardMeasureMissing: "還沒想好用什麼證據",
    topicStageMoveButton: "前往第 {n} 階段：{title}",
    topicStageMoveMessage: "好，我們進到第 {n} 階段：{title}",
    topicStageFinishButton: "五個階段都談完了：整理最終題目",
    topicStageFinishMessage: "好，五個階段都談完了，幫我整理最終題目",
    topicCardFocusLabel: "這輪先看：",
    topicCardFocusSkip: "換一個",
    topicCardFocusSkipHint: "這不是你現在的重點？先放著，教練會改問別的。卡片上仍會保留提醒。",
    topicCardFocusSkipFailed: "暫時無法更換，請稍後再試。",
    topicCardStageSeparator: "、",
    topicCardReviewNote: "你剛改了題目，教練下一輪會先陪你回頭看第 {stages} 階段還成不成立。",
    topicFocusPainPoint: "用一句話寫下你卡住的問題",
    topicFocusCandidates: "從痛點想出幾個想解決的問題",
    topicFocusOwnCandidate: "用自己的話寫一個候選題目",
    topicFocusMotherQuestion: "拿掉工具和案例，你真正想知道什麼",
    topicFocusOperationalization: "題目裡哪些關鍵詞需要拿證據說明",
    topicFocusMeasure: "「{term}」要用什麼證據看出來",
    topicFocusFeasibilityMissing: "可行性：{term}",
    topicFocusFeasibilityUnsure: "可行性：{term}還缺什麼才能確定",
    topicCardDiscarded: "淘汰的題目",
    topicCardCanReturn: "之後可以再回來",
    topicCardObjections: "我的反問",
    topicCardPending: "AI 整理的草稿（尚未採用）",
    topicCardEmpty: "還沒有確認的內容；採用上面的草稿後，會出現在這裡。",
    topicCardUnavailable: "題目卡暫時無法載入，對話不受影響。",
    topicCardNotSynced: "對話同步完成後即可使用題目卡。",
    topicCardVersion: "版本 v{n}",
    topicCardOpen: "開啟題目卡",
    topicCardClose: "收合題目卡",
    topicCardHistory: "版本紀錄",
    topicCardExport: "匯出 Markdown",
    topicCardExplore: "開分支探索",
    topicCardExploreMessage: "我想在這條分支深入探索這個候選題目：「{topic}」",
    topicCardBranchTitle: "候選",
    topicCardBranchFailed: "目前無法建立分支，請等這一輪回答完成後再試。",
    topicTourIntroTitle: "歡迎來到選題",
    topicTourStart: "開始（約 30 秒）",
    topicTourAskTitle: "先說說你的痛點",
    topicTourAskBody: "在輸入框寫下「我卡在／我好奇＿＿」，或點下面的例子試試。回答完成後，我再帶你看題目卡。",
    topicTourExample1: "我做的教學系統和 ChatGPT 差不多，不知道研究價值在哪",
    topicTourExample2: "我好奇 AI 的回答方式會不會讓學生想得更少",
    topicTourCardTitle: "這是你的題目卡",
    topicTourCardPoint1: "第 1、2 階段會出現「AI 建議」：點關鍵字就能複製，再自己到 Google Scholar 等地方查。選題空間不會自己上網搜尋。",
    topicTourCardPoint2: "AI 列出的候選題目會標「AI 提議」；用你自己的話改寫後，就成了你的題目。",
    topicTourCardPoint3: "第 5 階段有可行性檢查：時間、資料與場域、指導教授與方法、有沒有人做過、研究倫理。",
    topicTourCardPoint4: "不要的題目收在「淘汰的題目」，之後可以再回來；候選可以「開分支探索」；題目卡可以匯出 Markdown。手機上點右上角的「選題」標籤開啟。",
    topicTourFinishTitle: "準備好了",
    topicTourFinishBody: "隨時可以用側欄或首頁頂部的切換鈕回到一般對話；選題對話會分開保存。",
    textSelectionCopy: '複製',
    textSelectionAskQuote: '問AREQA(引用)',
    textSelectionExplain: '幫我解釋',
    textSelectionExplainPrompt: '請幫我解釋這段文字：\n\n{text}',
    quotedTextDefaultPrompt: '請回答這段引用內容。',
    back: '返回',
    askPlaceholder: '問問 AREQA',
    replyPlaceholder: '回覆',
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
    responseInterruptedByUser: "你打斷了 AREQA 的回應",
    requestModeCreateImage: "Create Image",
    requestModeEnglishTutor: "English Tutor",
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
    onboardingFeaturesTitle: "你可能還沒用過這些功能",
    onboardingFeaturesBody: "花 1 分鐘認識 {count} 個能讓學習更順手的功能，隨時可以略過。",
    onboardingFeaturesStart: "看看",
    onboardingFeaturesOfferTitle: "AREQA 有幾個你可能還沒用過的功能",
    onboardingFeaturesOfferBody: "例如把重點存進筆記、從某個回答另開對話分支，或上傳 PDF 提問。",
    onboardingFeaturesOfferAccept: "看看（約 1 分鐘）",
    onboardingFeaturesOfferDismiss: "不用了",
    onboardingWelcomeTitle: "歡迎來到 AREQA：懂你所學，伴你所讀",
    onboardingPitch: "我可以把學習材料和觀念講解易懂清楚，再陪你延伸發想思考的學習夥伴！您需要導覽嗎？",
    onboardingStart: "開始（約 2 分鐘）",
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
    onboardingFinishBody: "你還可以用麥克風跟 AREQA 語音對話、把對話分享給別人，或在帳號選單裡查看筆記與 AREQA 對你的記憶。想找研究題目，可以切到首頁頂部的「選題（測試版）」。想再看一次這個導覽，到帳號選單點「觀看功能導覽」。",
    onboardingReplay: "觀看功能導覽",
    onboardingOpenForMe: "幫我打開",
    onboardingBackToChat: "回到對話",
    onboardingNotesEntryTitle: "你的筆記在這裡",
    onboardingNotesEntryBody: "筆記收在左下角的帳號選單：點你的名字，再選「瀏覽筆記」。也可以直接按「幫我打開」。",
    onboardingNotesFiltersTitle: "搜尋和篩選筆記",
    onboardingNotesFiltersBody: "上方輸入關鍵字可以搜尋筆記；這裡可以依「來源」對話或「標籤」篩選，只看某段對話或某個主題的筆記。",
    onboardingNoteActionsTitle: "整理每一則筆記",
    onboardingNoteActionsBody: "每則筆記下方都有這些操作：",
    onboardingNoteActionTag: "在「新增標籤」輸入文字後按 Enter，幫筆記分類，例如「期中考」。",
    onboardingNoteActionEdit: "鉛筆圖示：修改筆記內容，只留下你要的重點。",
    onboardingNoteActionPin: "圖釘圖示：釘選常看的筆記，它會排在最上面。",
    onboardingNoteActionSource: "「開啟來源位置」：跳回當初存這則筆記的那段回答。",
    onboardingNoteActionDelete: "「刪除」：移除不需要的筆記。",
    onboardingBranchTry: "現在試試看：點「⋯」→「建立新對話分支」。",
    onboardingBranchSidebarTitle: "新分支出現在左邊了",
    onboardingBranchSidebarBody: "左側清單裡，前面有分支圖示的這筆就是剛建立的分支。它複製了到這則回答為止的對話，你在裡面繼續問，原本的對話不會被改動。點它進去看看，或按「幫我打開」。",
    onboardingBranchInsideTitle: "這就是分支對話",
    onboardingBranchInsideAbove: "這條「從 · 原對話名稱」標示以上，是從原對話帶過來的內容，AREQA 會沿用這些上下文回答你。",
    onboardingBranchInsideBelow: "標示以下是分支裡的新對話，你在這裡問什麼，都不會改動原本的對話。",
    onboardingBranchInsideReturn: "點這條標示可以跳回原對話；原對話底部也會出現「到分支」的連結，讓你隨時切回來。左側對話的「⋯」選單也能「返回來源」。",
    shareDialogTitle: "分享對話",
    shareDialogClose: "關閉",
    shareSnapshotNotice: "只會分享到目前為止的訊息",
    shareWhoHasAccess: "誰可以存取",
    shareAnyoneWithLink: "擁有連結的任何人",
    shareAnyoneWithLinkHint: "可以唯讀檢視這段對話",
    shareYou: "(你)",
    shareOwnerRole: "擁有者",
    shareCopyLink: "複製連結",
    shareReadOnlyOwnerNotice: "這是你分享的對話的唯讀副本。",
    shareOpenOriginal: "開啟原始對話",
    shareUnavailable: "這個分享連結無法開啟，或已停止分享。",
    shareLinkCreated: '分享連結已建立：',
    shareLinkFailed: 'Failed to create share link. Please try again later.',
    shareAccessLabel: '連結權限',
    shareAccessView: '僅檢視',
    shareAccessViewHint: '任何人都能唯讀檢視到目前為止的訊息',
    shareAccessEdit: '可參與',
    shareAccessEditHint: '已登入的人可以加入，看到完整對話並向 AI 提問',
    shareMembers: '參與者',
    shareMemberUnnamed: '參與者',
    shareEditorRole: '可參與',
    shareMemberRemove: '移除',
    shareMemberRemoveFailed: '無法移除參與者，請稍後再試。',
    collabMemoryNotice: '共同對話不會使用任何人的個人學習記憶。',
    collabLoginToJoin: '登入後再開啟這個連結，就能加入這段對話。',
    collabNoAccess: '你目前無法存取這段對話。擁有者可能已移除你，或把連結改為僅檢視。',
    collabBack: '回到 AREQA',
    shareAccessUpdated: '已更新連結權限',
    shareReadOnlyViewerNotice: '這是唯讀的分享對話，無法在這裡提問。',
    collabJoinFailed: '無法加入這段共同對話，目前以唯讀方式顯示。',
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
    workspaceSwitch: "工作区",
    workspaceChat: "对话",
    workspaceTopicFinder: "选题",
    workspaceChatTooltip: "一般对话",
    workspaceTopicFinderTooltip: "选题：找出适合你的研究题目",
    workspaceBeta: "测试版",
    topicFinderEmptyGreeting: "一起找出适合你的研究题目 🔭",
    topicFinderEmptyPainPrompt: "你最近卡在什么问题上？",
    topicFinderPlaceholder: "说说你最近卡住的问题……",
    topicCardTitle: "题目卡",
    topicFinderEmptyMethodPrompt: "从你的痛点出发，我会陪你一个阶段一个阶段找题目，也可以跳着走。",
    topicCardStageFilter: "第 {n} 阶段",
    topicCardNextStage: "下一阶段 →",
    topicCardGoToStage: "切换到第 {n} 阶段：{title}",
    topicCardAdopted: "已采用，存成新版本。",
    topicCardStageFailed: "切换阶段失败，请稍后再试。",
    topicCardConfirmHint: "要不要采用、何时换阶段都由你决定；AI 只负责整理和提出疑问。",
    topicCardDone: "你已走完五个阶段",
    topicCardDoneSub: "可以导出题目卡，或点上方的数字回到任何一个阶段。",
    topicCardDiscardedBy: "第 {n} 阶段淘汰",
    topicCardConfirmFailed: "保存失败，请稍后再试。",
    topicCardStale: "题目卡已有更新，请看过最新内容后再采用一次。",
    topicStageTitle1: "观察痛点，先发散",
    topicStageTitle2: "有没有很简单的解法？",
    topicStageTitle3: "你真正想知道的是什么？",
    topicStageTitle4: "帮候选题目找「看得见的证据」",
    topicStageTitle5: "做得到吗？",
    topicStageSub1: "从生活中的痛点或研究的缺口出发，先发想几个想解决的问题。",
    topicStageSub2: "一个现成工具、现有论文或研究成果，现在就能解决它吗？想出最偷懒的解法，再说明它够不够。",
    topicStageSub3: "拿掉工具和案例，把具体题目往上抽一层，写出你的「母问题」。",
    topicStageSub4: "题目里的每一个关键词，必须要能具体解释，而且，有没有可能找到证据证明「自己原本的想法其实是错的」？",
    topicStageSub5: "以你现在的时间、资源、场域和指导教授，做得到吗？有人做过了吗？合乎研究伦理吗？",
    topicCardSuggestions: "AI 建议（参考用，请自己查证）",
    topicCardKeywords: "可以搜索的关键词",
    topicCardKeywordCopy: "复制关键词：{keyword}",
    topicCardKeywordCopied: "已复制，可以粘贴到 Google Scholar 搜索。",
    topicCardGaps: "可能的研究缺口",
    topicCardRelated: "相关议题",
    topicCardFeasibility: "可行性检查",
    topicFeasTime: "时间",
    topicFeasData: "资料与场域",
    topicFeasAdvisor: "指导教授与方法",
    topicFeasPriorWork: "有没有人做过",
    topicFeasEthics: "研究伦理",
    topicCardAiProposed: "AI 提议",
    topicCardAiProposedHint: "这个候选是 AI 列出的；用你自己的话改写后，就会变成你的想法。",
    topicFeasOk: "可以",
    topicFeasUnsure: "还不确定",
    topicFeasBlocked: "有困难",
    topicFeasMissing: "还没讨论",
    topicTourIntroBody: "这里不会直接给你题目，而是像指导教授一样，分 5 个阶段陪你找题目，可以跳着走：",
    topicTourIntroPoint3: "AI 只负责整理和提出疑问，要不要采用、何时换阶段由你决定。",
    topicTourCardBody: "上方的 1～5 可以直接切换阶段，不用照顺序。AI 会把对话整理成草稿；你觉得对，就按「采用这份整理」，想往下走再按「下一阶段 →」。",
    topicCardStageDone: "完成",
    topicCardDraftQuestion: "AI 帮你整理了以下内容，要更新到下方「目前的题目」吗？",
    topicCardDraftCandidatesQuestion: "AI 帮你整理了以下候选题目，要列入下方「目前的题目」的候选清单吗？",
    topicCardDraftYes: "需要",
    topicCardDraftNo: "不需要",
    topicCardRejected: "已略过，题目卡没有变动。",
    topicCardCurrentTopic: "目前的题目",
    topicCardPainPoint: "你卡住的问题",
    topicCardMotherQuestion: "你真正想知道的（母问题）",
    topicCardCandidates: "候选题目",
    topicCardProgress: "进度",
    topicCardOperationalization: "怎么证明（每个关键词用什么证据看）",
    topicCardMeasureMissing: "还没想好用什么证据",
    topicStageMoveButton: "前往第 {n} 阶段：{title}",
    topicStageMoveMessage: "好，我们进到第 {n} 阶段：{title}",
    topicStageFinishButton: "五个阶段都谈完了：整理最终题目",
    topicStageFinishMessage: "好，五个阶段都谈完了，帮我整理最终题目",
    topicCardFocusLabel: "这轮先看：",
    topicCardFocusSkip: "换一个",
    topicCardFocusSkipHint: "这不是你现在的重点？先放着，教练会改问别的。卡片上仍会保留提醒。",
    topicCardFocusSkipFailed: "暂时无法更换，请稍后再试。",
    topicCardStageSeparator: "、",
    topicCardReviewNote: "你刚改了题目，教练下一轮会先陪你回头看第 {stages} 阶段还成不成立。",
    topicFocusPainPoint: "用一句话写下你卡住的问题",
    topicFocusCandidates: "从痛点想出几个想解决的问题",
    topicFocusOwnCandidate: "用自己的话写一个候选题目",
    topicFocusMotherQuestion: "拿掉工具和案例，你真正想知道什么",
    topicFocusOperationalization: "题目里哪些关键词需要拿证据说明",
    topicFocusMeasure: "「{term}」要用什么证据看出来",
    topicFocusFeasibilityMissing: "可行性：{term}",
    topicFocusFeasibilityUnsure: "可行性：{term}还缺什么才能确定",
    topicCardDiscarded: "淘汰的题目",
    topicCardCanReturn: "之后可以再回来",
    topicCardObjections: "我的反问",
    topicCardPending: "AI 整理的草稿（尚未采用）",
    topicCardEmpty: "还没有确认的内容；采用上面的草稿后，会出现在这里。",
    topicCardUnavailable: "题目卡暂时无法加载，对话不受影响。",
    topicCardNotSynced: "对话同步完成后即可使用题目卡。",
    topicCardVersion: "版本 v{n}",
    topicCardOpen: "打开题目卡",
    topicCardClose: "收起题目卡",
    topicCardHistory: "版本记录",
    topicCardExport: "导出 Markdown",
    topicCardExplore: "开分支探索",
    topicCardExploreMessage: "我想在这条分支深入探索这个候选题目：「{topic}」",
    topicCardBranchTitle: "候选",
    topicCardBranchFailed: "目前无法建立分支，请等这一轮回答完成后再试。",
    topicTourIntroTitle: "欢迎来到选题",
    topicTourStart: "开始（约 30 秒）",
    topicTourAskTitle: "先说说你的痛点",
    topicTourAskBody: "在输入框写下「我卡在／我好奇＿＿」，或点下面的例子试试。回答完成后，我再带你看题目卡。",
    topicTourExample1: "我做的教学系统和 ChatGPT 差不多，不知道研究价值在哪",
    topicTourExample2: "我好奇 AI 的回答方式会不会让学生想得更少",
    topicTourCardTitle: "这是你的题目卡",
    topicTourCardPoint1: "第 1、2 阶段会出现「AI 建议」：点关键词就能复制，再自己到 Google Scholar 等地方查。选题空间不会自己上网搜索。",
    topicTourCardPoint2: "AI 列出的候选题目会标「AI 提议」；用你自己的话改写后，就成了你的题目。",
    topicTourCardPoint3: "第 5 阶段有可行性检查：时间、资料与场域、指导教授与方法、有没有人做过、研究伦理。",
    topicTourCardPoint4: "不要的题目收在「淘汰的题目」，之后可以再回来；候选可以「开分支探索」；题目卡可以导出 Markdown。手机上点右上角的「选题」标签打开。",
    topicTourFinishTitle: "准备好了",
    topicTourFinishBody: "随时可以用侧栏或首页顶部的切换按钮回到一般对话；选题对话会分开保存。",
    textSelectionCopy: '复制',
    textSelectionAskQuote: '问AREQA(引用)',
    textSelectionExplain: '帮我解释',
    textSelectionExplainPrompt: '请帮我解释这段文字：\n\n{text}',
    quotedTextDefaultPrompt: '请回答这段引用内容。',
    back: '返回',
    askPlaceholder: '问问 AREQA',
    replyPlaceholder: '回复',
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
    responseInterruptedByUser: "你打断了 AREQA 的回应",
    requestModeCreateImage: "Create Image",
    requestModeEnglishTutor: "English Tutor",
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
    onboardingFeaturesTitle: "你可能还没用过这些功能",
    onboardingFeaturesBody: "花 1 分钟认识 {count} 个能让学习更顺手的功能，随时可以跳过。",
    onboardingFeaturesStart: "看看",
    onboardingFeaturesOfferTitle: "AREQA 有几个你可能还没用过的功能",
    onboardingFeaturesOfferBody: "例如把重点存进笔记、从某个回答另开对话分支，或上传 PDF 提问。",
    onboardingFeaturesOfferAccept: "看看（约 1 分钟）",
    onboardingFeaturesOfferDismiss: "不用了",
    onboardingWelcomeTitle: "欢迎来到 AREQA：懂你所学，伴你所读",
    onboardingPitch: "我可以把学习材料和观念讲解得易懂清楚，再陪你延伸发想思考的学习伙伴！你需要导览吗？",
    onboardingStart: "开始（约 2 分钟）",
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
    onboardingFinishBody: "你还可以用麦克风跟 AREQA 语音对话、把对话分享给别人，或在账号菜单里查看笔记与 AREQA 对你的记忆。想找研究题目，可以切到首页顶部的「选题（测试版）」。想再看一次这个导览，到账号菜单点「观看功能导览」。",
    onboardingReplay: "观看功能导览",
    onboardingOpenForMe: "帮我打开",
    onboardingBackToChat: "回到对话",
    onboardingNotesEntryTitle: "你的笔记在这里",
    onboardingNotesEntryBody: "笔记收在左下角的账号菜单：点你的名字，再选「浏览笔记」。也可以直接按「帮我打开」。",
    onboardingNotesFiltersTitle: "搜索和筛选笔记",
    onboardingNotesFiltersBody: "上方输入关键字可以搜索笔记；这里可以按「来源」对话或「标签」筛选，只看某段对话或某个主题的笔记。",
    onboardingNoteActionsTitle: "整理每一则笔记",
    onboardingNoteActionsBody: "每则笔记下方都有这些操作：",
    onboardingNoteActionTag: "在「新增标签」输入文字后按 Enter，给笔记分类，例如「期中考」。",
    onboardingNoteActionEdit: "铅笔图标：修改笔记内容，只留下你要的重点。",
    onboardingNoteActionPin: "图钉图标：置顶常看的笔记，它会排在最上面。",
    onboardingNoteActionSource: "「打开来源位置」：跳回当初保存这则笔记的那段回答。",
    onboardingNoteActionDelete: "「删除」：移除不需要的笔记。",
    onboardingBranchTry: "现在试试看：点「⋯」→「建立新对话分支」。",
    onboardingBranchSidebarTitle: "新分支出现在左边了",
    onboardingBranchSidebarBody: "左侧列表里，前面有分支图标的这一项就是刚建立的分支。它复制了到这则回答为止的对话，你在里面继续问，原本的对话不会被改动。点它进去看看，或按「帮我打开」。",
    onboardingBranchInsideTitle: "这就是分支对话",
    onboardingBranchInsideAbove: "这条「从 · 原对话名称」标示以上，是从原对话带过来的内容，AREQA 会沿用这些上下文回答你。",
    onboardingBranchInsideBelow: "标示以下是分支里的新对话，你在这里问什么，都不会改动原本的对话。",
    onboardingBranchInsideReturn: "点这条标示可以跳回原对话；原对话底部也会出现「到分支」的链接，让你随时切回来。左侧对话的「⋯」菜单也能「返回来源」。",
    shareDialogTitle: "分享对话",
    shareDialogClose: "关闭",
    shareSnapshotNotice: "只会分享到目前为止的消息",
    shareWhoHasAccess: "谁可以访问",
    shareAnyoneWithLink: "拥有链接的任何人",
    shareAnyoneWithLinkHint: "可以只读查看这段对话",
    shareYou: "(你)",
    shareOwnerRole: "所有者",
    shareCopyLink: "复制链接",
    shareReadOnlyOwnerNotice: "这是你分享的对话的只读副本。",
    shareOpenOriginal: "打开原始对话",
    shareUnavailable: "这个分享链接无法打开，或已停止分享。",
    shareLinkCreated: '分享链接已建立：',
    shareLinkFailed: 'Failed to create share link. Please try again later.',
    shareAccessLabel: '链接权限',
    shareAccessView: '仅查看',
    shareAccessViewHint: '任何人都能只读查看到目前为止的消息',
    shareAccessEdit: '可参与',
    shareAccessEditHint: '已登录的人可以加入，看到完整对话并向 AI 提问',
    shareMembers: '参与者',
    shareMemberUnnamed: '参与者',
    shareEditorRole: '可参与',
    shareMemberRemove: '移除',
    shareMemberRemoveFailed: '无法移除参与者，请稍后再试。',
    collabMemoryNotice: '共同对话不会使用任何人的个人学习记忆。',
    collabLoginToJoin: '登录后再打开这个链接，就能加入这段对话。',
    collabNoAccess: '你目前无法访问这段对话。所有者可能已移除你，或把链接改为仅查看。',
    collabBack: '回到 AREQA',
    shareAccessUpdated: '已更新链接权限',
    shareReadOnlyViewerNotice: '这是只读的分享对话，无法在这里提问。',
    collabJoinFailed: '无法加入这段共同对话，目前以只读方式显示。',
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
    workspaceSwitch: "Workspace",
    workspaceChat: "Chat",
    workspaceTopicFinder: "Topic Finder",
    workspaceChatTooltip: "Ordinary chat",
    workspaceTopicFinderTooltip: "Topic Finder: find a research topic that fits you",
    workspaceBeta: "Beta",
    topicFinderEmptyGreeting: "Let's find a research topic that fits you 🔭",
    topicFinderEmptyPainPrompt: "What have you been stuck on lately?",
    topicFinderPlaceholder: "Describe what you've been stuck on…",
    topicCardTitle: "Topic card",
    topicFinderEmptyMethodPrompt: "Start from your pain point. I'll work through it with you stage by stage, and you can jump around.",
    topicCardStageFilter: "Stage {n}",
    topicCardNextStage: "Next stage →",
    topicCardGoToStage: "Go to stage {n}: {title}",
    topicCardAdopted: "Saved as a new version.",
    topicCardStageFailed: "Could not switch stage. Please try again.",
    topicCardConfirmHint: "You decide what to keep and when to move on; the AI only summarises and raises questions.",
    topicCardDone: "You have been through all five stages",
    topicCardDoneSub: "Export the card, or tap a number above to revisit any stage.",
    topicCardDiscardedBy: "dropped at stage {n}",
    topicCardConfirmFailed: "Could not save. Please try again.",
    topicCardStale: "The card changed. Review the latest version, then try again.",
    topicStageTitle1: "Notice a pain point, then diverge",
    topicStageTitle2: "Is there a simple solution?",
    topicStageTitle3: "What do you really want to know?",
    topicStageTitle4: "Find visible evidence for your candidate topic",
    topicStageTitle5: "Can you do it?",
    topicStageSub1: "Start from a pain point in daily life or a gap in research, and list a few problems you want to solve.",
    topicStageSub2: "Would an existing tool, paper, or research result already solve it? Name the laziest solution and whether it is enough.",
    topicStageSub3: "Remove the tool and the example, step up one level, and write your core question.",
    topicStageSub4: "Every key term in your topic must be explainable in concrete terms. And could you find evidence that your original idea was actually wrong?",
    topicStageSub5: "Can you do it with your time, resources, setting, and advisor? Has someone already done it? Is it ethical?",
    topicCardSuggestions: "AI suggestions (for reference; check them yourself)",
    topicCardKeywords: "Keywords to search",
    topicCardKeywordCopy: "Copy keyword: {keyword}",
    topicCardKeywordCopied: "Copied. Paste it into Google Scholar.",
    topicCardGaps: "Possible research gaps",
    topicCardRelated: "Related issues",
    topicCardFeasibility: "Feasibility check",
    topicFeasTime: "Time",
    topicFeasData: "Data and setting",
    topicFeasAdvisor: "Advisor and method",
    topicFeasPriorWork: "Done before?",
    topicFeasEthics: "Research ethics",
    topicCardAiProposed: "AI-proposed",
    topicCardAiProposedHint: "The AI listed this candidate. Put it in your own words to make it yours.",
    topicFeasOk: "OK",
    topicFeasUnsure: "Not sure yet",
    topicFeasBlocked: "Difficult",
    topicFeasMissing: "Not discussed yet",
    topicTourIntroBody: "Topic Finder does not hand you a topic. Like an advisor, it works with you through five stages, and you can jump around:",
    topicTourIntroPoint3: "The AI only summarises and raises questions; you decide what to keep and when to move on.",
    topicTourCardBody: "Tap 1-5 at the top to switch stages in any order. The AI turns the conversation into a draft; if it is right, press \"Use this summary\", and press \"Next stage →\" when you want to move on.",
    topicCardStageDone: "Done",
    topicCardDraftQuestion: "The AI summarised the following. Add it to \"Your topic so far\" below?",
    topicCardDraftCandidatesQuestion: "The AI summarised these candidate topics. Add them to the candidate list in \"Your topic so far\" below?",
    topicCardDraftYes: "Yes",
    topicCardDraftNo: "No",
    topicCardRejected: "Skipped. Your topic card is unchanged.",
    topicCardCurrentTopic: "Your topic so far",
    topicCardPainPoint: "What you are stuck on",
    topicCardMotherQuestion: "What you really want to know",
    topicCardCandidates: "Candidate topics",
    topicCardProgress: "Progress",
    topicCardOperationalization: "How you will show it (evidence for each key term)",
    topicCardMeasureMissing: "No evidence chosen yet",
    topicStageMoveButton: "Go to stage {n}: {title}",
    topicStageMoveMessage: "OK, let's move to stage {n}: {title}",
    topicStageFinishButton: "All five stages covered: wrap up your topic",
    topicStageFinishMessage: "OK, let's wrap up the five stages",
    topicCardFocusLabel: "Next up: ",
    topicCardFocusSkip: "Something else",
    topicCardFocusSkipHint: "Not your focus right now? Set it aside and the coach will ask about something else. The card keeps the reminder.",
    topicCardFocusSkipFailed: "Could not switch. Please try again.",
    topicCardStageSeparator: ", ",
    topicCardReviewNote: "You just changed your topic. Next, the coach will check with you whether your earlier work in stage {stages} still holds.",
    topicFocusPainPoint: "write what you are stuck on in one sentence",
    topicFocusCandidates: "turn your pain point into a few problems worth solving",
    topicFocusOwnCandidate: "put one candidate topic in your own words",
    topicFocusMotherQuestion: "without the tool and the example, what do you really want to know",
    topicFocusOperationalization: "which key terms in your topic need evidence",
    topicFocusMeasure: "what evidence will show \"{term}\"",
    topicFocusFeasibilityMissing: "feasibility: {term}",
    topicFocusFeasibilityUnsure: "feasibility: what is still missing for {term}",
    topicCardDiscarded: "Set-aside topics",
    topicCardCanReturn: "may return later",
    topicCardObjections: "My objections",
    topicCardPending: "AI draft (not adopted yet)",
    topicCardEmpty: "Nothing confirmed yet. Adopt the draft above to fill this in.",
    topicCardUnavailable: "The topic card is unavailable right now; the chat still works.",
    topicCardNotSynced: "The topic card becomes available once this chat has synced.",
    topicCardVersion: "Version v{n}",
    topicCardOpen: "Open topic card",
    topicCardClose: "Collapse topic card",
    topicCardHistory: "History",
    topicCardExport: "Export Markdown",
    topicCardExplore: "Explore in a branch",
    topicCardExploreMessage: "In this branch I want to explore this candidate topic in depth: \"{topic}\"",
    topicCardBranchTitle: "Candidate",
    topicCardBranchFailed: "Cannot branch right now. Try again after this answer finishes.",
    topicTourIntroTitle: "Welcome to Topic Finder",
    topicTourStart: "Start (about 30 seconds)",
    topicTourAskTitle: "Start with your pain point",
    topicTourAskBody: "Write \"I am stuck on / curious about ___\" in the box, or try an example below. After the answer, I will show you the topic card.",
    topicTourExample1: "My tutor app feels just like ChatGPT. What is worth researching?",
    topicTourExample2: "I wonder whether the way AI answers makes students think less",
    topicTourCardTitle: "This is your topic card",
    topicTourCardPoint1: "Stages 1 and 2 show \"AI suggestions\": tap a keyword to copy it, then search Google Scholar or similar yourself. Topic Finder does not search the web on its own.",
    topicTourCardPoint2: "Candidates the AI listed are tagged \"AI-proposed\"; put one in your own words and it becomes yours.",
    topicTourCardPoint3: "Stage 5 has a feasibility check: time, data and setting, advisor and method, prior work, and research ethics.",
    topicTourCardPoint4: "Dropped topics stay under \"Set-aside topics\" so you can come back; explore a candidate in its own branch; export the card as Markdown. On a phone, tap the Topic Finder badge to open it.",
    topicTourFinishTitle: "You are ready",
    topicTourFinishBody: "Switch back to ordinary chat any time from the sidebar or the switch at the top of the home screen; Topic Finder chats are kept separately.",
    textSelectionCopy: 'Copy',
    textSelectionAskQuote: 'Ask AREQA (quote)',
    textSelectionExplain: 'Explain',
    textSelectionExplainPrompt: 'Please explain this passage:\n\n{text}',
    quotedTextDefaultPrompt: 'Please answer this quoted passage.',
    back: 'Back',
    askPlaceholder: 'Ask AREQA',
    replyPlaceholder: 'Reply',
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
    responseInterruptedByUser: "You interrupted AREQA's response",
    requestModeCreateImage: "Create Image",
    requestModeEnglishTutor: "English Tutor",
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
    onboardingFeaturesTitle: "Features you may not have tried",
    onboardingFeaturesBody: "Take a minute to see {count} features that make studying easier. You can skip anytime.",
    onboardingFeaturesStart: "Show me",
    onboardingFeaturesOfferTitle: "AREQA has a few features you may not have tried",
    onboardingFeaturesOfferBody: "For example saving key points to notes, branching a new conversation from an answer, or asking about an uploaded PDF.",
    onboardingFeaturesOfferAccept: "Show me (1 min)",
    onboardingFeaturesOfferDismiss: "No thanks",
    onboardingWelcomeTitle: "Welcome to AREQA: understands what you learn, reads alongside you",
    onboardingPitch: "I'm a learning partner that makes your study materials and concepts clear and easy to follow, then helps you explore and think further. Would you like a quick tour?",
    onboardingStart: "Start (about 2 min)",
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
    onboardingFinishBody: "You can also talk to AREQA by voice, share a conversation, or open your notes and what AREQA remembers about you from the account menu. To find a research topic, switch to \"Topic Finder (Beta)\" at the top of the home screen. To see this tour again, choose \"Feature tour\" in the account menu.",
    onboardingReplay: "Feature tour",
    onboardingOpenForMe: "Open it for me",
    onboardingBackToChat: "Back to chat",
    onboardingNotesEntryTitle: "Your notes live here",
    onboardingNotesEntryBody: "Notes are in the account menu at the bottom left: click your name, then choose \"Notes\". Or press \"Open it for me\".",
    onboardingNotesFiltersTitle: "Search and filter notes",
    onboardingNotesFiltersBody: "Search notes by keyword above, or filter by source conversation or tag to see only one conversation or topic.",
    onboardingNoteActionsTitle: "Organize each note",
    onboardingNoteActionsBody: "Every note has these actions:",
    onboardingNoteActionTag: "Type in \"Add tag\" and press Enter to label a note, for example \"midterm\".",
    onboardingNoteActionEdit: "Pencil: edit the note so it keeps only what you need.",
    onboardingNoteActionPin: "Pin: keep notes you use often at the top.",
    onboardingNoteActionSource: "\"Open source location\": jump back to the answer the note came from.",
    onboardingNoteActionDelete: "\"Delete\": remove notes you no longer need.",
    onboardingBranchTry: "Try it now: open ⋯ and choose \"Create conversation branch\".",
    onboardingBranchSidebarTitle: "Your new branch is on the left",
    onboardingBranchSidebarBody: "The item with the branch icon in the sidebar is the branch you just created. It copies the conversation up to this answer, and anything you ask there leaves the original untouched. Open it, or press \"Open it for me\".",
    onboardingBranchInsideTitle: "This is a branch conversation",
    onboardingBranchInsideAbove: "Everything above the \"From · original title\" marker was carried over from the original conversation, and AREQA uses it as context.",
    onboardingBranchInsideBelow: "Below the marker is the new branch conversation. Nothing you ask here changes the original.",
    onboardingBranchInsideReturn: "Click the marker to jump back to the original. The original also shows a \"To branch\" link at the bottom, and the ⋯ menu of a sidebar item can \"Return to source\".",
    shareDialogTitle: "Share conversation",
    shareDialogClose: "Close",
    shareSnapshotNotice: "Only messages up until now will be shared",
    shareWhoHasAccess: "Who has access",
    shareAnyoneWithLink: "Anyone with the link",
    shareAnyoneWithLinkHint: "Can view this conversation read-only",
    shareYou: "(you)",
    shareOwnerRole: "Owner",
    shareCopyLink: "Copy link",
    shareReadOnlyOwnerNotice: "This is the read-only copy that you shared of your chat.",
    shareOpenOriginal: "Open original chat",
    shareUnavailable: "This share link is unavailable or no longer shared.",
    shareLinkCreated: 'Share link created: ',
    shareLinkFailed: 'Failed to create share link. Please try again later.',
    shareAccessLabel: 'Link access',
    shareAccessView: 'View only',
    shareAccessViewHint: 'Anyone can view messages up until now',
    shareAccessEdit: 'Can participate',
    shareAccessEditHint: 'Signed-in people can join, see the whole chat and ask the AI',
    shareMembers: 'Participants',
    shareMemberUnnamed: 'Participant',
    shareEditorRole: 'Participant',
    shareMemberRemove: 'Remove',
    shareMemberRemoveFailed: 'Could not remove the participant. Please try again.',
    collabMemoryNotice: 'Shared chats never use anyone\'s personal learning memory.',
    collabLoginToJoin: 'Sign in and open this link again to join the chat.',
    collabNoAccess: 'You cannot open this chat. The owner may have removed you or made the link view-only.',
    collabBack: 'Back to AREQA',
    shareAccessUpdated: 'Link access updated',
    shareReadOnlyViewerNotice: 'This shared chat is read-only; you cannot ask here.',
    collabJoinFailed: 'Could not join this shared chat, so it is shown read-only.',
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
