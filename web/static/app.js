// ========================================
//  Quiz Agent Platform — Frontend Logic
// ========================================

const chatArea = document.getElementById("chat-area");
const welcomeEl = document.getElementById("welcome");
const promptInput = document.getElementById("prompt-input");
const sendBtn = document.getElementById("send-btn");
const projectsList = document.getElementById("projects-list");
const activeProjectBadge = document.getElementById("active-project-badge");
const activeProjectName = document.getElementById("active-project-name");
const imageUpload = document.getElementById("image-upload");
const uploadBtn = document.getElementById("upload-btn");
const imagePreviewStrip = document.getElementById("image-preview-strip");

let isBuilding = false;
let runningProject = null;
let currentProject = null; // Currently active project name
let currentEventSource = null; // Track active SSE connection
let pendingImages = []; // Files waiting to be sent with next message

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

    // Image upload
    uploadBtn.addEventListener("click", () => imageUpload.click());
    imageUpload.addEventListener("change", handleImageSelect);

    // Quick prompts
    document.querySelectorAll(".quick-prompt").forEach((btn) => {
        btn.addEventListener("click", () => {
            const prompt = btn.dataset.prompt;
            // Auto-generate project name from button text
            const autoName = btn.textContent.trim().toLowerCase().replace(/\s+/g, "_");
            setActiveProject(autoName);
            promptInput.value = prompt;
            promptInput.dispatchEvent(new Event("input"));
            handleSend();
        });
    });
});

// ---- Active project management ----
function setActiveProject(name) {
    currentProject = name;
    activeProjectBadge.style.display = "flex";
    activeProjectName.textContent = name;
    promptInput.placeholder = `Describe what to build or change in "${name}"...`;
}

function clearActiveProject() {
    currentProject = null;
    activeProjectBadge.style.display = "none";
    activeProjectName.textContent = "";
    promptInput.placeholder = "Select a project or type to get started...";
    loadProjects(); // Refresh to remove highlight
}

// ---- Disable/enable sidebar project buttons during build ----
function setSidebarDisabled(disabled) {
    document.querySelectorAll(".project-item").forEach((item) => {
        if (disabled) {
            item.classList.add("disabled");
            item.style.pointerEvents = "none";
            item.style.opacity = "0.5";
        } else {
            item.classList.remove("disabled");
            item.style.pointerEvents = "";
            item.style.opacity = "";
        }
    });
}

// ---- Load existing projects ----
async function loadProjects() {
    try {
        const runResp = await fetch("/api/running");
        if (!runResp.ok) throw new Error("Failed to check running status");
        const runData = await runResp.json();
        runningProject = runData.running ? runData.project : null;
    } catch {
        runningProject = null;
    }

    try {
        const resp = await fetch("/api/projects");
        if (!resp.ok) throw new Error("Failed to load projects");
        const projects = await resp.json();
        if (projects.length === 0) {
            projectsList.innerHTML = '<p class="muted">No projects yet</p>';
        } else {
            projectsList.innerHTML = projects
                .map((p) => {
                    const isRunning = runningProject === p.name;
                    const isActive = currentProject === p.name;
                    const btnClass = isRunning ? "project-run-btn running" : "project-run-btn";
                    const btnText = isRunning ? "Stop" : "Run";
                    const itemClass = isActive ? "project-item active" : "project-item";
                    return `
                <div class="${itemClass}" onclick="handleProjectClick('${p.name}')">
                    <span class="project-name">${p.name}</span>
                    <div class="project-actions">
                        <span class="project-tech">${p.tech}</span>
                        <button class="${btnClass}" onclick="event.stopPropagation(); handleRunProject('${p.name}', this)" title="${isRunning ? 'Stop dev server' : 'Run dev server'}">${btnText}</button>
                    </div>
                </div>
            `;
                })
                .join("");
        }
        // Re-apply disabled state if building
        if (isBuilding) setSidebarDisabled(true);
    } catch {
        projectsList.innerHTML = '<p class="muted">Could not load projects</p>';
    }
}

