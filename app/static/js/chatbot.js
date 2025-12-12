// ===================================================== 
// LOAD TREE.JSON (FAQ SYSTEM)
// =====================================================
async function loadTree() {
  const res = await fetch("/chatbot/tree");
  return await res.json();
}

// =====================================================
// UI HELPERS
// =====================================================
function addBotMessage(html) {
  const chat = document.getElementById("sv-chat-window");
  if (!chat) return;
  const box = document.createElement("div");
  box.className = "sv-msg sv-msg-bot sv-fade-in";
  box.innerHTML = html;
  chat.appendChild(box);
  chat.scrollTop = chat.scrollHeight;
}

function addUserMessage(text) {
  const chat = document.getElementById("sv-chat-window");
  if (!chat) return;
  const box = document.createElement("div");
  box.className = "sv-msg sv-msg-user sv-fade-in";
  box.textContent = text;
  chat.appendChild(box);
  chat.scrollTop = chat.scrollHeight;
}

function clearSuggestions() {
  const s = document.getElementById("sv-suggestions");
  if (s) s.innerHTML = "";
}

// =====================================================
// GLOBAL DATA
// =====================================================
let SECTIONS = [];
let CURRENT_SECTION = null;
let LAST_QUESTION = null;
let LAST_ANSWER = null;

let ACTIVE_TICKET_ID = null;
let AGENT_WATCH_INTERVAL = null;
let CHAT_POLL_INTERVAL = null;
let LAST_MESSAGE_ID = 0;

let IS_TICKET_CLOSED = false;

// =====================================================
// LOCK CHAT UI WHEN TICKET CLOSED
// =====================================================
function lockChatUI(closeText) {
  if (IS_TICKET_CLOSED) return;
  IS_TICKET_CLOSED = true;

  const closedBanner = document.getElementById("sv-ticket-closed-banner");
  if (closedBanner) {
    closedBanner.style.display = "block";
    closedBanner.textContent =
      closeText || "This ticket has been closed. You can start a new chat from the Messages page.";
  }

  const chatInput = document.getElementById("sv-chat-input");
  if (chatInput) chatInput.style.display = "none";

  const faqSection = document.getElementById("sv-suggestions-section");
  if (faqSection) faqSection.style.display = "none";

  if (CHAT_POLL_INTERVAL) {
    clearInterval(CHAT_POLL_INTERVAL);
    CHAT_POLL_INTERVAL = null;
  }
  if (AGENT_WATCH_INTERVAL) {
    clearInterval(AGENT_WATCH_INTERVAL);
    AGENT_WATCH_INTERVAL = null;
  }

  localStorage.removeItem("chatbot_active_ticket");
}

// =====================================================
// RESTORE PREVIOUS TICKET
// =====================================================
document.addEventListener("DOMContentLoaded", () => {
  // 1) إذا السيرفر أرسل تذكرة مفتوحة
  if (window.ACTIVE_TICKET_FROM_SERVER) {
    ACTIVE_TICKET_ID = window.ACTIVE_TICKET_FROM_SERVER;
    localStorage.setItem("chatbot_active_ticket", ACTIVE_TICKET_ID);
    startAgentWatcher(ACTIVE_TICKET_ID);
    startChatPolling(ACTIVE_TICKET_ID);
    return;
  }

  // 2) لو فقط مخزنة في localStorage
  const saved = localStorage.getItem("chatbot_active_ticket");
  if (saved) {
    ACTIVE_TICKET_ID = parseInt(saved);
    startAgentWatcher(ACTIVE_TICKET_ID);
    startChatPolling(ACTIVE_TICKET_ID);
  }
});


// =====================================================
// FEEDBACK BUTTONS
// =====================================================
function showFeedbackButtons() {
  if (IS_TICKET_CLOSED) return;

  const chat = document.getElementById("sv-chat-window");
  if (!chat) return;

  const wrapper = document.createElement("div");
  wrapper.className = "sv-msg sv-msg-bot sv-fade-in";

  wrapper.innerHTML = `
    <div class="sv-feedback-title">✔️ Did this answer your question?</div>
    <div class="sv-feedback-buttons">
      <button class="sv-yes-btn">Yes</button>
      <button class="sv-no-btn">No</button>
    </div>
  `;

  chat.appendChild(wrapper);
  chat.scrollTop = chat.scrollHeight;

  wrapper.querySelector(".sv-yes-btn").onclick = handleYes;
  wrapper.querySelector(".sv-no-btn").onclick = handleNo;
}

