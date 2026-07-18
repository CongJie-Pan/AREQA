# AREQA: An Adaptive RAG-based Educational QA System over Closed-domain Knowledge Bases

## 研究主題 (Research Topic)
**AREQA（發音同 Eureka）：基於通用使用者模型與主動式 UX 之自適應教育問答系統設計與實作**  
*(AREQA: Design and Implementation of an Adaptive Educational QA System Driven by General User Models and Proactive UX)*

---

## 一、研究動機 (Motivation)

隨著大型語言模型（LLM）的普及，檢索增強生成（Retrieval-Augmented Generation, RAG）技術已被廣泛應用於封閉領域（Closed-domain）的知識問答系統中，協助使用者精準獲取專業資訊。然而，在「教育與學習」的場景中，現有的 RAG 問答系統仍面臨兩大核心困境：

1. **缺乏長期的個人化認知模型（Amnesic Interaction）：** 
   傳統的問答系統多為「單次回應（Single-turn reactive）」設計，無法跨越對話輪次累積使用者的學習軌跡。當學生在不同章節遇到困難時，系統無法意識到學生的先備知識盲區或學習習慣，導致每次的回答都是「從零開始的標準答案」，缺乏因材施教的溫度。
   
2. **被動的知識檢索，缺乏教學鷹架（Lack of Proactive Scaffolding）：** 
   真正的教育不只是「給予答案」，更需要適時的陪伴與引導。現有系統必須依賴使用者主動提出完美的問題（Prompting）才能發揮作用；當學生面臨高認知負荷、甚至不知道該如何提問時，系統卻只能被動等待。缺乏「主動介入（Proactive Agency）」與「防呆/關懷機制」，使得 AI 淪為單純的搜尋引擎，而非真正的學習伴讀。

本研究命名為 **AREQA**（Adaptive RAG-based Educational QA System），其發音取自英文的 **"Eureka"（我找到了！）**，象徵著學生在學習過程中獲得頓悟的喜悅。同時，"AREQA" 唸起來宛如一位溫雅的女性名字，我們期望透過技術架構的創新，賦予這個系統「如學伴般的溫暖陪伴感」，讓科技在精準檢索之餘，更能主動察覺學生的需求並提供個人化的支持。

---

## 二、研究目的 (Objectives)

本研究旨在設計並實作一個能解決上述困境的自適應教育問答系統（AREQA），具體的研究目的包含以下三項：

1. **建構具備動態記憶提取的持續性通用使用者模型（Persistent GUM）：**
   結合 LLM 與向量檢索技術，設計一套長短期記憶管理機制。系統將能從日常對話中提取使用者的學習狀態、理解痛點與偏好（Proposition），並透過時間衰減（Decay）與意圖過濾（Intent-Aware Retrieval），在 RAG 生成回應時無縫注入使用者的專屬脈絡，避免記憶污染。

2. **開發基於學習者熟練度之自適應輸出策略（Proficiency-Aware Output Calibration）：**
   參考教育心理學的「最近發展區（ZPD）」理論與自適應鷹架（Adaptive Scaffolding）概念，系統將根據使用者的互動軌跡動態評估其熟練度。對於初學者提供詳盡的步驟與解釋；對於熟練者則實施「鷹架消退」，給予精簡提示或挑戰性問題，達到真正的因材施教。

3. **設計低侵入性的主動式學習體驗（Proactive Educational UX）：**
   打破「你問我答」的被動模式，將「乾巴巴的建議」轉化為「預執行草稿（Pre-Executed Drafts）」與「適時關懷」。透過監測使用者的行為特徵（如停頓、重複修改等高認知負荷訊號），在最不干擾工作流的時機點，主動提供認知支持、錯誤預防（防呆機制）或排程提醒，進一步深化 AREQA 作為「專屬學伴」的陪伴感。