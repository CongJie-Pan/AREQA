<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" style="height:64px;margin-right:32px"/>

# │ 我正在開發一個基於 React 的 LLM 聊天介面，前端使用了  react-markdown  與  remark-gfm  來渲染 AI 生成的 Markdown 文字。

│
│ 目前我的 AI 會在文字中隨機生成引用文獻的標記，例如：「這種總體性的信仰要求【文獻2】【文獻5】，使得任何異議都被視為威脅...」或者有時是  [2]  這種格式。
│
│ 我的目標：
│ 我希望將文字中的  【文獻X】  或  [X]  轉換成「可點擊的 Inline Citation Buttons（類似 Perplexity 內文的數字引用按鈕）」。點擊該按鈕後，會觸發 React 的 onClick 事件，打開對應文獻的詳細 Modal。
│
│ 請幫我研究並總結業界在 React 中實作這個功能的最佳實踐。請從以下幾個方向為我提供建議：
│
│ 1. 正則預處理 + 自訂 Markdown 元件：在送入 react-markdown 前把標記字串 replace 成特定 Markdown 語法（例如連結  [2](#cite-2) ），再攔截  <a>  標籤的作法是否推薦？效能如何？
│ 2. 自訂 Remark / Rehype Plugin：寫一個 Unified AST 樹的解析插件來精準捕捉這些文字並轉換為 React 節點，這會不會太複雜？有沒有現成的開源套件可以做到這件事（例如 react-string-replace 或是 remark-
│ directive）？
│ 3. Streaming 相容性：我們的聊天文字是逐字 Streaming 串流輸出的，哪一種方法在面對尚未輸出完整的字串（例如只輸出到  【文獻 ）時，最不會導致畫面閃爍或報錯？
│
│ 請給我您的最終推薦方案與具體的實作思路。

很好，現在我已有充足的資料可以給出一份完整的技術分析。以下是針對你三個問題的深度解答與最終推薦方案。

***

## React 內嵌引用按鈕實作最佳實踐


***

## 方案一：正則預處理 + 自訂 `<a>` 元件

**核心思路：** 在字串進入 `react-markdown` 之前，先用 `String.replace()` 把 `【文獻X】` 和 `[X]` 都統一轉換成標準 Markdown 連結語法 `[X](#cite-X)`，再用 `react-markdown` 的 `components` prop 攔截所有 `<a>` 標籤，辨識其 `href` 是否以 `#cite-` 開頭，若是則渲染成自訂的引用按鈕元件。

```tsx
// 1. 預處理函式：統一格式化引用標記
function preprocessCitations(text: string): string {
  // 處理全形【文獻X】格式
  text = text.replace(/【文獻(\d+)】/g, '[$1](#cite-$1)');
  // 處理半形 [X] 格式（僅數字，避免誤碰 Markdown 連結）
  text = text.replace(/\[(\d+)\](?!\()/g, '[$1](#cite-$1)');
  return text;
}

// 2. 引用按鈕元件
const CitationButton = ({ citationId, onClick }: {
  citationId: number;
  onClick: (id: number) => void;
}) => (
  <button
    onClick={() => onClick(citationId)}
    className="inline-flex items-center justify-center w-5 h-5 mx-0.5
               text-xs font-bold text-white bg-blue-500 rounded-full
               hover:bg-blue-600 cursor-pointer align-super"
    style={{ fontSize: '0.65rem', lineHeight: 1 }}
  >
    {citationId}
  </button>
);

// 3. 攔截 <a> 標籤的 react-markdown 元件
const markdownComponents = {
  a: ({ href, children, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) => {
    if (href?.startsWith('#cite-')) {
      const id = parseInt(href.replace('#cite-', ''), 10);
      return <CitationButton citationId={id} onClick={handleOpenModal} />;
    }
    return <a href={href} {...props}>{children}</a>;
  }
};

// 4. 整合使用
function ChatMessage({ content }: { content: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={markdownComponents}
    >
      {preprocessCitations(content)}
    </ReactMarkdown>
  );
}
```

**效能評估：**

- ✅ **實作極簡**：不需要理解 AST，任何人都能快速維護。
- ✅ **與現有工具零衝突**：完全利用 `react-markdown` 現有機制，`remark-gfm` 照常工作。
- ⚠️ **Regex 維護風險**：若 LLM 輸出的格式多樣（如 `[文獻 2]`、`（文獻2）`），你需要持續迭代 Regex，容易出現邊界誤觸。
- ⚠️ **每次渲染都重跑 replace**：在 Streaming 場景下每個 Token 都會觸發，可透過 `useMemo` 緩解。

這是業界最常見的輕量作法，完全符合你的需求且幾乎不增加工程複雜度 。[^1][^2]

***

## 方案二：自訂 Remark Plugin（AST 操作）

**核心思路：** 寫一個 `remark` Plugin，在 `unified` 解析樹（MDAST）的 `text` 節點中用 `findAndReplace` 精確捕捉引用標記，並將其替換為自訂的 HAST 節點（帶有 `data-cite-id` 屬性的 `<button>`），再由 `react-markdown` 透過 `components` prop 轉換成 React 元件。

```tsx
// remark-citation-plugin.ts
import { findAndReplace } from 'mdast-util-find-and-replace';
import type { Plugin } from 'unified';
import type { Root } from 'mdast';

const remarkCitationPlugin: Plugin<[], Root> = () => {
  return (tree) => {
    findAndReplace(tree, [
      // 同時匹配兩種格式
      [/【文獻(\d+)】|\[(\d+)\](?!\()/g, (_match: string, g1: string, g2: string) => {
        const id = g1 || g2;
        return {
          type: 'link',
          url: `#cite-${id}`,
          data: { hProperties: { 'data-cite-id': id } },
          children: [{ type: 'text', value: id }],
        };
      }],
    ]);
  };
};
```

目前最成熟的現成套件參考 ：[^3]

- `mdast-util-find-and-replace`（`unified` 生態系官方工具）：最適合此需求，可精確在文字節點中做替換而不破壞其他 Markdown 語法。
- `remark-directive`：適合你能完全控制 LLM 輸出格式的場景（讓 LLM 輸出 `::cite[^2]` 這樣的 Directive 語法），功能強大但需要改 Prompt。
- `rehype-citation`：主要用於 BibTeX 學術引用格式，**不適合** 你目前的數字引用需求 。[^4]

**效能評估：**

- ✅ **精準且正確**：在 AST 層面操作，不可能誤觸已存在的 Markdown 連結語法。
- ✅ **可複用**：Plugin 寫好後可應用在 Next.js SSG、MDX 等所有場景。
- ⚠️ **額外學習成本**：需要理解 `unist-util-visit`、MDAST/HAST 的 Node 結構。
- ⚠️ **Streaming 下有潛在問題**：見下一節。

***

## 方案三：Streaming 相容性分析（最關鍵）

這是你的架構中技術風險最高的環節。當 Token 正在逐字串流，你的字串可能出現這些**危險的中間狀態**：

```
「...這種總體性的信仰要求【文獻      ← 此時僅輸出到這裡
「...這種總體性的信仰要求【文獻2     ← 數字出現但右括號未到
「...這種總體性的信仰要求【文獻2】   ← 完整，安全
```

`react-markdown` 本身在面對不完整的語法時已相當穩健（它會將未封閉的節點當成純文字），但加入自訂 Plugin 或 Regex 後，就可能出現「標記半路出現 → 渲染成按鈕 → 下一個 Token 讓按鈕消失」的閃爍問題 。[^5][^6]

**各方案在 Streaming 下的表現比較：**


| 方案 | 面對 `【文獻` 不完整時的行為 | 閃爍風險 |
| :-- | :-- | :-- |
| 正則預處理 | Regex 不匹配 → 原樣顯示 `【文獻` | ⚠️ 低度閃爍（從文字變按鈕） |
| Remark Plugin | `findAndReplace` 不匹配 → 原樣顯示 | ⚠️ 低度閃爍 |
| **延遲渲染（最佳解）** | **不渲染引用標記，直到字串穩定** | ✅ **零閃爍** |

**生產環境最佳解：`remend` + `useDeferredValue`**

Vercel 於 2025 年 12 月開源的 `remend` 套件，正是為了解決「Streaming 時 Markdown 語法不完整」這個問題而生 。使用它作為預處理器，可確保任何不完整的標記在下一個 Token 到來之前自動被「補完」，不會殘留在畫面上：[^7]

```tsx
import remend from 'remend';
import { useDeferredValue, useMemo } from 'react';

