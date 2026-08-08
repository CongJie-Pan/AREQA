## 問題根因：為什麼目前實作會「跳著一行行出現」

目前架構的核心問題不是動畫曲線或 delay 數值的調校問題，而是**渲染單位（reveal unit）與動畫觸發機制（mount-based animation）的錯配**。具體拆解如下：

### 1. Key 不穩定導致重複 mount

`key={`${index}-${row}`}` 這個 key 同時依賴 `index` 與 `row`（row 的實際文字內容）。在 streaming 過程中，同一個 row 的文字會持續增長（例如段落文字從「這是一」變成「這是一段」），row 字串本身在每次 throttle flush 後幾乎必定改變。React 的 reconciliation 是以 key 判斷「這是不是同一個邏輯元素」——key 一變，React 就認為這是全新元素，直接 unmount 舊 DOM 節點、mount 新節點，而不是更新現有節點的內容。這正是 CSS `animation` 會「重播」的根本原因：`animation-fill-mode: both` 加上 mount-triggered 的 CSS animation，只要元素被當作新節點插入 DOM，動畫就會從 `opacity:0` 重新開始播放一次。[^1][^2]

### 2. Row 是「離散區塊」而非「連續文字流」

`splitMarkdownRevealRows` 把 Markdown 切成 heading / list / quote / table / code fence / paragraph 等分類區塊，每個區塊各自用獨立 `<div>` + 獨立 `<ReactMarkdown>` 渲染。這代表視覺上的「一段文字」在 DOM 層面其實是多個彼此獨立、按 block 順序插入的節點。用戶感知到的「跳出來」正是這些 block-level 節點依序被插入、各自觸發一次 translateY+blur 動畫的疊加效果——而 Perplexity / Claude / ChatGPT 想要的效果是**字元/token 級的連續淡入**，視覺粒度完全不同。

### 3. Throttle + Stagger Delay 造成「批次跳動」

`useThrottledValue(content, 56)` 讓 content 每 56ms 才更新一次，這代表每次更新時可能同時新增多個字、甚至多行內容。搭配 `Math.min(index, 14) * 38ms` 的 stagger delay，效果是「一批文字」在同一時間點被插入、然後依序播放位移動畫，而不是逐字連續浮現。這種「批次到達」+「逐行 stagger」的組合，本質上就是視覺上的階梯感（jank），與絲滑的連續 reveal 是相反的設計方向。

### 4. `useDeferredValue` 沒有解決根本問題

`useDeferredValue` 只是把非緊急更新的渲染優先權降低，避免掉幀，但它不改變「新 row 出現 = 新 DOM 節點 = 動畫重播」的結構性問題，也無法讓已存在的文字節點「被動延展」而不觸發新動畫。

综合來看，Perplexity/Claude/ChatGPT 之所以看起來「絲滑一整片浮現」，關鍵在於它們的 reveal 效果是**基於已存在內容的視覺遮罩位移**，而不是**基於新 DOM 節點插入所觸發的 entrance animation**。這是兩種完全不同的實作範式。

## 業界主流做法：真正絲滑的 Streaming Reveal 通常怎麼做

### 方案 A：Per-token/per-word CSS 動畫 + 穩定 append（Streamdown 模式）

Vercel 官方的 `streamdown`（`react-markdown` 的 drop-in replacement，專為 AI streaming 設計）採用的策略是：將 Markdown 解析為區塊後，**只有最後一個未完成區塊會持續重渲染，其餘區塊被 memoize 不動**；同時提供 `animated` prop，透過 rehype 外掛把新到達的文字用 `sep: "word"` 或 `sep: "char"` 切成獨立 `<span>`，讓每個新 mount 的 span 觸發一個極短（150ms）的 fade-in，並利用 React reconciliation 只讓「新增」的 span 觸發動畫、既有 span 不受影響。這與目前實作的差異在於：**reveal 單位是 word/char 而不是整個 block row**，且已渲染內容永遠不會被重新 mount。[^3][^4][^5]

