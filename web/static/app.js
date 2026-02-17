// ========================================
//  Quiz Agent Platform — Frontend Logic
// ========================================

const chatArea = document.getElementById("chat-area");
const welcomeEl = document.getElementById("welcome");
const promptInput = document.getElementById("prompt-input");
const sendBtn = document.getElementById("send-btn");
const projectsList = document.getElementById("projects-list");

let isBuilding = false;
let runningProject = null; // Track which project's dev server is running

// ---- Initialize ----
document.addEventListener("DOMContentLoaded", () => {
    loadProjects();
    checkStatus();

    // Auto-resize textarea
    promptInput.addEventListener("input", () => {
        promptInput.style.height = "auto";
        promptInput.style.height = Math.min(promptInput.scrollHeight, 120) + "px";
    });

    // Send on Enter
    promptInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    });

    sendBtn.addEventListener("click", handleSend);

    // Quick prompts
    document.querySelectorAll(".quick-prompt").forEach((btn) => {
        btn.addEventListener("click", () => {
            promptInput.value = btn.dataset.prompt;
            promptInput.dispatchEvent(new Event("input"));
            handleSend();
        });
    });
});

// ---- Load existing projects ----
async function loadProjects() {
    // Check which project is currently running
    try {
        const runResp = await fetch("/api/running");
        const runData = await runResp.json();
        runningProject = runData.running ? runData.project : null;
    } catch {
        runningProject = null;
    }

    try {
        const resp = await fetch("/api/projects");
        const projects = await resp.json();
        if (projects.length === 0) {
            projectsList.innerHTML = '<p class="muted">No projects yet</p>';
        } else {
            projectsList.innerHTML = projects
                .map((p) => {
                    const isRunning = runningProject === p.name;
                    const btnClass = isRunning ? "project-run-btn running" : "project-run-btn";
                    const btnText = isRunning ? "Stop" : "Run";
                    return `
                <div class="project-item">
                    <span class="project-name" onclick="handleProjectClick('${p.name}')">${p.name}</span>
                    <div class="project-actions">
                        <span class="project-tech">${p.tech}</span>
                        <button class="${btnClass}" onclick="event.stopPropagation(); handleRunProject('${p.name}', this)" title="${isRunning ? 'Stop dev server' : 'Run dev server'}">${btnText}</button>
                    </div>
                </div>
            `;
                })
                .join("");
        }
    } catch {
        projectsList.innerHTML = '<p class="muted">Could not load projects</p>';
    }
}

// ---- Check integrations status ----
function checkStatus() {
    // These are set by the server based on env vars
    const figmaDot = document.getElementById("figma-status");
    const memoryDot = document.getElementById("memory-status");

    // Check if Figma is configured (we'll do a simple check via projects endpoint)
    fetch("/api/memory")
        .then((r) => r.json())
        .then((data) => {
            memoryDot.classList.add("active");
        })
        .catch(() => {});

    // We'll assume Figma is active if the page loads (server checks env)
    figmaDot.classList.add("active");
}

// ---- Handle clicking an existing project ----
function handleProjectClick(projectName) {
    promptInput.value = `I want to modify the existing project "${projectName}".`;
    promptInput.dispatchEvent(new Event("input"));
    promptInput.focus();
}

