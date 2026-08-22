const stages = [
  {
    name: "建立資料",
    short: "知道分析輸入是什麼",
    title: "建立研究資料",
    brief:
      "你已經先看過資料表。現在扮演研究人員，判斷多位專家、多個學習情境與多個模型交錯出現時，資料結構帶來什麼分析問題。",
    taskTitle: "任務：指出這份資料最需要小心的地方",
    question: "下列哪一點是 3.4 進入階層分析前最在意的風險？",
    choices: [
      "同一位評分者與同一個 scenario 會重複出現在資料中",
      "模型名稱太長，圖表不容易排版",
      "每個分數都是 1 到 7，所以不能畫圖",
    ],
    correct: 0,
    correctText:
      "正確。這就是 repeated measurements：資料列不是完全獨立，所以不能只把所有列當成互不相關的觀測。",
  },
  {
    name: "看普通平均",
    short: "體會 naive average 的限制",
    title: "先做最直覺的平均分比較",
    brief:
      "研究人員通常會先看平均分。這一步很有用，但它還沒有處理評分者嚴格程度和情境難度。",
    taskTitle: "任務：先用平均分做初判",
    question: "只看右側平均分，你會先判斷哪個模型表現最好？",
    choices: ["LearnLM", "GPT-4o", "Gemini 1.5 Pro"],
    correct: 0,
    correctText:
      "這是合理初判。但 3.4 不會停在這裡，因為平均分可能混入評分者與題目差異。",
  },
  {
    name: "辨識偏差",
    short: "找出評分者與情境效果",
    title: "辨識 repeated measurements 的偏差來源",
    brief:
      "階層式迴歸的直覺是：不要把每筆評分當成漂浮在空中的獨立數字，而是把它放回所屬背景中。分數同時受到模型、評分者、學習情境影響。",
    taskTitle: "任務：判斷哪個因素應該被模型納入",
    question: "如果 E03 總是給低分，S04 又特別難教，分析模型應該怎麼處理？",
    choices: [
      "把 E03 的嚴格程度和 S04 的難度納入估計",
      "直接刪掉 E03 和 S04",
      "只保留 LearnLM 的分數",
    ],
    correct: 0,
    correctText:
      "正確。階層模型會把評分者和 scenario 當作背景層一起估計，避免把「嚴格評分者」或「困難題目」誤算成模型能力差。",
  },
  {
    name: "調整模型效果",
    short: "從 raw score 到 adjusted effect",
    title: "估計調整後的模型效果",
    brief:
      "這一關把分數拆成幾個來源：整體平均、模型效果、評分者偏差、scenario 難度和隨機誤差。真正要比較的是模型效果，但它必須在控制其他來源後才比較公平。",
    taskTitle: "任務：完成分析公式的解讀",
    question: "在這個簡化公式中，哪一項才是我們真正想比較的主角？",
    choices: ["model effect", "evaluator bias", "random noise"],
    correct: 0,
    correctText:
      "正確。model effect 才是研究主角；evaluator bias 和 scenario difficulty 是必須控制的背景差異。",
  },
  {
    name: "加入不確定性",
    short: "理解 credible interval",
    title: "不要只報一個分數，也要報不確定性",
    brief:
      "貝氏統計的直覺是：舊經驗加上新數據，得到更新後的判斷。論文使用 Bayesian analysis，所以不只報一個估計分數，也會報 posterior mean 和 95% highest density interval 來呈現不確定性。",
    taskTitle: "任務：判斷哪個結論比較嚴謹",
    question: "看到模型分數後，哪種說法最接近 3.4 的精神？",
    choices: [
      "LearnLM 的估計較高，而且不確定性範圍也應一起報告",
      "LearnLM 平均高 0.1，所以永遠一定比較好",
      "只要畫圖好看，就不用管信心範圍",
    ],
    correct: 0,
    correctText:
      "正確。3.4 的貝氏框架重點之一，是把「目前資料支持什麼」和「我們還有多不確定」一起呈現。",
  },
  {
    name: "質化編碼",
    short: "整理文字回饋主題",
    title: "把開放式回饋變成可分析的主題",
    brief:
      "除了分數，3.4 也分析專家寫下的開放式回饋。研究人員會建立 codebook，標註每段回饋是否出現某些教學行為主題。",
    taskTitle: "任務：把文字回饋標成主題",
    question: "「這個 tutor 沒有直接給答案，而是一步步問問題引導學生。」最適合標哪些主題？",
    choices: [
      "challenges_learner + step_by_step",
      "formatting + response_time",
      "tech_error + no_refusals",
    ],
    correct: 0,
    correctText:
      "正確。這就是質化分析：不是只問誰分高，也要整理大家覺得它好或差的具體行為。",
  },
];