function handleYes() {
  if (IS_TICKET_CLOSED) return;

  addBotMessage("Great! 😊<br>Would you like to ask another question?");

  const chat = document.getElementById("sv-chat-window");
  if (!chat) return;

  const btn = document.createElement("button");
  btn.className = "sv-option-chip";
  btn.textContent = "Back to Categories";

  btn.onclick = () => showSections();

  const box = document.createElement("div");
  box.className = "sv-msg sv-msg-bot";
  box.appendChild(btn);
  chat.appendChild(box);
}

// =============================================================
// USER CLICKED NO → CREATE SUPPORT TICKET
// =============================================================
async function handleNo() {
  if (IS_TICKET_CLOSED) return;

  addBotMessage("One moment… contacting support 🕓");

  const formData = new FormData();
  formData.append("question", LAST_QUESTION || "(unknown)");
  formData.append("answer", LAST_ANSWER || "(unknown)");

  const res = await fetch("/chatbot/support", {
    method: "POST",
    body: formData,
  });

  let data;
  try {
    data = await res.json();
  } catch (e) {
    addBotMessage("⚠️ Error contacting support.");
    return;
  }

  if (!data.ok) {
    addBotMessage("⚠️ Failed to create support ticket.");
    return;
  }

  ACTIVE_TICKET_ID = data.ticket_id;
  LAST_MESSAGE_ID = 0;
  IS_TICKET_CLOSED = false;

  localStorage.setItem("chatbot_active_ticket", ACTIVE_TICKET_ID);

  addBotMessage("A support agent will assist you shortly 🟣");

  startAgentWatcher(ACTIVE_TICKET_ID);
  startChatPolling(ACTIVE_TICKET_ID);
}

// =============================================================
// CHECK AGENT STATUS
// =============================================================
async function checkAgentStatus(ticketId) {
  if (IS_TICKET_CLOSED) return;

  try {
    const res = await fetch(`/api/chatbot/agent_status/${ticketId}`);
    const data = await res.json();

    if (data.assigned && data.agent_name) {
      clearInterval(AGENT_WATCH_INTERVAL);
      AGENT_WATCH_INTERVAL = null;

      const banner = document.getElementById("sv-live-agent-banner");
      if (banner) {
        banner.style.display = "block";
        banner.innerHTML = `
          You are now chatting with one of our agents:
          <span style="color:#6b46c1; font-weight:700;">${data.agent_name}</span>
        `;
      }

      const chatInput = document.getElementById("sv-chat-input");
      if (chatInput) chatInput.style.display = "block";

      addBotMessage(
        `You're now connected with <b>${data.agent_name}</b>. How can I help you?`
      );
    }
  } catch (err) {
    console.log("poll error:", err);
  }
}

function startAgentWatcher(ticketId) {
  if (!ticketId) return;
  if (AGENT_WATCH_INTERVAL) clearInterval(AGENT_WATCH_INTERVAL);
  AGENT_WATCH_INTERVAL = setInterval(() => {
    checkAgentStatus(ticketId);
  }, 2000);
}

// =============================================================
// POLL REAL MESSAGES (WITH INSTANT CLOSE)
// =============================================================
async function pollMessages(ticketId) {
  if (!ticketId) return;

  try {
    const res = await fetch(`/api/chatbot/messages/${ticketId}`);
    const data = await res.json();

    // ⚡ INSTANT CLOSE — NO WAITING
    if (data.ticket_status === "closed") {
      if (!IS_TICKET_CLOSED) {
        lockChatUI(
          data.closed_by
            ? `This ticket has been closed by ${data.closed_by}.`
            : "This ticket has been closed."
        );
      }
      return; // stop everything instantly
    }

    // Show new messages
    (data.messages || []).forEach((msg) => {
      if (msg.id > LAST_MESSAGE_ID) {
        LAST_MESSAGE_ID = msg.id;

        if (msg.sender_role === "support" || msg.sender_role === "agent") {
          addBotMessage(msg.body);
        } else if (msg.sender_role === "user") {
          addUserMessage(msg.body);
        } else if (msg.sender_role === "system") {
          addBotMessage(msg.body);
        }
      }
    });

  } catch (e) {
    console.log("chat poll error:", e);
  }
}