// ---- Check integrations status ----
function checkStatus() {
    const figmaDot = document.getElementById("figma-status");
    const mcpDot = document.getElementById("mcp-status");
    const memoryDot = document.getElementById("memory-status");

    fetch("/api/status")
        .then((r) => {
            if (!r.ok) throw new Error("Status check failed");
            return r.json();
        })
        .then((data) => {
            if (data.figma) figmaDot.classList.add("active");
            if (data.mcp) mcpDot.classList.add("active");
            if (data.memory) memoryDot.classList.add("active");
        })
        .catch(() => {});
}

// ---- Handle clicking an existing project ----
function handleProjectClick(projectName) {
    // If switching projects while building, ignore
    if (isBuilding) return;

    // 1. Select the project immediately (this enables chat input)
    setActiveProject(projectName);

    // 2. Clear chat area
    chatArea.innerHTML = "";
    if (welcomeEl) {
        chatArea.appendChild(welcomeEl);
        welcomeEl.style.display = "none";
    }

    // 3. Show a working-on card right away so user knows it's selected
    const statusCard = document.createElement("div");
    statusCard.className = "message message-agent project-selected-card";
    statusCard.innerHTML = `
        <div class="message-header">
            <div class="message-avatar">A</div>
            <span class="message-label">Agent</span>
        </div>
        <div class="message-body">
            <div class="project-selected-info">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>
                <span>Working on <strong>${escapeHtml(projectName)}</strong> &mdash; describe your changes below.</span>
            </div>
        </div>
    `;
    chatArea.appendChild(statusCard);

    // 4. Focus input and refresh sidebar immediately (don't wait for history)
    promptInput.focus();
    loadProjects();

    // 5. Load chat history in background (non-blocking)
    _loadChatHistory(projectName, statusCard);
}

async function _loadChatHistory(projectName, statusCard) {
    try {
        const resp = await fetch(`/api/chat-history/${projectName}`);
        if (!resp.ok) return; // Server doesn't have this endpoint yet — just keep the status card
        const history = await resp.json();
        if (!Array.isArray(history) || history.length === 0) return; // No history — keep status card as is

        // We have history — rebuild the chat area with it
        // Remove the status card we placed
        statusCard.remove();

        // Add "Previous conversation" separator at top
        const sep = document.createElement("div");
        sep.className = "history-separator";
        sep.textContent = "Previous conversation";
        chatArea.appendChild(sep);

        // Render previous messages
        history.forEach((msg) => {
            if (msg.type === "user") {
                addMessage("user", msg.text);
            } else if (msg.type === "agent") {
                const agentEl = addMessage("agent", "");
                const body = agentEl.querySelector(".message-body");
                const card = document.createElement("div");
                card.className = "result-card";
                if (msg.status === "error") {
                    card.style.borderColor = "var(--error)";
                    card.innerHTML = `<h4 style="color: var(--error)">Error</h4><pre>${escapeHtml(msg.text)}</pre>`;
                } else if (msg.status === "stopped") {
                    card.style.borderColor = "var(--warning)";
                    card.innerHTML = `<h4 style="color: var(--warning)">Build Stopped</h4><pre>${escapeHtml(msg.text)}</pre>`;
                } else {
                    card.innerHTML = `<h4>Build Complete</h4><pre>${escapeHtml(msg.text)}</pre>`;
                }
                body.innerHTML = "";
                body.appendChild(card);
            }
        });

        // Add continuation hint at bottom
        const hint = document.createElement("div");
        hint.className = "message message-agent project-selected-card";
        hint.innerHTML = `
            <div class="message-header">
                <div class="message-avatar">A</div>
                <span class="message-label">Agent</span>
            </div>
            <div class="message-body">
                <div class="project-selected-info">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>
                    <span>Continuing <strong>${escapeHtml(projectName)}</strong> &mdash; describe your next changes.</span>
                </div>
                <div class="history-revert-container"></div>
            </div>
        `;
        chatArea.appendChild(hint);
        chatArea.scrollTop = chatArea.scrollHeight;

        // Check for snapshots and show revert button if available
        const snapshots = await loadSnapshots(projectName);
        if (snapshots.length > 0) {
            const container = hint.querySelector(".history-revert-container");
            const revertBtn = document.createElement("button");
            revertBtn.className = "revert-btn";
            revertBtn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="1 4 1 10 7 10"></polyline><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"></path></svg> Revert Last Change`;
            revertBtn.addEventListener("click", () => handleRevertLatest(revertBtn));
            container.appendChild(revertBtn);
        }
    } catch {
        // Silently ignore — the status card is already showing, project is selected and usable
    }
}

