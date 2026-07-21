const LEARNER_ID = "demo_student";

document.addEventListener("DOMContentLoaded", async () => {
    const chatHistory = document.getElementById("chat-history");
    const chatForm = document.getElementById("chat-form");
    const chatInput = document.getElementById("chat-input");
    const treeContainer = document.getElementById("tree");
    const modeSelect = document.getElementById("mode-select");
    const phaseDisplay = document.getElementById("phase-display");
    const topicDisplay = document.getElementById("topic-display");
    const planSourceDisplay = document.getElementById("plan-source-display");
    const edfStateDisplay = document.getElementById("edf-state-display");
    const edfPolicyDisplay = document.getElementById("edf-policy-display");
    const evidenceCountDisplay = document.getElementById("evidence-count-display");
    const contextCountDisplay = document.getElementById("context-count-display");
    const currentActivityCard = document.getElementById("current-activity-card");
    const currentActivityLabel = document.getElementById("current-activity-label");
    const activityStatusDot = document.getElementById("activity-status-dot");
    const activityBadges = document.getElementById("activity-badges");
    const resetBtn = document.getElementById("reset-btn");
    const loadingUI = document.getElementById("loading");
    let lastActivityKey = "";

    // Initialize
    startSession();

    chatForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const text = chatInput.value.trim();
        if (!text) return;

        appendMessage(text, "student");
        chatInput.value = "";
        
        showLoading(true);
        renderPendingActivity("正在分析教學決策", "respond");
        try {
            const res = await fetch("/api/respond", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ learner_id: LEARNER_ID, answer: text })
            });
            const data = await res.json();
            handleResponse(data);
        } catch (err) {
            appendMessage("系統錯誤：" + err.message, "teacher");
            renderActivityStatus({ code: "error", label: "系統錯誤", status: "idle", detail: "request_failed" }, []);
        } finally {
            showLoading(false);
        }
    });

    resetBtn.addEventListener("click", async () => {
        chatInput.disabled = true;
        const messages = chatHistory.querySelectorAll('.message');
        messages.forEach(m => m.remove());
        showLoading(true);
        renderPendingActivity("正在重置學習狀態", "reset");
        try {
            const res = await fetch("/api/reset", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ learner_id: LEARNER_ID }) // no curriculum_id means fallback to onboarding
            });
            const data = await res.json();
            handleResponse(data);
        } catch(err) {
            console.error(err);
        } finally {
            showLoading(false);
            chatInput.disabled = false;
            chatInput.focus();
        }
    });

    modeSelect.addEventListener("change", async (e) => {
        const newMode = e.target.value;
        try {
            renderPendingActivity("正在切換教學模式", "mode");
            const res = await fetch("/api/mode", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ learner_id: LEARNER_ID, mode: newMode })
            });
            if (!res.ok) {
                const error = await res.json();
                alert(error.detail || "無法切換模式");
                // Revert select visually
                modeSelect.value = newMode === "llm" ? "rule" : "llm";
                return;
            }
            const data = await res.json();
            handleResponse(data);
        } catch(err) {
            console.error(err);
        }
    });




    async function startSession() {
        showLoading(true);
        renderPendingActivity("正在載入學習引擎", "start");
        try {
            const res = await fetch("/api/start", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ learner_id: LEARNER_ID })
            });
            const data = await res.json();
            if (data.mode) {
                modeSelect.value = data.mode;
            }
            handleResponse(data);
        } catch(err) {
            appendMessage("無法連線至伺服器。", "teacher");
        } finally {
            showLoading(false);
        }
    }

    function handleResponse(data) {
        if (data.message) {
            appendMessage(data.message, "teacher", data.state_changes);
        }
        if (data.tree) {
            renderTree(data.tree, data.node_id);
        }
        if (data.mode) {
            modeSelect.value = data.mode;
        }
        if (data.learning) {
            phaseDisplay.textContent = data.learning.phase;
            topicDisplay.textContent = data.learning.topic || "--";
            planSourceDisplay.textContent = data.learning.plan_source;
            edfStateDisplay.textContent = data.learning.edf_state;
            edfPolicyDisplay.textContent = data.learning.edf_policy;
            evidenceCountDisplay.textContent = data.learning.evidence_count;
            contextCountDisplay.textContent = data.learning.context_count;
            renderActivityStatus(data.learning.current_activity, data.learning.activity_steps || []);
            
            if (data.learning.phase === "onboarding") {
                chatInput.placeholder = "請輸入您想學習的主題或困難點...";
            } else {
                chatInput.placeholder = "請輸入您的答案...";
            }
        }
    }

    function renderActivityStatus(currentActivity, steps) {
        const activity = currentActivity || { code: "idle", label: "等待學習主題", status: "idle", detail: "" };
        const key = `${activity.code}:${activity.status}:${activity.detail}`;
        currentActivityLabel.textContent = activity.label || activityLabel(activity.code);
        activityStatusDot.className = `activity-dot ${activity.status || "done"}`;
        if (key !== lastActivityKey) {
            currentActivityCard.classList.remove("flip");
            void currentActivityCard.offsetWidth;
            currentActivityCard.classList.add("flip");
            lastActivityKey = key;
        }

        activityBadges.innerHTML = "";
        const displaySteps = steps.length > 0 ? steps : [activity];
        displaySteps.slice(-6).forEach(step => {
            const badge = document.createElement("div");
            badge.className = `activity-badge ${step.status || "done"}`;

            const name = document.createElement("span");
            name.className = "activity-badge-label";
            name.textContent = step.label || activityLabel(step.code);

            const detail = document.createElement("span");
            detail.className = "activity-badge-detail";
            detail.textContent = step.detail || step.code || "--";

            badge.appendChild(name);
            badge.appendChild(detail);
            activityBadges.appendChild(badge);
        });
    }

    function renderPendingActivity(label, detail) {
        const pending = {
            code: "processing",
            label,
            status: "processing",
            detail
        };
        renderActivityStatus(pending, [
            pending,
            { code: "engine_processing", label: "等待後端決策", status: "processing", detail: "skill/edf/gum" }
        ]);
    }

    function activityLabel(code) {
        const labels = {
            idle: "等待學習主題",
            intake_topic: "接收學習主題",
            domain_resolved: "判斷學習領域",
            intent_detected: "判斷學習方向",
            level_detected: "判斷目前程度",
            skill_loaded: "載入領域 Skill",
            skill_validated: "驗證 Skill 規則",
            plan_compiled: "編譯學習路徑",
            diagnostic_selected: "選擇診斷概念",
            response_classified: "分類學習者回應",
            evidence_applied: "更新概念掌握狀態",
            scope_mismatch: "偵測題目層級不合",
            scaffold_selected: "選擇前置概念補架",
            acceleration_selected: "加快學習節奏",
            memory_updated: "保存直接學習證據",
            edf_evaluated: "更新 EDF 教學策略",
            tutoring_started: "進入教學引導",
            processing: "系統處理中",
            engine_processing: "等待後端決策",
            error: "系統錯誤"
        };
        return labels[code] || "系統處理中";
    }

    function appendMessage(text, role, stateChanges = null) {
        const div = document.createElement("div");
        div.className = `message ${role}`;
        
        // Handle newlines securely
        const lines = text.split("\n");
        lines.forEach((line, index) => {
            const span = document.createElement("span");
            span.textContent = line;
            div.appendChild(span);
            if (index < lines.length - 1) {
                div.appendChild(document.createElement("br"));
            }
        });
        
        // Add state changes if any
        if (stateChanges && stateChanges.length > 0) {
            const stateDiv = document.createElement("div");
            stateDiv.className = "state-changes";
            
            const strong = document.createElement("strong");
            strong.textContent = "狀態更新紀錄：";
            stateDiv.appendChild(strong);
            
            const ul = document.createElement("ul");
            stateChanges.forEach(sc => {
                const li = document.createElement("li");
                li.textContent = sc;
                ul.appendChild(li);
            });
            stateDiv.appendChild(ul);
            div.appendChild(stateDiv);
        }
        
        chatHistory.appendChild(div);
        chatHistory.scrollTop = chatHistory.scrollHeight;
    }

    function renderTree(nodes, currentNodeId) {
        treeContainer.innerHTML = "";
        nodes.forEach(node => {
            const el = document.createElement("div");
            el.className = `tree-node ${node.status}`;
            if (node.id === currentNodeId) {
                el.classList.add("active");
            }
            
            const label = document.createElement("span");
            label.className = "label";
            label.style.paddingLeft = node.prerequisites.length > 0 ? "16px" : "0";
            label.textContent = (node.prerequisites.length > 0 ? "↳ " : "") + node.label;

            const status = document.createElement("span");
            status.className = "status";
            
            let icon = "⚪";
            let statusText = "未診斷";
            if (node.status === "mastered") { icon = "✅"; statusText = "掌握"; }
            else if (node.status === "not_mastered") { icon = "❌"; statusText = "未掌握"; }
            
            status.textContent = `${icon} ${statusText}`;

            el.appendChild(label);
            el.appendChild(status);
            treeContainer.appendChild(el);
        });
    }

    function showLoading(show) {
        if (show) {
            loadingUI.classList.remove("hidden");
            chatHistory.appendChild(loadingUI); // Move to bottom
            chatHistory.scrollTop = chatHistory.scrollHeight;
        } else {
            loadingUI.classList.add("hidden");
        }
    }
});