// ---- Send message ----
async function handleSend() {
    const prompt = promptInput.value.trim();
    if (!prompt || isBuilding) return;

    // Hide welcome
    if (welcomeEl) {
        welcomeEl.style.display = "none";
    }

    // Add user message
    addMessage("user", prompt);

    // Clear input
    promptInput.value = "";
    promptInput.style.height = "auto";

    // Disable input while building
    isBuilding = true;
    sendBtn.disabled = true;
    promptInput.disabled = true;

    // Add agent response placeholder with building indicator
    const agentMsg = addMessage("agent", null, true);

    try {
        // Start the build
        const resp = await fetch("/api/build", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ prompt }),
        });

        const { session_id, error } = await resp.json();
        if (error) {
            setMessageResult(agentMsg, error, true);
            return;
        }

        // Stream logs via SSE
        const eventSource = new EventSource(`/api/stream/${session_id}`);
        const logContainer = agentMsg.querySelector(".log-stream");

        const finishBuild = () => {
            isBuilding = false;
            sendBtn.disabled = false;
            promptInput.disabled = false;
            promptInput.focus();
        };

        eventSource.onmessage = (event) => {
            const data = JSON.parse(event.data);

            if (data.type === "log") {
                addLogLine(logContainer, data.message);
            } else if (data.type === "ask_user") {
                showAskUser(agentMsg, data.message, session_id);
            } else if (data.type === "result") {
                setMessageResult(agentMsg, data.message, false);
                eventSource.close();
                finishBuild();
                loadProjects();
            } else if (data.type === "stopped") {
                setMessageResult(agentMsg, data.message, false, true);
                eventSource.close();
                finishBuild();
                loadProjects();
            } else if (data.type === "error") {
                setMessageResult(agentMsg, data.message, true);
                eventSource.close();
                finishBuild();
            } else if (data.type === "done") {
                eventSource.close();
                finishBuild();
            }
        };

        eventSource.onerror = () => {
            eventSource.close();
            if (isBuilding) {
                setMessageResult(agentMsg, "Connection lost. Check the terminal for details.", true);
                finishBuild();
            }
        };
    } catch (err) {
        setMessageResult(agentMsg, `Failed to connect: ${err.message}`, true);
        isBuilding = false;
        sendBtn.disabled = false;
        promptInput.disabled = false;
    }
}

// ---- Add a message to chat ----
function addMessage(type, text, isStreaming = false) {
    const msg = document.createElement("div");
    msg.className = `message message-${type}`;

    const avatar = type === "user" ? "U" : "A";
    const label = type === "user" ? "You" : "Agent";

    if (type === "user") {
        msg.innerHTML = `
            <div class="message-header">
                <div class="message-avatar">${avatar}</div>
                <span class="message-label">${label}</span>
            </div>
            <div class="message-body">${escapeHtml(text)}</div>
        `;
    } else if (isStreaming) {
        msg.innerHTML = `
            <div class="message-header">
                <div class="message-avatar">${avatar}</div>
                <span class="message-label">${label}</span>
            </div>
            <div class="message-body">
                <div class="building-indicator">
                    <div class="spinner"></div>
                    <span class="building-text">Building your quiz app...</span>
                    <button class="stop-btn" onclick="handleStop(this)" title="Stop build">Stop</button>
                </div>
                <div class="log-stream"></div>
            </div>
        `;
    } else {
        msg.innerHTML = `
            <div class="message-header">
                <div class="message-avatar">${avatar}</div>
                <span class="message-label">${label}</span>
            </div>
            <div class="message-body">${escapeHtml(text)}</div>
        `;
    }

    chatArea.appendChild(msg);
    chatArea.scrollTop = chatArea.scrollHeight;
    return msg;
}

// ---- Add a log line to the stream ----
function addLogLine(container, text) {
    if (!container) return;

    const line = document.createElement("div");
    line.className = "log-line";

    // Colorize based on content
    if (text.includes("-> Tool:")) {
        line.classList.add("tool");
    } else if (text.includes("ERROR")) {
        line.classList.add("error");
    } else if (text.match(/\[(plan|generate|review|fix)\]/i)) {
        line.classList.add("phase");
    }

    line.textContent = text;
    container.appendChild(line);
    container.scrollTop = container.scrollHeight;

    // Also scroll the chat area
    chatArea.scrollTop = chatArea.scrollHeight;
}