### 方案 B：Mask-image / clip-path 遮罩位移（視覺上最接近「整段浮現」）

CSS `mask-image` 搭配 `linear-gradient` 是產生「整段內容從上到下漸進顯現」最經典的技巧：將 mask 設為從 `black`（完全顯示）過渡到 `transparent`（完全隱藏）的漸層，然後透過動畫改變 `mask-position` 或 `mask-size`，讓遮罩邊界往下移動，露出下方已經存在、但被遮住的內容。這個方法的關鍵優勢是：**遮罩動畫作用在容器層，不需要對個別文字節點做 mount/unmount**，因此不會有 key 變化導致的重播問題，也天然支援任意 Markdown 結構（表格、code block、數學公式都能被遮罩，只要遮罩是純粹的視覺層而不干擾底層 DOM）。[^6][^7][^8]

### 方案 C：Framer Motion `layout` animation + AnimatePresence

Framer Motion 的 layout animation 能在 DOM 結構變化時自動計算 FLIP（First-Last-Invert-Play）位移，讓新增內容的高度變化被平滑地動畫化，但這通常用於「訊息氣泡整體高度變化」場景，而非逐字 reveal；若用在細粒度 token 級動畫上效能成本較高，通常不是首選。

### 方案 D：requestAnimationFrame 控制遮罩高度／opacity 漸進顯示

一些实作直接用 `requestAnimationFrame` 循環，根据內容高度變化，逐步調整一個絕對定位的遮罩 `div`（例如 `background: linear-gradient` 疊在文字底部，隨著時間往下移動），達到「文字逐漸浮出遮罩」的效果，本質上是手動實作 mask-image 動畫但擁有更精細的時間控制（可配合 easing function、可暫停）。

## 各方案適用性評估

| 方案 | 是否需重構渲染邏輯 | 是否保留現有 row 分類 | 對 Markdown 結構相容性 | 效能（長回答） | 絲滑度 |
|---|---|---|---|---|---|
| Mask-image 容器遮罩位移 | 低（純 CSS 疊加層） | 可保留 | 高（不動 DOM 結構） | 高 | 高 |
| Per-word/char span 動畫（Streamdown 模式） | 中（需切字元/詞） | 需改為單一 memoized 區塊 | 高（官方已處理 streaming edge case） | 中高 | 高 |
| Stable append row identity（用 index 但避免文字變化觸發 remount） | 低（改 key 策略） | 保留 | 高 | 高 | 中（仍是 block-level） |
| Intersection/ResizeObserver 監控高度 | 高（需額外量測邏輯） | 可保留 | 中 | 中 | 中 |
| Framer Motion layout animation | 中 | 可保留 | 中 | 中低（大量節點時掉幀） | 中 |
| requestAnimationFrame 手動遮罩 | 高 | 可保留 | 高 | 中（需自行節流） | 高 |

## 最推薦的 React Implementation Strategy

綜合考量「支援 streaming partial Markdown」「不破壞 list/table/code/math」「不造成 excessive remount」「效能適合長回答」，建議採用**兩層疊加架構**：**Stable Block Identity（解決 remount 問題）+ Mask-Image 容器級漸進顯現（解決視覺絲滑度問題）**，並可選擇性引入 Streamdown 的 per-block memoization 概念取代手寫 `splitMarkdownRevealRows`。

### 核心修正 1：徹底修正 Key 策略，消除虛假 remount

Row 的 key 絕不能包含會隨 streaming 變化的內容（`row` 字串本身）。應該改為只依賴該 row 在序列中的**穩定序號**，一旦某個 row 被建立就永遠使用同一個 key，即使其文字內容持續增長：