const rows = [
  ["E01", "S01", "LearnLM", 6.2, "clear, guiding"],
  ["E01", "S01", "GPT-4o", 4.8, "gave answer quickly"],
  ["E02", "S02", "LearnLM", 5.8, "step by step"],
  ["E02", "S02", "Gemini 1.5 Pro", 5.0, "clear but less adaptive"],
  ["E03", "S04", "LearnLM", 4.9, "hard scenario"],
  ["E03", "S04", "GPT-4o", 4.1, "too much info"],
];

const rawScores = [
  ["LearnLM", 5.63],
  ["Gemini 1.5 Pro", 5.02],
  ["GPT-4o", 4.46],
];

const adjustedScores = [
  ["LearnLM", 5.54, "5.26 to 5.82"],
  ["Gemini 1.5 Pro", 5.04, "4.78 to 5.31"],
  ["GPT-4o", 4.53, "4.24 to 4.82"],
];

const themeCounts = [
  ["challenges_learner", "LearnLM", 42, "good"],
  ["step_by_step", "LearnLM", 39, "good"],
  ["clarity", "LearnLM", 37, "good"],
  ["gives_away_answers", "GPT-4o", 31, "warn"],
  ["info_amount", "GPT-4o", 24, "warn"],
  ["keeps_on_topic", "Gemini 1.5 Pro", 29, "good"],
];

const state = {
  current: 0,
  maxUnlocked: 0,
  answered: new Array(stages.length).fill(false),
};

const stageList = document.querySelector("#stageList");
const datasetPreview = document.querySelector("#datasetPreview");
const rowMetric = document.querySelector("#rowMetric");
const evaluatorMetric = document.querySelector("#evaluatorMetric");
const scenarioMetric = document.querySelector("#scenarioMetric");
const modelMetric = document.querySelector("#modelMetric");
const rowCount = document.querySelector("#rowCount");
const startAnalysisButton = document.querySelector("#startAnalysisButton");
const analysisGuide = document.querySelector("#analysisGuide");
const stageEyebrow = document.querySelector("#stageEyebrow");
const stageTitle = document.querySelector("#stageTitle");
const stageBrief = document.querySelector("#stageBrief");
const taskPanel = document.querySelector("#taskPanel");
const evidencePanel = document.querySelector("#evidencePanel");
const progressFill = document.querySelector("#progressFill");
const progressText = document.querySelector("#progressText");
const backButton = document.querySelector("#backButton");
const nextButton = document.querySelector("#nextButton");

function renderStageList() {
  stageList.innerHTML = stages
    .map((stage, index) => {
      const locked = index > state.maxUnlocked;
      const done = state.answered[index];
      const active = index === state.current;
      return `
        <button class="stage-button ${active ? "active" : ""} ${done ? "done" : ""} ${locked ? "locked" : ""}"
          type="button"
          data-stage="${index}"
          ${locked ? "disabled" : ""}>
          <span class="stage-number">${done ? "OK" : index + 1}</span>
          <span>
            <span class="stage-name">${stage.name}</span>
            <span class="stage-desc">${stage.short}</span>
          </span>
        </button>
      `;
    })
    .join("");

  document.querySelectorAll(".stage-button").forEach((button) => {
    button.addEventListener("click", () => {
      state.current = Number(button.dataset.stage);
      render();
    });
  });
}