function StreamingMessage({ streamedContent, citations, onCiteClick }: {
  streamedContent: string;
  citations: Record<number, { title: string; url: string }>;
  onCiteClick: (id: number) => void;
}) {
  // 使用 useDeferredValue 讓引用渲染「慢一拍」，避免閃爍
  const deferredContent = useDeferredValue(streamedContent);

  // 管道：remend 補完不完整語法 → 正則替換引用格式
  const processedContent = useMemo(() => {
    const completed = remend(deferredContent); // 補完未封閉的 Markdown 語法
    return completed
      .replace(/【文獻(\d+)】/g, '[$1](#cite-$1)')
      .replace(/\[(\d+)\](?!\()/g, '[$1](#cite-$1)');
  }, [deferredContent]);

  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        a: ({ href, children }) => {
          if (href?.startsWith('#cite-')) {
            const id = parseInt(href.replace('#cite-', ''), 10);
            return (
              <button
                onClick={() => onCiteClick(id)}
                className="inline-flex items-center justify-center
                           w-5 h-5 text-xs font-bold text-white
                           bg-blue-500 rounded-full hover:bg-blue-600
                           align-super mx-0.5 cursor-pointer"
              >
                {id}
              </button>
            );
          }
          return <a href={href}>{children}</a>;
        }
      }}
    >
      {processedContent}
    </ReactMarkdown>
  );
}
```

若你想要更徹底地解決 Streaming 渲染問題，也可考慮將整個 `react-markdown` 換成 `streamdown`（Vercel 出品，直接替換，同樣接受 `components` prop，且內建對不完整語法的優雅處理）。[^8]

***

## 最終推薦方案

**結論：採用「方案一（正則預處理）+ `remend` 補完 + `useDeferredValue` 防閃爍」的組合。**

這個組合在以下三個維度都達到最優解：

1. **正確性**：`remend` 確保任何時刻傳入 `react-markdown` 的字串語法都是完整的 。[^7]
2. **簡潔性**：不需要學 AST，整個核心邏輯不超過 30 行，任何前端工程師都可維護 。[^1]
3. **Streaming 穩定性**：`useDeferredValue` 讓引用按鈕的出現「延遲到字串穩定後」，視覺上無任何閃爍 。[^9][^5]

若你未來需要讓 LLM 輸出更語意化的標記格式（如 `::cite[^2]{.citation}`），再考慮升級到 `remark-directive` Plugin，整個管道依然可以平滑遷移。
<span style="display:none">[^10][^11][^12][^13][^14][^15][^16][^17][^18][^19][^20][^21][^22][^23][^24][^25][^26][^27][^28][^29][^30][^31][^32][^33][^34][^35][^36][^37][^38][^39][^40][^41]</span>

<div align="center">⁂</div>

[^1]: https://dev.to/flumer/enhance-your-markdown-with-custom-react-components-using-react-markdown-1kbi

[^2]: https://www.singlehanded.dev/blog/understanding-the-components-prop-in-react-markdown

[^3]: https://leeroopedia.com/index.php/Implementation:Infiniflow_Ragflow_MarkdownContent_Component

[^4]: https://www.npmjs.com/package/rehype-citation/v/0.0.3

[^5]: https://auditbuffet.com/patterns/ab-000329

[^6]: https://x.com/haydenbleasel/status/1996640723886919965

[^7]: https://vercel.com/changelog/new-npm-package-for-automatic-recovery-of-broken-streaming-markdown

[^8]: https://reactscript.com/render-streaming-ai-markdown/

[^9]: https://dev.to/jvoltci/i-made-streaming-markdown-300x-faster-heres-the-architecture-4a9f

[^10]: https://github.com/remarkjs/react-markdown

[^11]: https://thepromptbench.com/ai-product-ux/streaming-ui-patterns-that-dont-break/

[^12]: https://github.com/threepointone/markdown-in-js

[^13]: https://www.npmjs.com/package/remark-rehype/v/9.1.0

[^14]: https://github.com/kunall17/react-native-markdown-editor/blob/master/README.md

[^15]: https://github.com/orgs/remarkjs/discussions/1278

[^16]: https://github.com/tomasdelima/react-custom-markdown

[^17]: http://github.com/rehypejs/rehype/blob/main/doc/plugins.md

[^18]: https://engineering.streak.com/p/preventing-unstyled-markdown-streaming-ai

[^19]: https://www.npmjs.com/package/rehype-react/v/7.0.0

[^20]: https://danielmschmidt.de/posts/2024-08-09-remark-plugin-inline-github-code-snippets/

[^21]: https://github.com/remarkjs/remark/blob/main/doc/plugins.md

[^22]: https://github.com/iansinnott/react-string-replace

[^23]: https://dev.to/ritek/the-power-of-remark-6h

[^24]: https://github.com/orgs/remarkjs/discussions/1151

[^25]: https://github.com/remarkjs/remark

[^26]: https://www.usingandunderstanding.ai/create/4cc1bb3e-e914-4552-9e0a-5ee004a867a3

[^27]: https://github.com/orgs/remarkjs/discussions/867

[^28]: https://www.npmjs.com/package/remark-marginnotes

[^29]: https://github.com/markedjs/marked/issues/3657

[^30]: https://github.com/orgs/Milkdown/discussions/1674

[^31]: https://classic.yarnpkg.com/en/package/react-string-replace

[^32]: https://github.com/twardoch/remark-mark-plus

[^33]: https://www.reddit.com/r/Rag/comments/1gp0ga7/how_to_implement_citation_display_in_a_streaming/

[^34]: https://docs.cohere.com/docs/rag-citations

[^35]: https://www.reddit.com/r/Rag/comments/1qqmcqh/streaming_rag_with_sources/o2ia5z4/

[^36]: https://www.youtube.com/watch?v=P4xHWojIB-M

[^37]: https://www.reddit.com/r/nextjs/comments/1k64zyy/how_do_you_stream_citations_on_reactmarkdown/

[^38]: https://www.assistant-ui.com/docs/ui/streamdown

[^39]: https://medium.com/data-science-collective/anthropic-style-citations-with-any-llm-2c061671ddd5

[^40]: https://i-study-everyday.online/category/ragflow/

[^41]: https://www.shadcn.io/ai/response.mdx

