const LEARNER_ID = "demo_student";

document.addEventListener("DOMContentLoaded", async () => {
    const chatHistory = document.getElementById("chat-history");
    const chatForm = document.getElementById("chat-form");
    const chatInput = document.getElementById("chat-input");
    const treeContainer = document.getElementById("tree");
    const modeSelect = document.getElementById("mode-select");
    const curriculumSelect = document.getElementById("curriculum-select");
    const resetBtn = document.getElementById("reset-btn");
    const loadingUI = document.getElementById("loading");

    // Initialize
    await loadCurriculums();
    startSession();

    chatForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const text = chatInput.value.trim();
        if (!text) return;

        appendMessage(text, "student");
        chatInput.value = "";
        
        showLoading(true);
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
        } finally {
            showLoading(false);
        }
    });

    curriculumSelect.addEventListener("change", async (e) => {
        const newCurriculum = e.target.value;
        curriculumSelect.disabled = true;
        chatInput.disabled = true;
        
        const messages = chatHistory.querySelectorAll('.message');
        messages.forEach(m => m.remove());
        showLoading(true);
        try {
            const res = await fetch("/api/reset", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ learner_id: LEARNER_ID, curriculum_id: newCurriculum })
            });
            const data = await res.json();
            handleResponse(data);
        } catch(err) {
            console.error(err);
        } finally {
            showLoading(false);
            curriculumSelect.disabled = false;
            chatInput.disabled = false;
            chatInput.focus();
        }
    });

    modeSelect.addEventListener("change", async (e) => {
        const newMode = e.target.value;
        try {
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

    resetBtn.addEventListener("click", async () => {
        const messages = chatHistory.querySelectorAll('.message');
        messages.forEach(m => m.remove());
        showLoading(true);
        try {
            const res = await fetch("/api/reset", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ learner_id: LEARNER_ID })
            });
            const data = await res.json();
            handleResponse(data);
        } catch(err) {
            console.error(err);
        } finally {
            showLoading(false);
        }
    });

    async function loadCurriculums() {
        try {
            const res = await fetch("/api/curriculums");
            const curriculums = await res.json();
            curriculumSelect.innerHTML = "";
            for (const [key, name] of Object.entries(curriculums)) {
                const option = document.createElement("option");
                option.value = key;
                option.textContent = name;
                curriculumSelect.appendChild(option);
            }
        } catch(err) {
            console.error("無法載入課程列表:", err);
        }
    }

    async function startSession() {
        showLoading(true);
        try {
            const res = await fetch("/api/start", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ learner_id: LEARNER_ID })
            });
            const data = await res.json();
            modeSelect.value = data.mode;
            if (data.curriculum_id) {
                curriculumSelect.value = data.curriculum_id;
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
        if (data.curriculum_id && curriculumSelect.value !== data.curriculum_id) {
            curriculumSelect.value = data.curriculum_id;
        }
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