function dataTable(headers, bodyRows) {
  return `
    <div class="table-scroll">
      <table class="data-table">
        <thead>
          <tr>${headers.map((header) => `<th>${header}</th>`).join("")}</tr>
        </thead>
        <tbody>
          ${bodyRows
            .map(
              (row) =>
                `<tr>${row.map((cell) => `<td>${cell}</td>`).join("")}</tr>`,
            )
            .join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderDatasetPreview() {
  datasetPreview.innerHTML = dataTable(
    ["evaluator", "scenario", "model", "score", "feedback"],
    rows,
  );
  rowMetric.textContent = rows.length;
  evaluatorMetric.textContent = new Set(rows.map(([evaluator]) => evaluator)).size;
  scenarioMetric.textContent = new Set(rows.map(([, scenario]) => scenario)).size;
  modelMetric.textContent = new Set(rows.map(([, , model]) => model)).size;
  rowCount.textContent = `${rows.length} rows`;
}

function barList(scores, includeInterval = false) {
  const max = 7;
  return `
    <div class="bar-list">
      ${scores
        .map(([model, score, interval]) => {
          const width = Math.max(3, (score / max) * 100);
          return `
            <div class="bar-row">
              <strong>${model}</strong>
              <div class="bar-track"><div class="bar-fill" style="width:${width}%"></div></div>
              <span class="bar-value">${score.toFixed(2)}</span>
              ${includeInterval ? `<span class="mini-copy">95% range: ${interval}</span>` : ""}
            </div>
          `;
        })
        .join("")}
    </div>
  `;
}

function renderEvidence(index) {
  if (index === 0) {
    return `
      <div class="evidence-box">
        <h3>先找出重複出現的單位</h3>
        <p class="mini-copy">資料表已經放在頁面最上方。這裡把重複次數整理出來，請觀察它是否符合「每列彼此獨立」的假設。</p>
      </div>
      ${dataTable(
        ["重複單位", "預覽中出現次數", "分析含意"],
        [
          ["E01 / E02 / E03", "各 2 次", "同一評分者的給分可能相關"],
          ["S01 / S02 / S04", "各 2 次", "同一情境下的結果可能相關"],
          ["model", "跨評分者與情境", "要控制前兩者後再比較"],
        ],
      )}
    `;
  }

  if (index === 1) {
    return `
      <div class="evidence-box">
        <h3>普通平均分</h3>
        <p class="mini-copy">這是最直覺的起點，但還沒有扣除誰比較嚴格、哪題比較難。</p>
      </div>
      ${barList(rawScores)}
    `;
  }

  if (index === 2) {
    return `
      <div class="evidence-box">
        <h3>階層式迴歸的直覺</h3>
        <p class="mini-copy">一句話：把個體放在所屬的環境背景中一起分析。這裡的個體是每一筆評分，背景是評分者與學習情境。</p>
      </div>
      <div class="layer-stack" aria-label="Hierarchical data layers">
        <div class="layer-card">
          <span class="layer-label">第 1 層：單筆評分</span>
          <strong>某位專家對某模型在某情境下給出的 score</strong>
          <p class="mini-copy">這是資料表中的每一列，也是模型最後要解釋的結果。</p>
        </div>
        <div class="layer-card">
          <span class="layer-label">第 2 層：評分者背景</span>
          <strong>E01、E02、E03 可能有各自的寬鬆或嚴格程度</strong>
          <p class="mini-copy">同一位評分者給出的分數會彼此相關，不能假裝完全獨立。</p>
        </div>
        <div class="layer-card">
          <span class="layer-label">第 3 層：scenario 背景</span>
          <strong>S01、S02、S04 可能有不同的任務難度</strong>
          <p class="mini-copy">同一個情境下的模型比較，會受到題目本身難易度影響。</p>
        </div>
      </div>
      <div class="comparison-grid">
        <div class="mini-card">
          <strong>評分者效果</strong>
          <p class="mini-copy">E03 平均給分偏低。這可能代表模型差，也可能代表 E03 本來就嚴格。</p>
        </div>
        <div class="mini-card">
          <strong>Scenario 效果</strong>
          <p class="mini-copy">S04 平均分偏低。這可能代表該任務本來就比較難教。</p>
        </div>
      </div>
      ${dataTable(
        ["分析層次", "例子", "如果不控制會怎樣"],
        [
          ["evaluator", "E03 is strict", "把嚴格評分誤認成模型很差"],
          ["scenario", "S04 is hard", "把難題誤認成模型很差"],
          ["model", "LearnLM", "沒有扣掉背景差異就下結論"],
        ],
      )}
    `;
  }

  if (index === 3) {
    return `
      <div class="evidence-box">
        <h3>簡化版階層模型公式</h3>
        <p class="mini-copy">這不是要你硬背公式，而是看懂研究者如何把一個分數拆成不同來源。</p>
        <div class="formula">
          \\[
            \\operatorname{score}_{ijm}
            = \\mu
            + \\beta_{\\text{model}[m]}
            + u_{\\text{evaluator}[i]}
            + v_{\\text{scenario}[j]}
            + \\varepsilon_{ijm}
          \\]
        </div>
      </div>
      <div class="formula-parts">
        <div class="formula-part target">
          <span>\\(\\beta_{\\text{model}[m]}\\)</span>
          <strong>模型效果</strong>
          <p class="mini-copy">這才是主角：扣掉評分者與題目差異後，某模型的教學品質估計。</p>
        </div>
        <div class="formula-part">
          <span>\\(\\mu\\)</span>
          <strong>整體平均</strong>
          <p class="mini-copy">所有資料共同的基準分數。</p>
        </div>
        <div class="formula-part">
          <span>\\(u_{\\text{evaluator}[i]}\\)</span>
          <strong>評分者偏差</strong>
          <p class="mini-copy">某位評分者本來偏寬鬆或偏嚴格。</p>
        </div>
        <div class="formula-part">
          <span>\\(v_{\\text{scenario}[j]}\\)</span>
          <strong>情境難度</strong>
          <p class="mini-copy">某個學習任務本來比較容易或困難。</p>
        </div>
        <div class="formula-part">
          <span>\\(\\varepsilon_{ijm}\\)</span>
          <strong>隨機誤差</strong>
          <p class="mini-copy">模型無法完全解釋的剩餘波動。</p>
        </div>
      </div>
      <div class="evidence-box">
        <h3>研究判斷</h3>
        <p class="mini-copy">普通平均問的是「誰分數最高？」階層式迴歸問的是「扣掉評分者與題目背景後，誰的模型效果較高？」</p>
      </div>
      ${barList(adjustedScores, true)}
    `;
  }

  if (index === 4) {
    return `
      <div class="evidence-box">
        <h3>貝氏統計的更新流程</h3>
        <p class="mini-copy">一句話：舊經驗 + 新數據 = 更新後的判斷。這裡的判斷不是單一答案，而是一組可能的模型效果分布。</p>
      </div>
      <div class="bayes-flow" aria-label="Bayesian update flow">
        <div class="bayes-step">
          <span>Prior</span>
          <strong>先驗信念</strong>
          <p class="mini-copy">分析前對模型效果的合理預期，例如效果通常不會無限大或無限小。</p>
        </div>
        <div class="flow-arrow">+</div>
        <div class="bayes-step">
          <span>Likelihood</span>
          <strong>新證據</strong>
          <p class="mini-copy">目前看到的專家評分資料，以及它在階層模型下有多合理。</p>
        </div>
        <div class="flow-arrow">=</div>
        <div class="bayes-step result">
          <span>Posterior</span>
          <strong>後驗判斷</strong>
          <p class="mini-copy">結合先驗與資料後，得到模型效果可能落在哪些範圍。</p>
        </div>
      </div>
      <div class="evidence-box">
        <h3>posterior mean 與 95% HDI 怎麼讀</h3>
        <p class="mini-copy">posterior mean 是更新後分布的中心估計；95% HDI 是最可信的一段範圍。範圍越寬，代表資料還不足以讓我們很確定。</p>
      </div>
      ${dataTable(
        ["model", "posterior mean", "95% HDI / uncertainty range"],
        adjustedScores.map(([model, score, interval]) => [model, score.toFixed(2), interval]),
      )}
    `;
  }

  return `
    <div class="evidence-box">
      <h3>Codebook 主題計數</h3>
      <p class="mini-copy">質化分析把文字回饋轉成主題標籤，讓研究人員知道分數背後的原因。</p>
    </div>
    <div class="chip-row">
      ${themeCounts
        .map(
          ([theme, model, count, tone]) =>
            `<span class="chip ${tone}">${theme} | ${model}: ${count}</span>`,
        )
        .join("")}
    </div>
    ${dataTable(
      ["feedback text", "coded theme"],
      [
        ["It asked questions and helped the learner reason.", "challenges_learner"],
        ["It broke the explanation into manageable steps.", "step_by_step"],
        ["It gave the final answer too quickly.", "gives_away_answers"],
      ],
    )}
  `;
}

function renderTask(stage, index) {
  return `
    <div class="task-box">
      <h3>${stage.taskTitle}</h3>
      <p class="mini-copy">${stage.question}</p>
      <div class="choices">
        ${stage.choices
          .map(
            (choice, choiceIndex) =>
              `<button class="choice ${
                state.answered[index] && choiceIndex === stage.correct ? "selected" : ""
              }" type="button" data-choice="${choiceIndex}" ${
                state.answered[index] ? "disabled" : ""
              }>${choice}</button>`,
          )
          .join("")}
      </div>
    </div>
    <div class="task-box">
      <div class="answer-status" id="answerStatus">${
        state.answered[index] ? "Completed" : "Choose an answer to complete this stage"
      }</div>
      <p class="hint" id="answerHint">${
        state.answered[index]
          ? stage.correctText
          : "每一關都對應 3.4 的一個分析決策。先做判斷，再看下一關怎麼延伸。"
      }</p>
    </div>
  `;
}

function bindChoices(stage, index) {
  document.querySelectorAll(".choice").forEach((button) => {
    button.addEventListener("click", () => {
      const choice = Number(button.dataset.choice);
      const status = document.querySelector("#answerStatus");
      const hint = document.querySelector("#answerHint");
      document.querySelectorAll(".choice").forEach((node) => {
        node.classList.remove("selected");
      });
      button.classList.add("selected");

      if (choice === stage.correct) {
        state.answered[index] = true;
        state.maxUnlocked = Math.max(state.maxUnlocked, index + 1);
        status.textContent = "Correct";
        status.classList.add("correct");
        hint.textContent = stage.correctText;
        nextButton.disabled = false;
        renderStageList();
      } else {
        status.textContent = "Try again";
        status.classList.remove("correct");
        hint.textContent = "這個選項沒有處理 3.4 真正在意的分析問題。再想想資料結構或研究目的。";
      }
    });
  });
}

function typesetMath() {
  if (!window.MathJax) return;

  const targets = [evidencePanel, taskPanel].filter(Boolean);
  const runTypeset = () => {
    if (window.MathJax.typesetPromise) {
      window.MathJax.typesetPromise(targets).catch(() => {});
    }
  };

  if (window.MathJax.startup?.promise) {
    window.MathJax.startup.promise.then(runTypeset);
  } else {
    runTypeset();
  }
}

function render() {
  const stage = stages[state.current];
  stageEyebrow.textContent = `Stage ${state.current + 1}`;
  stageTitle.textContent = stage.title;
  stageBrief.textContent = stage.brief;
  taskPanel.innerHTML = renderTask(stage, state.current);
  evidencePanel.innerHTML = renderEvidence(state.current);

  const progress = ((state.current + 1) / stages.length) * 100;
  progressFill.style.width = `${progress}%`;
  progressText.textContent = `${state.current + 1} / ${stages.length}`;

  backButton.disabled = state.current === 0;
  nextButton.disabled = !state.answered[state.current];
  nextButton.textContent =
    state.current === stages.length - 1 ? "Finish Pipeline" : "Next Stage";

  renderStageList();
  bindChoices(stage, state.current);
  typesetMath();
}

backButton.addEventListener("click", () => {
  state.current = Math.max(0, state.current - 1);
  render();
});

nextButton.addEventListener("click", () => {
  if (!state.answered[state.current]) return;
  if (state.current < stages.length - 1) {
    state.current += 1;
    state.maxUnlocked = Math.max(state.maxUnlocked, state.current);
    render();
  } else {
    taskPanel.innerHTML = `
      <div class="task-box">
        <h3>Pipeline complete</h3>
        <p class="mini-copy">
          你已經走完 3.4 的完整分析邏輯：資料收集、平均分初看、處理 repeated measurements、
          調整模型效果、報告不確定性、編碼文字回饋。
        </p>
      </div>
    `;
    nextButton.disabled = true;
  }
});

startAnalysisButton.addEventListener("click", () => {
  analysisGuide.scrollIntoView({ behavior: "smooth", block: "start" });
});

renderDatasetPreview();
render();
