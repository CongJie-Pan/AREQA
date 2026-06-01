<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" style="height:64px;margin-right:32px"/>

# 我這兩天的開發流程是修理bug，要處理4個bug，我就在想，我想讓程式碼更好維護一些，就為每個code加了更詳細清晰的註解，並且針對超過350行code進行模組化。還有針對drift ai 的violation部分修過code，是修改問答系統中SSE的部分。

之後再修這些bug過程中，有一些比較難解的，就參照網路上的意見重構該部分代碼。
這期間我都只有更新和運行測試完。
最後都修改完執行，SSE串流功能出了問題 輸出不了文字。原有的bug還存在。但是測試都通過。
---
我的業務細節可以忽略，主要是開發上，我下次可以怎麼改善？如果是Google等好的工程師，一開始面對我的情境會怎麼做？

根據你描述的情境，問題的核心很清晰：**你同時做了太多不同性質的事（修 bug + 重構 + 模組化 + 改 SSE 邏輯），讓問題難以追蹤，最終測試通過但功能卻壞了**。以下是系統性的分析與改善建議。

***

## 你的核心問題：變動範圍失控

你在兩天內同時進行了四件性質完全不同的事：

1. 修 4 個 bug
2. 為所有程式碼加詳細註解
3. 對超過 350 行的程式碼做模組化重構
4. 重構 SSE 問答系統邏輯

這些事情混在一起，導致你無法判斷「是哪個改動讓 SSE 輸出失效」。業界最佳實踐明確指出：**修 bug 和重構絕對不能在同一個 commit 或同一個時間段混合進行**[^1_1][^1_2]。

***

## Google 工程師會怎麼做？

### 先建立「能失敗的測試」，再動手修

Google 和業界稱之為 **Test-Driven Bugfixing（TDB）**：先寫一個能重現 bug 的測試、確認它失敗，再去修程式碼，最後確認測試通過[^1_3][^1_4]。這樣做有兩個關鍵好處：

- **你知道自己真的修好了**，而不只是猜測
- **防止同樣的 bug 日後復發**（regression prevention）[^1_5]

你目前的問題是「測試都通過，但 bug 還在」，這幾乎可以斷定：**你的測試根本沒有覆蓋到原始 bug 的情境**，所以測試通過只是假象。

### Atomic Commits：一次只做一件事

Google 內部工程實踐強調，每個 commit（CL）必須是最小可獨立運作的單位[^1_6][^1_7]。正確的作法是：

```
commit 1: fix bug #1 (含針對此 bug 的失敗測試)
commit 2: fix bug #2
commit 3: fix bug #3
commit 4: fix bug #4
--- 以上修完，全部通過 ---
commit 5: refactor module A (模組化)
commit 6: add comments to module B
```

這樣做的好處是：任何一步出錯，你都能用 `git bisect` 或 `git revert` 精準定位並回滾[^1_8][^1_6]。

### Bug Fix 和 Refactoring 的黃金法則

| 行為 | 正確時機 |
| :-- | :-- |
| 修 bug | 先做，獨立 commit，附測試 |
| 重構 / 模組化 | bug 全部修完、測試穩定後再做 |
| 加註解 | 可隨時做，但單獨 commit |
| 重構第三方邏輯（如 SSE） | 必須單獨分支，有充分測試才合入 |

業界共識是：「如果 bug 在重構前就存在，重構後它幾乎肯定還在」[^1_1]。你的情況正是如此——SSE 的重構反而引入了新問題。

***

## 下次面對同樣情境的改善步驟

**Phase 1：只專注修 bug（2 天）**

- 每個 bug 獨立開一個 branch
- 先寫一個會失敗的測試重現 bug[^1_9][^1_10]
- 修程式碼直到測試通過
- Commit 訊息格式：`fix: [bug#1] 修復 SSE 串流中斷問題`
- 4 個 bug 全修完後，執行所有測試，確認 green

**Phase 2：重構（另排時間）**

- 在所有 bug 都修完、功能穩定的前提下才動手[^1_1]
- 模組化一次只處理一個模組，單獨 commit
- 每次重構後立刻跑測試，確認沒有 regression

**Phase 3：針對 SSE 這類複雜改動**

- 複雜的串流邏輯改動要有**整合測試（integration test）**，不只是單元測試
- 考慮用 feature flag 把新舊邏輯隔開，可以快速切換回舊版

***

## 你現在的燃眉之急

既然測試通過但功能壞了，優先做兩件事：

