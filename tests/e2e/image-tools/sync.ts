/** Test-only cloud boundary. IndexedDB repositories and stores remain real. */
export const syncService = {
  pushMessage: async () => true,
  pushConversation: async () => true,
  pullFromCloud: async () => false,
  pullConversationMessages: async () => false,
  deleteConversation: async () => true,
  deleteMessage: async () => true,
};