// ---- Set the final result on an agent message ----
function setMessageResult(msgEl, result, isError, isStopped = false) {
    const body = msgEl.querySelector(".message-body");

    // Remove the building indicator
    const indicator = body.querySelector(".building-indicator");
    if (indicator) indicator.remove();

    // Add result card
    const card = document.createElement("div");
    card.className = "result-card";
    if (isError) {
        card.style.borderColor = "var(--error)";
        card.innerHTML = `<h4 style="color: var(--error)">Error</h4><pre>${escapeHtml(result)}</pre>`;
    } else if (isStopped) {
        card.style.borderColor = "var(--warning)";
        card.innerHTML = `<h4 style="color: var(--warning)">Build Stopped</h4><pre>${escapeHtml(result)}</pre>`;
    } else {
        card.innerHTML = `<h4>Build Complete</h4><pre>${escapeHtml(result)}</pre>`;
    }
    body.appendChild(card);

    // Add Run + Preview buttons for successful builds (not errors)
    if (!isError) {
        const actions = document.createElement("div");
        actions.className = "result-actions";
        actions.innerHTML = `
            <button class="run-btn" onclick="handleRunLatest(this)">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>
                Run App
            </button>
            <button class="preview-toggle-btn" onclick="togglePreview(this)" disabled>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2" ry="2"></rect><line x1="8" y1="21" x2="16" y2="21"></line><line x1="12" y1="17" x2="12" y2="21"></line></svg>
                Preview
            </button>
        `;
        body.appendChild(actions);

        // Preview container (hidden initially)
        const previewWrap = document.createElement("div");
        previewWrap.className = "preview-container";
        previewWrap.style.display = "none";
        previewWrap.innerHTML = `
            <div class="preview-header">
                <span class="preview-url">http://localhost:5173</span>
                <a href="http://localhost:5173" target="_blank" class="preview-open-btn" title="Open in new tab">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg>
                </a>
            </div>
            <iframe class="preview-iframe" src="about:blank"></iframe>
        `;
        body.appendChild(previewWrap);
    }

    chatArea.scrollTop = chatArea.scrollHeight;
}

// ---- Stop build ----
async function handleStop(btn) {
    btn.disabled = true;
    btn.textContent = "Stopping...";
    try {
        await fetch("/api/stop", { method: "POST" });
    } catch {
        // ignore
    }
}

// ---- Run/Stop project from result card ----
async function handleRunLatest(btn) {
    // If already running → stop
    if (btn.classList.contains("running")) {
        btn.disabled = true;
        btn.innerHTML = `<div class="spinner" style="width:12px;height:12px;border-width:2px"></div> Stopping...`;
        try {
            await fetch("/api/stop-server", { method: "POST" });
            runningProject = null;
        } catch {}
        btn.disabled = false;
        btn.classList.remove("running");
        btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg> Run App`;

        // Disable preview
        const previewBtn = btn.parentElement.querySelector(".preview-toggle-btn");
        if (previewBtn) {
            previewBtn.disabled = true;
            previewBtn.classList.remove("active");
        }
        const previewContainer = btn.closest(".message-body").querySelector(".preview-container");
        if (previewContainer) previewContainer.style.display = "none";

        loadProjects();
        return;
    }

    btn.disabled = true;
    btn.innerHTML = `<div class="spinner" style="width:12px;height:12px;border-width:2px"></div> Starting...`;

    try {
        const resp = await fetch("/api/projects");
        const projects = await resp.json();
        if (projects.length === 0) {
            btn.textContent = "No project found";
            return;
        }

        const latest = projects[projects.length - 1];
        const runResp = await fetch(`/api/run/${latest.name}`, { method: "POST" });
        const data = await runResp.json();

        if (data.error) {
            btn.textContent = "Failed";
            btn.title = data.error;
            return;
        }

        if (data.status === "static") {
            btn.textContent = "Static (open manually)";
            return;
        }

        runningProject = latest.name;
        btn.disabled = false;
        btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="6" y="6" width="12" height="12"></rect></svg> Stop`;
        btn.classList.add("running");

        // Enable preview button
        const previewBtn = btn.parentElement.querySelector(".preview-toggle-btn");
        if (previewBtn) previewBtn.disabled = false;

        // Auto-show preview after a brief delay for server to start
        setTimeout(() => {
            if (previewBtn) previewBtn.click();
        }, 2000);

        loadProjects();
    } catch (err) {
        btn.textContent = "Error";
    }
}

// ---- Toggle preview iframe ----
function togglePreview(btn) {
    const body = btn.closest(".message-body");
    const container = body.querySelector(".preview-container");
    if (!container) return;

    const isHidden = container.style.display === "none";
    container.style.display = isHidden ? "block" : "none";
    btn.classList.toggle("active", isHidden);

    if (isHidden) {
        const iframe = container.querySelector(".preview-iframe");
        iframe.src = "http://localhost:5173";
    }

    chatArea.scrollTop = chatArea.scrollHeight;
}