1. **用 `git log` 找到你這兩天所有的 commit，逐一 `git revert` 或 `git bisect`**，找出是哪個 commit 破壞了 SSE 輸出
2. **針對「SSE 能正常輸出文字」這個情境，補寫一個整合測試**[^1_5]，讓它先失敗，再修到通過

你的測試套件目前的問題在於：它只測試了程式碼的結構是否正確（單元測試），但沒有測試「SSE 能否真正把文字串流到前端」這個端對端行為[^1_11]。
<span style="display:none">[^1_12][^1_13][^1_14][^1_15][^1_16][^1_17][^1_18][^1_19][^1_20][^1_21][^1_22][^1_23][^1_24][^1_25][^1_26][^1_27][^1_28][^1_29][^1_30]</span>

<div align="center">⁂</div>

[^1_1]: https://www.techtarget.com/searchsoftwarequality/tip/When-and-how-to-refactor-code

[^1_2]: https://roccatello.it/2022/09/bugfixing-and-refactoring/

[^1_3]: https://evolveum.com/test-driven-bugfixing/

[^1_4]: https://www.tutisani.com/software-architecture/bug-fix-via-tdd.html

[^1_5]: https://www.avanderlee.com/workflow/test-driven-development-tdd-for-bug-fixes-in-swift/

[^1_6]: https://abseil.io/resources/swe-book/html/ch09.html

[^1_7]: https://google.github.io/eng-practices/review/developer/small-cls.html

[^1_8]: https://jeffreyfreeman.me/blog/writing-high-quality-well-scoped-commits/

[^1_9]: https://blog.planetargon.com/blog/entries/debugging-with-test-driven-development

[^1_10]: https://richardmorgan.com/software-engineering-best-practices/

[^1_11]: https://onlinelibrary.wiley.com/doi/10.1155/2011/492757

[^1_12]: https://static.crysys.hu/publications/files/setit/cpaper_szte_BagheriH22msr.pdf

[^1_13]: https://arxiv.org/html/2501.07531v1

[^1_14]: https://dev.to/wemake-services/best-engineering-practices-how-to-fix-a-bug-58g5

[^1_15]: https://github.com/google/eng-practices

[^1_16]: https://utkrusht.ai/blog/code-refactoring-techniques-that-work

[^1_17]: https://www.linkedin.com/posts/lalitkundu_at-google-id-go-home-knowing-my-systems-activity-7439673755469074432-IrM9

[^1_18]: https://security.googlecloudcommunity.com/community-blog-42/implementing-a-modern-detection-engineering-workflow-part-2-4056

[^1_19]: https://news.ycombinator.com/item?id=29019730

[^1_20]: https://oneuptime.com/blog/post/2026-01-15-server-sent-events-sse-react/view

[^1_21]: https://dev.to/samuelfaure/how-atomic-git-commits-dramatically-increased-my-productivity-and-will-increase-yours-too-4a84

[^1_22]: https://docs.apidog.com/sse-debugging-629889m0

[^1_23]: https://www.reddit.com/r/talesfromtechsupport/comments/1jr9x91/atomic_commits_a_real_life_case_study/

[^1_24]: https://cleverthis.com/news/writing-high-quality-well-scoped-commits/

[^1_25]: https://itnext.io/sse-event-driven-html-with-java-dc4a8666f3d2

[^1_26]: https://dev.to/samuelfaure/how-atomic-git-commits-dramatically-increased-my-productivity-and-will-increase-yours-too-4a84/comments

[^1_27]: https://cleverthis.com/news/

[^1_28]: https://stackoverflow.com/questions/25956243/debugging-html5-server-sent-events-in-browser

[^1_29]: https://ewirch.github.io/2017/08/better-commits-2-refactorings.html

[^1_30]: https://www.echoapi.com/blog/implementing-server-sent-events-sse-with-python-and-go/


---

# 那如果是Google工程師 他後續遇到這種結果會怎麼做 確保最有效率且無後遺症解決

Google 工程師面對「測試全過、但功能壞了」這種情況，會走一套非常明確的流程，核心原則是：**先止血（隔離影響），再找病因（溯源），最後根治並防止復發**。

***

## 第一步：立刻隔離，不繼續往前走

Google SRE 的黃金準則是——**有異常就先 rollback，不要先試著修**[^2_1][^2_2]。在你的情況下，代表：

1. 立刻 `git stash` 或切回上一個已知正常的 commit
2. 確認 SSE 功能在那個點是否正常，**先讓系統回到可運作狀態**
3. 這一步的目標是「止血」，不是「理解原因」