// ---- Show select-or-create card when user chats without a project ----
function showSelectOrCreateCard(pendingPrompt) {
    if (welcomeEl) welcomeEl.style.display = "none";

    const card = document.createElement("div");
    card.className = "message message-agent";

    // Fetch existing projects to show as options
    fetch("/api/projects")
        .then((r) => {
            if (!r.ok) throw new Error("Failed to load projects");
            return r.json();
        })
        .then((projects) => {
            let projectButtons = "";
            if (projects.length > 0) {
                projectButtons = `
                    <div class="select-project-label">Select an existing project:</div>
                    <div class="select-project-list">
                        ${projects.map((p) => `<button class="select-project-btn" data-name="${p.name}">${p.name} <span class="select-project-tech">${p.tech}</span></button>`).join("")}
                    </div>
                    <div class="select-project-divider">or</div>
                `;
            }

            card.innerHTML = `
                <div class="message-header">
                    <div class="message-avatar">A</div>
                    <span class="message-label">Agent</span>
                </div>
                <div class="message-body">
                    <div class="select-or-create-card">
                        <div class="project-name-card-title">No project selected</div>
                        <p class="project-name-card-desc">Pick a project to modify, or create a new one.</p>
                        ${projectButtons}
                        <div class="select-project-label">Create a new project:</div>
                        <div class="project-name-card-row">
                            <input type="text" class="project-name-card-input" placeholder="new_project_name" />
                            <button class="project-name-card-btn">Create &amp; Build</button>
                        </div>
                    </div>
                </div>
            `;
            chatArea.appendChild(card);
            chatArea.scrollTop = chatArea.scrollHeight;

            // Auto-suggest name for new project
            const input = card.querySelector(".project-name-card-input");
            if (pendingPrompt) {
                const words = pendingPrompt.toLowerCase()
                    .replace(/[^a-z0-9\s]/g, "")
                    .split(/\s+/)
                    .filter((w) => w.length > 2 && !["build", "create", "make", "quiz", "with", "about", "the", "and", "for", "that"].includes(w))
                    .slice(0, 2);
                if (words.length > 0) {
                    input.value = words.join("_") + "_quiz";
                }
            }

            // Handle clicking an existing project button
            card.querySelectorAll(".select-project-btn").forEach((btn) => {
                btn.addEventListener("click", () => {
                    const name = btn.dataset.name;
                    // Replace card content with confirmation
                    const body = card.querySelector(".message-body");
                    body.innerHTML = `<div class="project-name-confirmed">Selected: <strong>${escapeHtml(name)}</strong></div>`;
                    setActiveProject(name);
                    loadProjects();

                    if (pendingPrompt) {
                        promptInput.value = pendingPrompt;
                        promptInput.dispatchEvent(new Event("input"));
                        setTimeout(() => handleSend(), 200);
                    } else {
                        promptInput.focus();
                    }
                });
            });

            // Handle creating new project
            const createBtn = card.querySelector(".project-name-card-btn");
            const confirmCreate = () => {
                const name = input.value.trim().toLowerCase().replace(/\s+/g, "_").replace(/[^a-z0-9_]/g, "");
                if (!name) {
                    input.style.borderColor = "var(--error)";
                    setTimeout(() => { input.style.borderColor = ""; }, 1500);
                    return;
                }
                const body = card.querySelector(".message-body");
                body.innerHTML = `<div class="project-name-confirmed">Project: <strong>${escapeHtml(name)}</strong></div>`;
                setActiveProject(name);
                loadProjects();

                if (pendingPrompt) {
                    promptInput.value = pendingPrompt;
                    promptInput.dispatchEvent(new Event("input"));
                    setTimeout(() => handleSend(), 200);
                } else {
                    promptInput.focus();
                }
            };
            createBtn.addEventListener("click", confirmCreate);
            input.addEventListener("keydown", (e) => {
                if (e.key === "Enter") { e.preventDefault(); confirmCreate(); }
            });

            // Focus the first project button if any, otherwise the input
            const firstBtn = card.querySelector(".select-project-btn");
            if (firstBtn) firstBtn.focus();
            else input.focus();
        })
        .catch(() => {
            // Fallback: just show the name input
            showProjectNameCard(pendingPrompt);
        });
}