// ---- New Project — reset chat ----
function handleNewProject() {
    // Stop any running build
    if (isBuilding) {
        fetch("/api/stop", { method: "POST" }).catch(() => {});
    }

    // Clear chat area, show welcome
    chatArea.innerHTML = "";
    if (welcomeEl) {
        chatArea.appendChild(welcomeEl);
        welcomeEl.style.display = "";
    }

    // Reset state
    isBuilding = false;
    sendBtn.disabled = false;
    promptInput.disabled = false;
    promptInput.value = "";
    promptInput.style.height = "auto";
    promptInput.focus();

    loadProjects();
}

// ---- Run/Stop project from sidebar ----
async function handleRunProject(projectName, btn) {
    btn.disabled = true;

    // If this project is already running → stop it
    if (runningProject === projectName) {
        btn.textContent = "...";
        try {
            await fetch("/api/stop-server", { method: "POST" });
            runningProject = null;
        } catch {}
        btn.disabled = false;
        btn.textContent = "Run";
        btn.classList.remove("running");
        btn.title = "Run dev server";
        return;
    }

    btn.textContent = "...";
    try {
        const resp = await fetch(`/api/run/${projectName}`, { method: "POST" });
        const data = await resp.json();

        if (data.error) {
            btn.textContent = "Err";
            btn.title = data.error;
            setTimeout(() => { btn.disabled = false; btn.textContent = "Run"; }, 3000);
            return;
        }

        if (data.status === "static") {
            btn.textContent = "Static";
            setTimeout(() => { btn.disabled = false; btn.textContent = "Run"; }, 3000);
            return;
        }

        // Now running
        runningProject = projectName;
        btn.disabled = false;
        btn.textContent = "Stop";
        btn.classList.add("running");
        btn.title = "Stop dev server";

        // Open in new tab
        if (data.url) {
            setTimeout(() => window.open(data.url, "_blank"), 1500);
        }

        // Update other project buttons
        loadProjects();
    } catch {
        btn.textContent = "Err";
        setTimeout(() => { btn.disabled = false; btn.textContent = "Run"; }, 3000);
    }
}

// ---- Show ask_user prompt inline ----
function showAskUser(msgEl, question, sessionId) {
    const body = msgEl.querySelector(".message-body");

    // Hide building indicator while waiting for user
    const indicator = body.querySelector(".building-indicator");
    if (indicator) indicator.style.display = "none";

    // Create ask-user card
    const askCard = document.createElement("div");
    askCard.className = "ask-user-card";
    askCard.innerHTML = `
        <div class="ask-user-question">${escapeHtml(question)}</div>
        <div class="ask-user-input-row">
            <input type="text" class="ask-user-input" placeholder="Type your answer..." autofocus />
            <button class="ask-user-send">Send</button>
        </div>
    `;
    body.appendChild(askCard);

    const inputEl = askCard.querySelector(".ask-user-input");
    const sendBtnEl = askCard.querySelector(".ask-user-send");

    const submitAnswer = async () => {
        const answer = inputEl.value.trim();
        if (!answer) return;

        sendBtnEl.disabled = true;
        inputEl.disabled = true;

        // Show user's answer inline
        askCard.innerHTML = `
            <div class="ask-user-question">${escapeHtml(question)}</div>
            <div class="ask-user-answer">You: ${escapeHtml(answer)}</div>
        `;

        // Show building indicator again
        if (indicator) indicator.style.display = "flex";

        // Send answer to server
        try {
            await fetch(`/api/answer/${sessionId}`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ answer }),
            });
        } catch {
            // ignore — agent will time out
        }
    };

    sendBtnEl.addEventListener("click", submitAnswer);
    inputEl.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
            e.preventDefault();
            submitAnswer();
        }
    });

    inputEl.focus();
    chatArea.scrollTop = chatArea.scrollHeight;
}

// ---- Utils ----
function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}
