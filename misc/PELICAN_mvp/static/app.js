const LEARNER_ID = new URLSearchParams(window.location.search).get("learner_id") || "demo_student";

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
    const methodologyStages = document.getElementById("methodology-stages");
    const skillArtifactSummary = document.getElementById("skill-artifact-summary");
    const methodologySubsystemEvents = document.getElementById("methodology-subsystem-events");
    const agentExecutorTrace = document.getElementById("agent-executor-trace");
    const agentProposals = document.getElementById("agent-proposals");
    const tutorProposalTrace = document.getElementById("tutor-proposal-trace");
    const learnerProgressSnapshot = document.getElementById("learner-progress-snapshot");
    const resetBtn = document.getElementById("reset-btn");
    const exportBtn = document.getElementById("export-btn");
    const loadingUI = document.getElementById("loading");
    const loadingProgressTitle = document.getElementById("loading-progress-title");
    const loadingProgressSteps = document.getElementById("loading-progress-steps");
    let lastActivityKey = "";
    let progressPollTimer = null;
    let progressPollStartedAt = 0;
    let latestProgressSequence = 0;

    // Initialize
    startSession();

    chatForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const text = chatInput.value.trim();
        if (!text) return;

        appendMessage(text, "student");
        chatInput.value = "";
        
        showLoading(true);
        startProgressPolling();
        renderPendingActivity("正在分析教學決策", "respond");
        try {
            const res = await fetch("/api/respond", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ learner_id: LEARNER_ID, answer: text })
            });
            const data = await readJsonResponse(res, "回覆失敗");
            handleResponse(data);
        } catch (err) {
            appendMessage("系統錯誤：" + err.message, "teacher");
            renderActivityStatus({ code: "error", label: "系統錯誤", status: "idle", detail: "request_failed" }, []);
        } finally {
            stopProgressPolling();
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
            const data = await readJsonResponse(res, "重置失敗");
            handleResponse(data);
        } catch(err) {
            appendMessage("重置失敗：" + err.message, "teacher");
            renderActivityStatus({ code: "error", label: "系統錯誤", status: "idle", detail: "reset_failed" }, []);
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

    exportBtn.addEventListener("click", async () => {
        exportBtn.disabled = true;
        renderPendingActivity("正在匯出對話紀錄", "export");
        try {
            const res = await fetch(`/api/export?learner_id=${encodeURIComponent(LEARNER_ID)}`);
            if (!res.ok) {
                throw new Error("匯出失敗");
            }
            const blob = await res.blob();
            const url = URL.createObjectURL(blob);
            const link = document.createElement("a");
            link.href = url;
            link.download = `pelican_${LEARNER_ID}.md`;
            document.body.appendChild(link);
            link.click();
            link.remove();
            URL.revokeObjectURL(url);
            renderActivityStatus(
                { code: "exported", label: "已匯出對話紀錄", status: "done", detail: "markdown" },
                [{ code: "exported", label: "已匯出對話紀錄", status: "done", detail: "markdown" }]
            );
        } catch (err) {
            appendMessage("匯出失敗：" + err.message, "teacher");
            renderActivityStatus({ code: "error", label: "系統錯誤", status: "idle", detail: "export_failed" }, []);
        } finally {
            exportBtn.disabled = false;
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
            const data = await readJsonResponse(res, "啟動失敗");
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

    async function readJsonResponse(res, fallbackMessage) {
        let data = {};
        try {
            data = await res.json();
        } catch (err) {
            if (res.ok) {
                throw err;
            }
        }
        if (!res.ok) {
            throw new Error(data.detail || fallbackMessage);
        }
        return data;
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
            renderMethodologyStages(
                data.learning.methodology_events || [],
                data.learning.methodology_stages || [],
                data.learning.current_cycle_id || null
            );
            renderSkillArtifactSummary(data.learning.skill_artifact_summary || null);
            renderSubsystemEvents(data.learning.methodology_events || [], data.learning.current_cycle_id || null);
            renderAgentExecutorTrace(data.learning.agent_executor_trace || []);
            renderAgentProposals(data.learning.agent_proposals || []);
            renderTutorProposalTrace(data.learning.tutor_proposal_trace || []);
            renderLearnerProgress(data.learning.progress_snapshot || null);
            
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
            request_queued: "等待後端接收",
            request_received: "收到學習回覆",
            intake_topic: "接收學習主題",
            domain_resolved: "判斷學習領域",
            intent_detected: "判斷學習方向",
            level_detected: "判斷目前程度",
            skill_generation: "建立領域 Skill",
            skill_validation: "驗證 Skill 結構",
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
            complete: "完成教學回覆",
            exported: "已匯出對話紀錄",
            error: "系統錯誤"
        };
        return labels[code] || "系統處理中";
    }

    function startProgressPolling() {
        stopProgressPolling();
        progressPollStartedAt = Date.now();
        latestProgressSequence = 0;
        renderLoadingProgress([
            {
                code: "request_queued",
                label: "等待後端接收",
                status: "processing",
                detail: "polling"
            }
        ]);
        fetchRuntimeProgress();
        progressPollTimer = window.setInterval(fetchRuntimeProgress, 800);
    }

    function stopProgressPolling() {
        if (progressPollTimer) {
            window.clearInterval(progressPollTimer);
            progressPollTimer = null;
        }
    }

    async function fetchRuntimeProgress() {
        try {
            const res = await fetch(`/api/progress?learner_id=${encodeURIComponent(LEARNER_ID)}`, {
                cache: "no-store"
            });
            if (!res.ok) return;
            const data = await res.json();
            const events = Array.isArray(data.events)
                ? data.events.filter(event => {
                    const eventTime = Date.parse(event.timestamp || "");
                    return Number.isNaN(eventTime) || eventTime >= progressPollStartedAt;
                })
                : [];
            if (events.length === 0) return;
            renderLoadingProgress(events);
            const latest = events[events.length - 1];
            if ((latest.sequence || 0) > latestProgressSequence) {
                latestProgressSequence = latest.sequence || latestProgressSequence;
                renderActivityStatus(latest, events);
            }
        } catch (err) {
            // Polling is best-effort; the final /api/respond response remains
            // the authoritative state update for the chat.
            console.debug("Progress polling skipped", err);
        }
    }

    function renderLoadingProgress(events) {
        const displayEvents = events.slice(-5);
        const latest = displayEvents[displayEvents.length - 1] || {
            code: "processing",
            label: "正在處理",
            status: "processing",
            detail: ""
        };
        loadingProgressTitle.textContent = latest.label || activityLabel(latest.code);
        loadingProgressSteps.innerHTML = "";
        displayEvents.forEach(event => {
            const row = document.createElement("div");
            row.className = `loading-progress-step ${event.status || "processing"}`;

            const marker = document.createElement("span");
            marker.className = "loading-progress-marker";

            const label = document.createElement("span");
            label.className = "loading-progress-label";
            label.textContent = event.label || activityLabel(event.code);

            const detail = document.createElement("span");
            detail.className = "loading-progress-detail";
            detail.textContent = event.detail || event.code || "--";

            row.appendChild(marker);
            row.appendChild(label);
            row.appendChild(detail);
            loadingProgressSteps.appendChild(row);
        });
    }

    function stageLabel(stage) {
        const labels = {
            goal_framing: "Goal",
            skill_construction: "Skill",
            cognitive_diagnosis: "Diagnosis",
            knowledge_state_update: "State",
            edf_strategy_selection: "EDF",
            tutor_response: "Tutor"
        };
        return labels[stage] || stage || "--";
    }

    function renderMethodologyStages(events, stages, currentCycleId) {
        methodologyStages.innerHTML = "";
        const currentEvents = events.filter(event => !currentCycleId || event.cycle_id === currentCycleId);
        stages.forEach(stage => {
            const stageEvents = currentEvents.filter(event => event.event_type === "pipeline_stage" && event.stage === stage);
            const latest = stageEvents[stageEvents.length - 1];
            const item = document.createElement("div");
            item.className = `methodology-stage ${latest ? latest.status || "completed" : "pending"}`;

            const name = document.createElement("span");
            name.className = "methodology-stage-name";
            name.textContent = stageLabel(stage);

            const detail = document.createElement("span");
            detail.className = "methodology-stage-detail";
            detail.textContent = latest ? latest.reason_code || latest.status || "completed" : "pending";

            item.appendChild(name);
            item.appendChild(detail);
            methodologyStages.appendChild(item);
        });
    }

    function renderSubsystemEvents(events, currentCycleId) {
        methodologySubsystemEvents.innerHTML = "";
        appendListTitle(methodologySubsystemEvents, "Subsystem");
        const subsystem = events
            .filter(event => (!currentCycleId || event.cycle_id === currentCycleId) && event.event_type !== "pipeline_stage")
            .slice(-4);
        if (subsystem.length === 0) {
            appendEmptyLine(methodologySubsystemEvents, "No subsystem events");
            return;
        }
        subsystem.forEach(event => {
            const row = document.createElement("div");
            row.className = "methodology-row";
            row.textContent = `${event.event_type}: ${event.reason_code || event.status || "recorded"}`;
            methodologySubsystemEvents.appendChild(row);
        });
    }

    function renderAgentProposals(proposals) {
        agentProposals.innerHTML = "";
        appendListTitle(agentProposals, "Agent Proposals");
        const recent = proposals.slice(-5);
        if (recent.length === 0) {
            appendEmptyLine(agentProposals, "No proposals");
            return;
        }
        recent.forEach(proposal => {
            const row = document.createElement("div");
            row.className = "methodology-row";
            const move = proposal.pedagogical_move ? ` / ${proposal.pedagogical_move}` : "";
            row.textContent = `${proposal.role}: ${proposal.validation_status}${move} / ${proposal.reason_code || "recorded"}`;
            agentProposals.appendChild(row);
        });
    }

    function renderAgentExecutorTrace(rows) {
        agentExecutorTrace.innerHTML = "";
        appendListTitle(agentExecutorTrace, "Agent Executor Trace");
        const recent = rows.slice(-6);
        if (recent.length === 0) {
            appendEmptyLine(agentExecutorTrace, "No executor trace");
            return;
        }
        recent.forEach(row => {
            const item = document.createElement("div");
            item.className = "executor-trace-row";

            const head = document.createElement("div");
            head.className = "executor-trace-head";
            head.textContent = `${row.role || "--"} · ${row.validation_status || "--"} · ${row.reason_code || "recorded"}`;

            const artifact = row.proposal_artifact || {};
            const inputRef = row.input_ref || {};
            const outputRef = row.adopted_output_ref || {};
            const detail = document.createElement("div");
            detail.className = "executor-trace-detail";
            detail.textContent = `input: ${inputRef.label || inputRef.ref_type || "--"} → artifact: ${artifact.artifact_type || "--"} → adopted: ${outputRef.label || "--"}`;

            const effect = document.createElement("div");
            effect.className = "executor-trace-effect";
            effect.textContent = row.final_effect || artifact.display_summary || "--";

            item.appendChild(head);
            item.appendChild(detail);
            item.appendChild(effect);
            agentExecutorTrace.appendChild(item);
        });
    }

    function renderSkillArtifactSummary(summary) {
        skillArtifactSummary.innerHTML = "";
        appendListTitle(skillArtifactSummary, "Skill Artifact");
        if (!summary) {
            appendEmptyLine(skillArtifactSummary, "No skill artifact yet");
            return;
        }
        const identity = document.createElement("div");
        identity.className = "methodology-row";
        identity.textContent = `${summary.skill_id || "--"} / ${summary.domain_category || "--"}`;
        skillArtifactSummary.appendChild(identity);

        const target = summary.current_diagnostic_target;
        const targetRow = document.createElement("div");
        targetRow.className = "methodology-row";
        targetRow.textContent = target ? `Target: ${target.label}` : "Target: --";
        skillArtifactSummary.appendChild(targetRow);

        const concepts = Array.isArray(summary.concept_path) ? summary.concept_path : [];
        const pathRow = document.createElement("div");
        pathRow.className = "methodology-row wrap";
        pathRow.textContent = concepts.slice(0, 4).map(concept => concept.active ? `→ ${concept.label}` : concept.label).join(" · ") || "No concept path";
        skillArtifactSummary.appendChild(pathRow);
    }

    function renderTutorProposalTrace(proposals) {
        tutorProposalTrace.innerHTML = "";
        appendListTitle(tutorProposalTrace, "Tutor Proposal Trace");
        const recent = proposals.slice(-4);
        if (recent.length === 0) {
            appendEmptyLine(tutorProposalTrace, "No tutor proposals");
            return;
        }
        recent.forEach(proposal => {
            const row = document.createElement("div");
            row.className = "methodology-row wrap";
            row.textContent = `${proposal.validation_status}: ${proposal.pedagogical_move || proposal.strategy || "--"} → ${proposal.display_summary || proposal.reason_code || "recorded"}`;
            tutorProposalTrace.appendChild(row);
        });
    }

    function renderLearnerProgress(snapshot) {
        learnerProgressSnapshot.innerHTML = "";
        appendListTitle(learnerProgressSnapshot, "Progress");
        const nodes = snapshot && Array.isArray(snapshot.nodes) ? snapshot.nodes : [];
        const visible = nodes.filter(node => node.status !== "undiagnosed").slice(0, 4);
        if (visible.length === 0) {
            appendEmptyLine(learnerProgressSnapshot, "No progress yet");
            return;
        }
        visible.forEach(node => {
            const row = document.createElement("div");
            row.className = "methodology-row";
            const confidence = Math.round((node.confidence || 0) * 100);
            row.textContent = `${node.label}: ${node.status} (${confidence}%)`;
            learnerProgressSnapshot.appendChild(row);
        });
    }

    function appendListTitle(container, text) {
        const title = document.createElement("div");
        title.className = "methodology-list-title";
        title.textContent = text;
        container.appendChild(title);
    }

    function appendEmptyLine(container, text) {
        const row = document.createElement("div");
        row.className = "methodology-row empty";
        row.textContent = text;
        container.appendChild(row);
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
            else if (node.status === "inferred_mastered") { icon = "◐"; statusText = "推定掌握"; }
            else if (node.status === "partially_mastered") { icon = "◑"; statusText = "部分掌握"; }
            else if (node.status === "fragile") { icon = "△"; statusText = "不穩定"; }
            
            status.textContent = `${icon} ${statusText}`;

            el.appendChild(label);
            el.appendChild(status);
            treeContainer.appendChild(el);
        });
    }

    function showLoading(show) {
        if (show) {
            loadingUI.classList.remove("hidden");
            renderLoadingProgress([
                {
                    code: "processing",
                    label: "正在處理",
                    status: "processing",
                    detail: "request"
                }
            ]);
            chatHistory.appendChild(loadingUI); // Move to bottom
            chatHistory.scrollTop = chatHistory.scrollHeight;
        } else {
            loadingUI.classList.add("hidden");
        }
    }
});