// ---- Show project name input card in chat ----
function showProjectNameCard(pendingPrompt) {
    // Hide welcome
    if (welcomeEl) welcomeEl.style.display = "none";

    const card = document.createElement("div");
    card.className = "message message-agent";
    card.innerHTML = `
        <div class="message-header">
            <div class="message-avatar">A</div>
            <span class="message-label">Agent</span>
        </div>
        <div class="message-body">
            <div class="project-name-card">
                <div class="project-name-card-title">Name your project</div>
                <p class="project-name-card-desc">Choose a short name for this project (e.g., space_quiz, js_fundamentals)</p>
                <div class="project-name-card-row">
                    <input type="text" class="project-name-card-input" placeholder="my_quiz" autofocus />
                    <button class="project-name-card-btn">Start Building</button>
                </div>
            </div>
        </div>
    `;
    chatArea.appendChild(card);
    chatArea.scrollTop = chatArea.scrollHeight;

    const input = card.querySelector(".project-name-card-input");
    const btn = card.querySelector(".project-name-card-btn");

    // Auto-generate a name suggestion from the pending prompt
    if (pendingPrompt) {
        const words = pendingPrompt.toLowerCase()
            .replace(/[^a-z0-9\s]/g, "")
            .split(/\s+/)
            .filter((w) => w.length > 2 && !["build", "create", "make", "quiz", "with", "about", "the", "and", "for", "that"].includes(w))
            .slice(0, 2);
        if (words.length > 0) {
            input.value = words.join("_") + "_quiz";
        }
    }

    const confirm = () => {
        const name = input.value.trim().toLowerCase().replace(/\s+/g, "_").replace(/[^a-z0-9_]/g, "");
        if (!name) {
            input.style.borderColor = "var(--error)";
            setTimeout(() => { input.style.borderColor = ""; }, 1500);
            return;
        }

        // Replace the card with confirmation
        const body = card.querySelector(".message-body");
        body.innerHTML = `<div class="project-name-confirmed">Project: <strong>${escapeHtml(name)}</strong></div>`;

        setActiveProject(name);
        loadProjects();

        // If there was a pending prompt, send it now
        if (pendingPrompt) {
            promptInput.value = pendingPrompt;
            promptInput.dispatchEvent(new Event("input"));
            // Small delay so user sees the confirmation
            setTimeout(() => handleSend(), 200);
        } else {
            promptInput.focus();
        }
    };

    btn.addEventListener("click", confirm);
    input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
            e.preventDefault();
            confirm();
        }
    });

    input.focus();
}

// ---- Image upload handling ----
function handleImageSelect(e) {
    const files = Array.from(e.target.files);
    if (!files.length) return;
    for (const file of files) {
        if (!file.type.startsWith("image/")) continue;
        pendingImages.push(file);
    }
    imageUpload.value = ""; // Reset so same file can be re-selected
    renderImagePreviews();
}