Google 的案例研究顯示，最快解決 incident 的團隊都有一個共同點：他們在理解原因之前就先 rollback 了，而不是邊查邊繼續往前推[^2_2]。

***

## 第二步：用 `git bisect` 二元搜尋找出破壞點

這是最關鍵的一步。`git bisect` 用二元搜尋法，在 O(log n) 的時間複雜度內找到「第一個壞掉的 commit」[^2_3][^2_4]：

```bash
git bisect start
git bisect bad HEAD          # 標記現在是壞的
git bisect good <之前正常的commit hash>  # 標記已知正常點

# Git 會自動 checkout 中間點，你測試後標記：
git bisect good  # 或 git bisect bad
# 重複幾次後，Git 直接告訴你哪個 commit 是元兇
```

更強的做法是搭配自動化腳本，讓 Git 自己跑[^2_4][^2_5]：

```bash
git bisect run ./test_sse_stream.sh
# 腳本回傳 0 = good，非 0 = bad，Git 全自動二元搜尋
```

Google 內部甚至有專門的自動化系統（論文記錄於 140 個專案）來做這件事[^2_6]。

***

## 第三步：確認病因後，**只修這一個問題**

找到破壞的 commit 後，Google 工程師會：

- 用 `git show <commit_hash>` 看清楚那個 commit 到底改了什麼[^2_5]
- **只針對那個改動做最小範圍的 revert 或 fix**，不順手多改任何東西
- 針對 SSE 串流這個具體失敗行為，補寫一個會失敗的整合測試，確認它通過[^2_2]
- Commit 訊息清楚標明：`fix: revert SSE refactor regression introduced in <hash>`

***

## 第四步：補寫 Postmortem（即使是個人專案）

Google SRE 文化要求每次 incident 後必須寫 postmortem[^2_2]，即使是個人開發，也建議花 10 分鐘記錄：


| 問題 | 你的答案 |
| :-- | :-- |
| 什麼時間點壞掉？ | 哪個 commit |
| 根本原因是什麼？ | 哪個改動影響了哪個邏輯 |
| 為什麼測試沒抓到？ | 缺少什麼測試覆蓋 |
| 下次怎麼預防？ | 例如：SSE 必須有端對端測試才能合入 |

這個習慣的價值不是「反省」，而是**建立你自己的工程記憶**，讓同類問題不再發生第二次[^2_1][^2_2]。

***

## 整體流程一覽

```
發現異常
  ↓
Rollback 到已知正常狀態（止血）
  ↓
git bisect 找出第一個壞的 commit（溯源）
  ↓
用 git show 理解那個 commit 改了什麼（診斷）
  ↓
最小範圍 fix / revert（根治）
  ↓
補寫針對此 bug 的整合測試（防復發）
  ↓
寫 Postmortem 10 分鐘（建立記憶）
```

最核心的心態差異是：普通工程師遇到問題會「繼續往前修」，而 Google 工程師的第一直覺是**先往後退，站穩了再往前**[^2_1]。
<span style="display:none">[^2_10][^2_11][^2_12][^2_13][^2_14][^2_15][^2_7][^2_8][^2_9]</span>

<div align="center">⁂</div>

[^2_1]: https://sre.google/sre-book/emergency-response/

[^2_2]: https://sre.google/workbook/incident-response/

[^2_3]: https://blog.puckwang.com/posts/2021/use-git-bisect-debug/

[^2_4]: https://gun.io/news/2025/05/git-bisect-debugging-guide/

[^2_5]: https://www.linkedin.com/posts/tathagat-gaikwad_git-devops-debugging-activity-7382668912347439104-qO-9

[^2_6]: https://research.google.com/pubs/archive/45794.pdf

[^2_7]: https://baroni.tech/posts/git-bisect/

[^2_8]: https://cloud.google.com/transform/5-critical-gaps-incident-response-planning-and-how-to-fix-them

[^2_9]: https://dev.to/emilysamp/how-to-run-an-automated-git-bisect-with-rspec-3dm3

[^2_10]: https://docs.cloud.google.com/docs/security/incident-response

[^2_11]: https://mcpmarket.com/tools/skills/git-bisect-debugging-workflow

[^2_12]: https://google.github.io/building-secure-and-reliable-systems/raw/ch16.html

[^2_13]: https://incident.io/blog/what-is-ai-sre-complete-guide-2026

[^2_14]: https://www.reddit.com/r/devops/comments/gfyqo7/how_do_i_implement_googles_incident_response/

[^2_15]: https://www.youtube.com/watch?v=Ks10Mv_KxNI