```tsx
{revealRows.map((row, index) => (
  <div
    className={styles.streamingRowReveal}
    data-streaming-row-index={index}
    key={`row-${index}`} // 穩定 key，只依賴序號，不依賴內容
    style={{ '--streaming-row-delay': `${Math.min(index, 14) * 38}ms` }}
  >
    <ReactMarkdown ...>{row}</ReactMarkdown>
  </div>
))}
```

這樣一來，同一個 row 在文字增長時只會觸發 React 對該節點的 **update**（重新渲染子樹），而不是 unmount + mount，CSS animation 也就不會重播。這是最低成本、必須優先修的一步，即使不改動畫策略也能立即消除「跳動」的一部分成因。

### 核心修正 2：把「Entrance Animation」從 Row 層級移到「Newly-Revealed Tail」層級

只有**新增的 row（前一次渲染時不存在的最後一個或最後幾個 row）**才需要觸發 entrance animation；已存在的 row 絕不應重新觸發動畫。做法是用一個 ref 記錄「已經播放過動畫的最大 index」，並用 CSS class（而非 key 變化）標記新 row：

```tsx
const animatedUpToRef = useRef(-1);

const rowsWithAnimFlag = revealRows.map((row, index) => {
  const shouldAnimate = index > animatedUpToRef.current;
  return { row, index, shouldAnimate };
});

useEffect(() => {
  animatedUpToRef.current = revealRows.length - 1;
}, [revealRows.length]); // 只在 row 數量增加時更新，不在文字內容變化時更新
```

```tsx
<div
  key={`row-${index}`}
  className={cx(styles.streamingRowBase, shouldAnimate && styles.streamingRowReveal)}
>
```

配合 CSS 用 `animation-play-state` 或直接條件式套用 class，確保動畫只在該 row 第一次出現時播放一次，之後即使內容持續 stream 進來也不再重播。

### 核心修正 3：疊加容器級 Mask-Image 漸進顯現，取代逐行位移動畫

這是達成「整段自然由上到下淡入」視覺效果的關鍵。在 `streamingMarkdownRows` 容器外層疊加一個遮罩層，讓最新內容的底部邊界呈現漸層淡出，隨著內容增長，遮罩區域自然往下延伸：

```css
.streamingMarkdownRows {
  -webkit-mask-image: linear-gradient(
    to bottom,
    black calc(100% - 24px),
    transparent 100%
  );
  mask-image: linear-gradient(
    to bottom,
    black calc(100% - 24px),
    transparent 100%
  );
  transition: mask-size 200ms ease-out;
}
```

這個遮罩只作用在容器底部邊界（新內容剛到達的位置），營造「文字從模糊/透明過渡到清晰」的邊緣效果，而不需要每個 row 各自做 translateY+blur 的進場動畫。配合 row 層級的簡化版 fade（僅 `opacity` transition，不做位移），可以達到視覺上連續、統一的「浮現」感，而不是逐行跳動。[^8][^6]

### 核心修正 4：以 `prefers-reduced-motion` 與效能為前提的完整 CSS

```css
@media (prefers-reduced-motion: no-preference) {
  .streamingRowReveal {
    animation: fadeInSoft 220ms ease-out both;
  }
}

@media (prefers-reduced-motion: reduce) {
  .streamingRowReveal {
    animation: none;
    opacity: 1;
  }
  .streamingMarkdownRows {
    mask-image: none;
    -webkit-mask-image: none;
  }
}

@keyframes fadeInSoft {
  from { opacity: 0; }
  to { opacity: 1; }
}
```

移除 `transform: translateY(8px)` 與 `filter: blur(2px)` 的組合動畫是有意為之——`filter: blur()` 在動畫過程中會強迫瀏覽器持續重新合成（repaint）整個文字圖層，在長回答、大量 row 同時存在時是效能殺手，尤其在低階裝置或大量 KaTeX/table 渲染同時發生時容易掉幀。改為單純 `opacity` transition 搭配容器級 mask，視覺上更接近 Perplexity/Claude 的效果，而效能成本遠低於 `blur + transform` 組合（Streamdown 官方文件也指出 `blurIn` 效果應謹慎使用於長文字流，並建議搭配較長 duration 而非逐字套用重疊 filter）。[^3]

