  我不建議現在改成 Anam 自己的語音。
  比較適合的是：保留 OpenAI Realtime 當語音/LLM 主體，Anam 只負責虛擬角色畫面。 但實作路線要選清楚，因為你現在其實還不是 LiveKit 架構。

  目前系統狀態

  README 顯示專案是 FastAPI backend + Next.js frontend。實際 realtime 架構是：

  Browser
    -> frontend/src/services/realtime/client.ts
    -> OpenAI Realtime WebRTC 或 WebSocket
    -> backend/app/routes/realtime.py 只負責建立 OpenAI client secret 與 AREQA context

  關鍵證據：

  - backend/app/routes/realtime.py:31 直接呼叫 OpenAI /v1/realtime/client_secrets
  - backend/app/routes/realtime.py:276 session 只開 output_modalities: ["audio"]
  - frontend/src/services/realtime/client.ts:1 註解明確寫它是 browser low-level OpenAI Realtime WebRTC client
  - frontend/src/services/realtime/client.ts:748 前端取得 backend mint 的 OpenAI realtime session
  - frontend/src/components/LiveTutor/LiveTutorPanel.tsx:312 目前只接 onRemoteStream 到 <audio>
  - frontend/package.json:22 沒有 LiveKit SDK
  - backend/requirements.txt:1 沒有 livekit-agents

  所以 Anam 給你的 LiveKit setup prompt 不能直接套，因為它假設你已經有 LiveKit Agents voice agent。

  我建議的方案

  最佳長期方案是：新增 LiveKit Agents 層，保留 OpenAI Realtime voice，讓 Anam LiveKit plugin 接 agent audio output。

  Frontend Next.js
    -> LiveKit room
    -> LiveKit Agent Worker
    -> OpenAI RealtimeModel
    -> AREQA context tool calls 回打 FastAPI
    -> Anam AvatarSession
    -> avatar video/audio track 回到 frontend

  這樣的好處是：

  - OpenAI Realtime 的低延遲語音能力保留
  - AREQA 目前的 tutor prompt、context、記憶邏輯可以搬過去
  - Anam 只當臉，不接管 LLM/STT/TTS
  - 前端可以真正顯示 LiveKit video track，而不是硬把 OpenAI 音訊再轉給 avatar
  - 之後要換 avatar 只改 ANAM_AVATAR_ID

  官方文件也支持這個方向：Anam LiveKit quickstart 說它是把 Anam avatar 加到 LiveKit voice agent，並使用 OpenAI Realtime；LiveKit Anam plugin 文件則說 avatar session 會接進 AgentSession。
  來源：
  https://anam.ai/docs/integrations/livekit/quickstart
  https://docs.livekit.io/agents/models/avatar/plugins/anam/
  https://docs.livekit.io/frontends/build/virtual-avatars/

  不建議用 Anam 自己語音的原因

  如果改成 Anam 自己語音，就會變成 Anam persona 管 STT/LLM/TTS。你現在 AREQA 的重點都在：

  - OpenAI Realtime session config
  - browser-side tool bridge
  - AREQA memory/context endpoint
  - transcript persistence
  - 中英繁簡語音規則
  - interruption / playback state

  這些都已經在現有 OpenAI realtime pipeline 裡。如果換成 Anam 自己語音，等於要重接 persona prompt、tools、memory、transcript、interruptions，短期風險比較高。

  可選的折衷方案

  如果你想先做最快 MVP，不想立刻引入 LiveKit，可以用 Anam JS SDK 的 audio passthrough：

  OpenAI Realtime WebSocket audio delta
    -> decode / resample 成 Anam 要的 PCM16 16kHz mono
    -> Anam createAgentAudioInputStream()
    -> avatar video element

  但這只適合用 NEXT_PUBLIC_LIVE_VOICE_TRANSPORT=websocket，因為 WebSocket path 目前可以拿到 response.audio.delta。WebRTC path 只拿到 remote stream，不好乾淨地把音訊 chunk 餵給 Anam。Anam 官方也說 client-side
  passthrough 比 server-side integration 延遲和複雜度更高。
  來源：
  https://anam.ai/docs/javascript-sdk/examples/custom-tts

  Action Plan

  1. 先做一個決策文件，記錄目前不是 LiveKit，而是 OpenAI Realtime browser-direct 架構。
  2. 新增 LiveKit Agent worker，建議用 Node.js，因為 Anam quickstart 的主範例是 Node，前端也已經是 TS/React。
  3. 安裝後端/agent 需要的套件：@livekit/agents、@livekit/agents-plugin-openai、@livekit/agents-plugin-anam、LiveKit token SDK。
  4. 在 FastAPI 新增 /api/v1/livekit/token，負責用 LIVEKIT_API_KEY / LIVEKIT_API_SECRET 產生 browser room token。
  5. 把目前 backend/app/routes/realtime.py:116 的 realtime instructions 與 backend/app/routes/realtime.py:622 的 context endpoint 保留，LiveKit agent tool call 回打它。
  6. 前端新增 LiveKit client path，讓 LiveTutorPanel 可以從現在的 OpenAI direct mode 切到 LiveKit avatar mode。
  7. LiveTutorPanel 裡把目前 logo orb 替換成 avatar video track；沒有 avatar 時 fallback 到現在的 AREQA icon。
  8. 環境變數加入 LIVEKIT_URL、LIVEKIT_API_KEY、LIVEKIT_API_SECRET、ANAM_API_KEY、ANAM_AVATAR_ID、OPENAI_API_KEY。
  9. 驗證：能進 room、agent 回答、avatar 出 video track、嘴型同步、沒有雙重音訊、關掉 ANAM_AVATAR_ID 仍可 voice-only。

  我的建議排序：先做 LiveKit + OpenAI Realtime + Anam face。不要先切 Anam 自己語音。
  
  ---
  
  
  › 好 那前端你覺得可以如何設計 ?