function renderImagePreviews() {
    if (pendingImages.length === 0) {
        imagePreviewStrip.style.display = "none";
        imagePreviewStrip.innerHTML = "";
        return;
    }
    imagePreviewStrip.style.display = "flex";
    imagePreviewStrip.innerHTML = "";
    pendingImages.forEach((file, idx) => {
        const thumb = document.createElement("div");
        thumb.className = "image-preview-thumb";
        const img = document.createElement("img");
        img.src = URL.createObjectURL(file);
        img.alt = file.name;
        const removeBtn = document.createElement("button");
        removeBtn.className = "image-preview-remove";
        removeBtn.innerHTML = "&times;";
        removeBtn.title = "Remove";
        removeBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            pendingImages.splice(idx, 1);
            renderImagePreviews();
        });
        thumb.appendChild(img);
        thumb.appendChild(removeBtn);
        imagePreviewStrip.appendChild(thumb);
    });
}

function clearPendingImages() {
    pendingImages = [];
    imagePreviewStrip.style.display = "none";
    imagePreviewStrip.innerHTML = "";
}

// ---- Send message ----
async function handleSend() {
    const prompt = promptInput.value.trim();
    if (!prompt || isBuilding) return;

    // If no project is active, ask user to select or create
    if (!currentProject) {
        showSelectOrCreateCard(prompt);
        promptInput.value = "";
        promptInput.style.height = "auto";
        return;
    }

    const projectName = currentProject;
    const userPromptText = prompt; // Save for history

    // Capture attached images before clearing
    const imagesToSend = [...pendingImages];

    // Hide welcome
    if (welcomeEl) welcomeEl.style.display = "none";

    // Add user message (show prompt cleanly, project context is in the badge)
    addMessage("user", prompt, false, false, imagesToSend);

    // Clear prompt input and images
    promptInput.value = "";
    promptInput.style.height = "auto";
    clearPendingImages();

    // Disable input while building
    isBuilding = true;
    sendBtn.disabled = true;
    promptInput.disabled = true;
    setSidebarDisabled(true);

    // Check if this is an existing project (it was selected from sidebar)
    const isExisting = document.querySelector(`.project-item.active .project-name[onclick*="'${projectName}'"]`) !== null;

    // Add agent response placeholder with appropriate indicator
    const agentMsg = addMessage("agent", null, true, isExisting);

    try {
        let resp;
        if (imagesToSend.length > 0) {
            const formData = new FormData();
            formData.append("prompt", prompt);
            formData.append("project_name", projectName);
            for (const file of imagesToSend) {
                formData.append("images", file);
            }
            resp = await fetch("/api/build", { method: "POST", body: formData });
        } else {
            resp = await fetch("/api/build", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ prompt, project_name: projectName }),
            });
        }

        if (!resp.ok) {
            const errText = await resp.text();
            setMessageResult(agentMsg, `Server error (${resp.status}): ${errText}`, true);
            finishBuild();
            return;
        }

        const { session_id, error } = await resp.json();
        if (error) {
            setMessageResult(agentMsg, error, true);
            finishBuild();
            return;
        }

        // Close previous EventSource if any
        if (currentEventSource) {
            currentEventSource.close();
            currentEventSource = null;
        }

        const eventSource = new EventSource(`/api/stream/${session_id}`);
        currentEventSource = eventSource;
        const logContainer = agentMsg.querySelector(".log-stream");

        eventSource.onmessage = (event) => {
            const data = JSON.parse(event.data);

            if (data.type === "log") {
                addLogLine(logContainer, data.message);
            } else if (data.type === "heartbeat") {
                // Ignore heartbeats in chat display — they just keep the connection alive
            } else if (data.type === "ask_user") {
                showAskUser(agentMsg, data.message, session_id);
            } else if (data.type === "result") {
                setMessageResult(agentMsg, data.message, false);
                saveChatHistory(projectName, userPromptText, data.message, "success");
                eventSource.close();
                currentEventSource = null;
                finishBuild();
                loadProjects();
            } else if (data.type === "stopped") {
                setMessageResult(agentMsg, data.message, false, true);
                saveChatHistory(projectName, userPromptText, data.message, "stopped");
                eventSource.close();
                currentEventSource = null;
                finishBuild();
                loadProjects();
            } else if (data.type === "error") {
                setMessageResult(agentMsg, data.message, true);
                saveChatHistory(projectName, userPromptText, data.message, "error");
                eventSource.close();
                currentEventSource = null;
                finishBuild();
            } else if (data.type === "done") {
                eventSource.close();
                currentEventSource = null;
                finishBuild();
            }
        };

        eventSource.onerror = () => {
            eventSource.close();
            currentEventSource = null;
            if (isBuilding) {
                setMessageResult(agentMsg, "Connection lost. Check the terminal for details.", true);
                finishBuild();
            }
        };
    } catch (err) {
        setMessageResult(agentMsg, `Failed to connect: ${err.message}`, true);
        finishBuild();
    }
}