function startChatPolling(ticketId) {
  if (!ticketId) return;
  if (CHAT_POLL_INTERVAL) clearInterval(CHAT_POLL_INTERVAL);
  CHAT_POLL_INTERVAL = setInterval(() => {
    pollMessages(ticketId);
  }, 1500);
}

// =============================================================
// SEND MESSAGE
// =============================================================
async function sendUserMessageToServer(text) {
  if (!ACTIVE_TICKET_ID || IS_TICKET_CLOSED) return;

  const formData = new FormData();
  formData.append("body", text);

  await fetch(`/api/chatbot/messages/${ACTIVE_TICKET_ID}`, {
    method: "POST",
    body: formData,
  });
}

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("sv-send-form");
  if (!form) return;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();

    if (IS_TICKET_CLOSED) return;

    const input = document.getElementById("sv-message-input");
    const text = input.value.trim();
    if (!text) return;

    addUserMessage(text);
    input.value = "";

    await sendUserMessageToServer(text);
  });
});

// =============================================================
// SHOW MAIN SECTIONS
// =============================================================
function showSections() {
  if (IS_TICKET_CLOSED) return;

  clearSuggestions();
  const suggestions = document.getElementById("sv-suggestions");
  suggestions.innerHTML = "";

  SECTIONS.forEach((sec) => {
    const btn = document.createElement("button");
    btn.className = "sv-question-chip";
    btn.textContent = sec.section_title;

    btn.onclick = () => {
      CURRENT_SECTION = sec;
      showQuestionsInSection(sec);
      addUserMessage(sec.section_title);
    };

    suggestions.appendChild(btn);
  });
}

// =============================================================
// SHOW QUESTIONS IN A SECTION
// =============================================================
function showQuestionsInSection(section) {
  if (IS_TICKET_CLOSED) return;

  clearSuggestions();
  const suggestions = document.getElementById("sv-suggestions");
  suggestions.innerHTML = "";

  let faqs = section.faqs;

  if (!Array.isArray(faqs)) {
    Object.entries(faqs).forEach(([qText, obj]) => {
      const btn = document.createElement("button");
      btn.className = "sv-question-chip";
      btn.textContent = qText;

      btn.onclick = () =>
        handleQuestionClick({
          label: qText,
          answer: obj.answer,
          options: obj.options || null,
        });

      suggestions.appendChild(btn);
    });
  } else {
    faqs.forEach((item) => {
      const btn = document.createElement("button");
      btn.className = "sv-question-chip";
      btn.textContent = item.question;

      btn.onclick = () =>
        handleQuestionClick({
          label: item.question,
          answer: item.answer,
          options: null,
        });

      suggestions.appendChild(btn);
    });
  }
}

// =============================================================
// QUESTION CLICK HANDLER
// =============================================================
function handleQuestionClick(q) {
  if (IS_TICKET_CLOSED) return;

  addUserMessage(q.label);
  LAST_QUESTION = q.label;

  clearSuggestions();

  if (q.answer) {
    addBotMessage(q.answer);
    LAST_ANSWER = q.answer;
    showFeedbackButtons();
  }

  if (q.options) {
    const chat = document.getElementById("sv-chat-window");
    const box = document.createElement("div");
    box.className = "sv-msg sv-msg-bot";

    const wrapper = document.createElement("div");
    wrapper.className = "sv-options-wrapper";

    const title = document.createElement("div");
    title.className = "sv-options-title";
    title.textContent = "Choose a case:";
    wrapper.appendChild(title);

    Object.entries(q.options).forEach(([label, data]) => {
      const btn = document.createElement("button");
      btn.className = "sv-option-chip";
      btn.textContent = label;

      btn.onclick = () => {
        addUserMessage(label);
        addBotMessage(data.answer || "…");
        LAST_ANSWER = data.answer || "…";
        showFeedbackButtons();
      };

      wrapper.appendChild(btn);
    });

    box.appendChild(wrapper);
    chat.appendChild(box);
    chat.scrollTop = chat.scrollHeight;
  }
}

// =============================================================
// INITIAL LOAD
// =============================================================
document.addEventListener("DOMContentLoaded", async () => {
  const data = await loadTree();
  SECTIONS = data.sections || [];

  addBotMessage("👋 Hello! I’m the Sevor assistant.<br>Select a category to get started.");
  showSections();
});