• 我會把前端設計成「Live Tutor 從語音 orb 升級成 avatar stage」，不要做成另一個頁面，也不要讓它像外掛 widget。它應該仍然是現在 LiveTutorPanel 的延伸。

  建議版面

  目前這裡是 AREQA icon orb：

  frontend/src/components/LiveTutor/LiveTutorPanel.tsx:542

  我會改成：

  ┌────────────────────────────┐
  │        avatar video         │
  │      16:9 或 4:5 crop        │
  │                             │
  │   status / speaking hint     │
  └────────────────────────────┘

  在桌面版，放在聊天畫面右下或輸入區上方的 inline panel。
  在手機版，變成比較高的 top panel，但不要全螢幕，避免擋住聊天內容。

  視覺狀態

  我會保留你現在的狀態邏輯：

  - connecting：顯示 Connecting
  - listening：avatar 靜止 / idle
  - thinking：底部小狀態顯示「思考中」
  - speaking：avatar video 播放，邊框或背景微弱 pulse
  - muted：顯示靜音 icon
  - error：沿用目前 Lost Connection + retry button

  重點是不要加太多說明文字。使用者看到角色、麥克風、掛斷、靜音，就知道怎麼用。

  控制列

  我建議 avatar panel 底部放一排 icon controls：

  [mic on/off] [interrupt/stop speaking] [close]

  可選：

  [avatar on/off]

  這個很實用，因為 Anam 有成本與延遲。使用者可以切回 voice-only。

  fallback 設計

  如果 LiveKit room 連上但 avatar 還沒加入：

  先顯示 AREQA icon orb
  avatar video track 出現後 crossfade 到 video

  如果 ANAM_AVATAR_ID 沒設：

  直接 voice-only，不報錯，只顯示現在的 AREQA icon

  這符合 Anam setup prompt 的規則：avatar 是增強，不應該讓語音功能壞掉。

  我會加的前端結構

  大概拆成這樣：

  frontend/src/components/LiveTutor/
  ├── LiveTutorPanel.tsx
  ├── styles.ts

  LiveTutorPanel 還是 session owner。
  LiveTutorAvatarStage 專門處理：

  - render LiveKit avatar video track
  - fallback AREQA icon
  - loading / speaking / muted state
  - mobile layout

  如果之後接 LiveKit，前端 service 可以新增：

  frontend/src/services/livekit/
  ├── token.ts
  ├── client.ts
  ├── avatarTracks.ts

  我的設計取向

  我會做成「安靜、專注、學習陪伴感」，不要像直播間，也不要像客服浮窗。AREQA 是教育 QA，不適合太花的舞台感。

  最適合的第一版：

  - avatar 佔 panel 主要面積
  - 黑或深灰背景，讓臉清楚
  - 控制列很小
  - 聊天 transcript 照舊進入 message list
  - avatar panel 可收合成原本 orb

  簡單說：角色是語音模式的臉，不是另一個產品入口。


› 所以 你是說基於現在的設計 如果將avater on 就把原本logo的部分 改為avater 顯示 ?


• 對，我的建議就是這樣。

  基於現在設計，不要大改整個 Live Tutor。把目前這段 logo orb：

  frontend/src/components/LiveTutor/LiveTutorPanel.tsx:542

  替換成一個可切換的 stage：

  <LiveTutorAvatarStage
    status={status}
    avatarVideoTrack={avatarVideoTrack}
    avatarEnabled={avatarEnabled}
  />

  邏輯是：

  avatar on + 有 video track
    -> 顯示 Anam avatar video

  avatar on + 還在等 video track
    -> 先顯示目前 AREQA logo orb / Connecting

  avatar off
    -> 顯示目前 AREQA logo orb

  avatar error
    -> 語音繼續，畫面 fallback 成 AREQA logo orb

  也就是：

  現在：
  Live Tutor panel = AREQA logo orb + audio

  之後：
  Live Tutor panel = Anam avatar video 或 AREQA logo fallback + audio

  這樣最好，原因是：

  - 現有 UI 使用者不需要重新學
  - Live voice 的 session lifecycle 不被打亂
  - avatar 壞了不會拖垮語音
  - 未來可以加一個小按鈕切 avatar on/off
  - 前端改動集中在 LiveTutorPanel 和一個新 LiveTutorAvatarStage

  所以是：avatar on 時，把原本 logo 的位置換成 avatar；avatar off 或還沒 ready，就沿用原本 logo。