function finishBuild() {
    isBuilding = false;
    sendBtn.disabled = false;
    promptInput.disabled = false;
    setSidebarDisabled(false);
    promptInput.placeholder = `Describe more changes for "${currentProject}"...`;
    promptInput.focus();
}

// ---- Add a message to chat ----
function addMessage(type, text, isStreaming = false, isModify = false, images = []) {
    const msg = document.createElement("div");
    msg.className = `message message-${type}`;

    const avatar = type === "user" ? "U" : "A";
    const label = type === "user" ? "You" : "Agent";

    if (type === "user") {
        let imagesHtml = "";
        if (images && images.length > 0) {
            const thumbs = images.map((file) => {
                const url = URL.createObjectURL(file);
                return `<img src="${url}" alt="${escapeHtml(file.name)}" class="user-msg-thumb" />`;
            }).join("");
            imagesHtml = `<div class="user-msg-images">${thumbs}</div>`;
        }
        msg.innerHTML = `
            <div class="message-header">
                <div class="message-avatar">${avatar}</div>
                <span class="message-label">${label}</span>
            </div>
            <div class="message-body">${imagesHtml}${escapeHtml(text)}</div>
        `;
    } else if (isStreaming) {
        const buildText = isModify ? "Analyzing project & applying changes..." : "Building your quiz app...";
        msg.innerHTML = `
            <div class="message-header">
                <div class="message-avatar">${avatar}</div>
                <span class="message-label">${label}</span>
            </div>
            <div class="message-body">
                <div class="building-indicator">
                    <div class="spinner"></div>
                    <span class="building-text">${buildText}</span>
                    <button class="stop-btn" onclick="handleStop(this)" title="Stop">Stop</button>
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

    // Skip heartbeat messages in log display
    if (text === "Still working...") return;

    const line = document.createElement("div");
    line.className = "log-line";

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
    chatArea.scrollTop = chatArea.scrollHeight;
}

// ---- Set the final result on an agent message ----
function setMessageResult(msgEl, result, isError, isStopped = false) {
    const body = msgEl.querySelector(".message-body");

    const indicator = body.querySelector(".building-indicator");
    if (indicator) indicator.remove();

    const card = document.createElement("div");
    card.className = "result-card";
    if (isError) {
        card.style.borderColor = "var(--error)";
        card.innerHTML = `
            <h4 style="color: var(--error)">Error</h4>
            <pre>${escapeHtml(result)}</pre>
            <button class="retry-btn" onclick="handleRetry(this)">Retry Build</button>
        `;
    } else if (isStopped) {
        card.style.borderColor = "var(--warning)";
        card.innerHTML = `<h4 style="color: var(--warning)">Build Stopped</h4><pre>${escapeHtml(result)}</pre>`;
    } else {
        card.innerHTML = `<h4>Build Complete</h4><pre>${escapeHtml(result)}</pre>`;
    }
    body.appendChild(card);

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
            <button class="revert-btn" onclick="handleRevertLatest(this)">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="1 4 1 10 7 10"></polyline><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"></path></svg>
                Revert
            </button>
        `;
        body.appendChild(actions);

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
        const resp = await fetch("/api/stop", { method: "POST" });
        if (!resp.ok) {
            // Stop request failed — recover button
            btn.disabled = false;
            btn.textContent = "Stop";
        }
    } catch {
        // Network error — recover button
        btn.disabled = false;
        btn.textContent = "Stop";
    }
}