### 是否要考慮直接採用 Streamdown

若專案能接受依賴替換，`streamdown` 是 Vercel 官方針對這個確切場景（React + streaming Markdown + 不完整語法 + math + 動畫）打造的 `react-markdown` drop-in replacement，內建 `remend`（目前架構已經在用）、per-block memoization（只有最後未完成區塊重渲染）、以及 `animated` prop 的 per-word fade-in，且明確處理 code block / SVG / MathML 不套用文字動畫以避免破壞版面。這相當於把目前手寫的 `splitMarkdownRevealRows` + 手動 row reveal 整套邏輯替換為官方維護、已處理過大量 edge case 的方案，長期維護成本更低；若專案已高度客製化（citation marker normalization、math normalization 等），則建議保留現有 pipeline 但套用上述四項修正,將 Streamdown 的「memoize 已完成區塊、只重渲染最後區塊」這個核心思路移植進 `splitMarkdownRevealRows` 的呼叫端（用 `React.memo` 包裝每個 row 元件，並確保除最後一個 row 外的 props 引用穩定，避免不必要重渲染）。[^4][^9][^3]

### 實作優先順序建議

1. 立即修正 key 策略（core fix 1）——零風險、立即消除大部分跳動感。
2. 引入「僅新增 row 觸發動畫」邏輯（core fix 2）——中等工作量，解決重播問題。
3. 加入容器 mask-image 漸進顯現（core fix 3）——視覺效果提升最大，純 CSS、無需改動渲染邏輯。
4. 簡化動畫為純 opacity + reduced-motion 支援（core fix 4）——效能與無障礙雙重收益。
5. 中長期評估遷移至 Streamdown 或至少借鏡其 memoization 策略，減少 ReactMarkdown 重複 parse 的成本。

---

## References

1. [Keys, Reconciliation, and Remounting: The Real Rules](https://www.frontendinterview.in/blog/react-keys-reconciliation-remounting) - Why keys matter beyond lists: how reconciliation decides to preserve state or remount, why index key...

2. [Key Stability in Lists | React Performance - Steve Kinney](https://stevekinney.com/courses/react-performance/key-stability-in-lists) - Master keys to keep state, focus, and animations intact—no more mysterious remounts or janky list up...

3. [Animation](https://streamdown.ai/docs/animation) - Streamdown supports per-word streaming animation through the built-in animated prop. Words fade in a...

4. [GitHub - vercel/streamdown: A drop-in replacement for react-markdown, designed for AI-powered streaming.](https://github.com/vercel/streamdown) - A drop-in replacement for react-markdown, designed for AI-powered streaming. - vercel/streamdown

5. [Configuration - Introduction - Streamdown](https://vercel-streamdown.mintlify.app/customization/configuration)

6. [CSS mask-image: Gradients, Shapes & Creative Effects](https://savvy.co.il/en/blog/css/css-mask-image/) - Master CSS mask-image with interactive demos. Create gradient fades, SVG shape masks, composite effe...

7. [CSS Gradient Text Reveal](https://medium.com/@mattkenefick/css-gradient-text-reveal-739e7fe36221) - Using mask-image to create a smooth gradient mask reveal over complex backgrounds.

8. [CSS mask: Fade, Reveal & Shape Elements (Complete 2026 Guide)](https://www.w3tweaks.com/css/css-mask-property-explained/) - CSS mask uses another image or gradient as a stencil for element visibility. Unlike clip-path's hard...

9. [https://raw.githubusercontent.com/NeverSight/skill...](https://raw.githubusercontent.com/NeverSight/skills_feed/refs/heads/main/data/skills-md/vercel/streamdown/streamdown/SKILL.md)