// ---- Run/Stop project from result card ----
async function handleRunLatest(btn) {
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
        // Use the currently selected project, not the latest
        let projectToRun = currentProject;
        if (!projectToRun) {
            const resp = await fetch("/api/projects");
            if (!resp.ok) throw new Error("Failed to load projects");
            const projects = await resp.json();
            if (projects.length === 0) {
                btn.textContent = "No project found";
                return;
            }
            projectToRun = projects[projects.length - 1].name;
        }

        const runResp = await fetch(`/api/run/${projectToRun}`, { method: "POST" });
        if (!runResp.ok) {
            const errData = await runResp.json().catch(() => ({ error: "Unknown error" }));
            btn.textContent = "Failed";
            btn.title = errData.error || "Unknown error";
            return;
        }
        const data = await runResp.json();

        if (data.error) {
            btn.textContent = "Failed";
            btn.title = data.error;
            return;
        }

        runningProject = projectToRun;
        btn.disabled = false;
        btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="6" y="6" width="12" height="12"></rect></svg> Stop`;
        btn.classList.add("running");

        const previewBtn = btn.parentElement.querySelector(".preview-toggle-btn");
        if (previewBtn) previewBtn.disabled = false;

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

// ---- New Project — reset chat & prompt for name ----
function handleNewProject() {
    if (isBuilding) {
        fetch("/api/stop", { method: "POST" }).catch(() => {});
    }

    // Clear chat area, show welcome
    chatArea.innerHTML = "";
    if (welcomeEl) {
        chatArea.appendChild(welcomeEl);
        welcomeEl.style.display = "none";
    }

    // Reset state
    isBuilding = false;
    sendBtn.disabled = false;
    promptInput.disabled = false;
    promptInput.value = "";
    promptInput.style.height = "auto";
    setSidebarDisabled(false);
    clearActiveProject();
    loadProjects();

    // Show name card for new project
    showProjectNameCard(null);
}

// ---- Run/Stop project from sidebar ----
async function handleRunProject(projectName, btn) {
    btn.disabled = true;

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
        if (!resp.ok) {
            const errData = await resp.json().catch(() => ({ error: "Unknown error" }));
            btn.textContent = "Err";
            btn.title = errData.error || "Unknown error";
            setTimeout(() => { btn.disabled = false; btn.textContent = "Run"; }, 3000);
            return;
        }
        const data = await resp.json();

        if (data.error) {
            btn.textContent = "Err";
            btn.title = data.error;
            setTimeout(() => { btn.disabled = false; btn.textContent = "Run"; }, 3000);
            return;
        }

        runningProject = projectName;
        btn.disabled = false;
        btn.textContent = "Stop";
        btn.classList.add("running");
        btn.title = "Stop dev server";

        if (data.url) {
            setTimeout(() => window.open(data.url, "_blank"), 1500);
        }

        loadProjects();
    } catch {
        btn.textContent = "Err";
        setTimeout(() => { btn.disabled = false; btn.textContent = "Run"; }, 3000);
    }
}

// ---- Show ask_user prompt inline ----
function showAskUser(msgEl, question, sessionId) {
    const body = msgEl.querySelector(".message-body");

    const indicator = body.querySelector(".building-indicator");
    if (indicator) indicator.style.display = "none";

    const askCard = document.createElement("div");
    askCard.className = "ask-user-card";

    // Add timeout countdown
    let timeLeft = 300; // 5 minutes
    askCard.innerHTML = `
        <div class="ask-user-question">${escapeHtml(question)}</div>
        <div class="ask-user-input-row">
            <input type="text" class="ask-user-input" placeholder="Type your answer..." autofocus />
            <button class="ask-user-send">Send</button>
        </div>
        <div class="ask-user-timeout" style="font-size:11px;color:var(--text-muted);margin-top:6px;">Waiting for your response...</div>
    `;
    body.appendChild(askCard);

    const inputEl = askCard.querySelector(".ask-user-input");
    const sendBtnEl = askCard.querySelector(".ask-user-send");
    const timeoutEl = askCard.querySelector(".ask-user-timeout");

    // Countdown timer
    const countdownInterval = setInterval(() => {
        timeLeft--;
        if (timeLeft <= 60) {
            timeoutEl.textContent = `Response needed within ${timeLeft}s...`;
            timeoutEl.style.color = "var(--warning)";
        }
        if (timeLeft <= 0) {
            clearInterval(countdownInterval);
            timeoutEl.textContent = "Timed out — agent will continue without your input.";
            timeoutEl.style.color = "var(--error)";
        }
    }, 1000);

    const submitAnswer = async () => {
        const answer = inputEl.value.trim();
        if (!answer) return;

        clearInterval(countdownInterval);
        sendBtnEl.disabled = true;
        inputEl.disabled = true;

        askCard.innerHTML = `
            <div class="ask-user-question">${escapeHtml(question)}</div>
            <div class="ask-user-answer">You: ${escapeHtml(answer)}</div>
        `;

        if (indicator) indicator.style.display = "flex";

        try {
            const resp = await fetch(`/api/answer/${sessionId}`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ answer }),
            });
            if (!resp.ok) {
                console.error("Failed to send answer:", resp.status);
            }
        } catch (err) {
            console.error("Error sending answer:", err);
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

// ---- Retry after error ----
function handleRetry(btn) {
    if (!currentProject) {
        showProjectNameCard("Fix any previous errors and complete the build.");
        return;
    }
    promptInput.value = `Continue building the "${currentProject}" project. Fix any previous errors and complete the build.`;
    promptInput.dispatchEvent(new Event("input"));
    handleSend();
}

// ---- Save chat history to backend ----
function saveChatHistory(projectName, userText, agentText, status) {
    fetch(`/api/chat-history/${projectName}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            messages: [
                { type: "user", text: userText, timestamp: new Date().toISOString() },
                { type: "agent", text: agentText, status, timestamp: new Date().toISOString() },
            ],
        }),
    }).catch((err) => {
        console.error("Failed to save chat history:", err);
    });
}

// ---- Snapshot / Revert ----
async function loadSnapshots(projectName) {
    try {
        const resp = await fetch(`/api/snapshots/${projectName}`);
        if (!resp.ok) return [];
        return await resp.json();
    } catch {
        return [];
    }
}

async function handleRevert(projectName, snapshotId) {
    if (!confirm("Revert to the previous version? This will restore files and chat history from before the last change.")) return;
    try {
        const resp = await fetch(`/api/revert/${projectName}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ snapshot_id: snapshotId }),
        });
        const data = await resp.json();
        if (data.status === "ok") {
            // Reload the project view to reflect reverted state
            handleProjectClick(projectName);
        } else {
            alert("Revert failed: " + (data.message || "Unknown error"));
        }
    } catch (err) {
        alert("Revert failed: " + err.message);
    }
}

async function handleRevertLatest(btn) {
    if (!currentProject) return;
    btn.disabled = true;
    btn.textContent = "Reverting...";
    const snapshots = await loadSnapshots(currentProject);
    if (snapshots.length === 0) {
        btn.textContent = "No snapshots";
        setTimeout(() => { btn.disabled = false; btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="1 4 1 10 7 10"></polyline><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"></path></svg> Revert`; }, 2000);
        return;
    }
    await handleRevert(currentProject, snapshots[0].snapshot_id);
}

// ---- Utils ----
function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}
