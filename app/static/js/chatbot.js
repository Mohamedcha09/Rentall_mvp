// ===========================
// LOAD TREE.JSON
// ===========================
async function loadTree() {
  const res = await fetch("/chatbot/tree");
  return await res.json();
}

// ===========================
// UI HELPERS
// ===========================
function addBotMessage(html) {
  const chat = document.getElementById("sv-chat-window");
  const box = document.createElement("div");
  box.className = "sv-msg sv-msg-bot sv-fade-in";
  box.innerHTML = html;
  chat.appendChild(box);
  chat.scrollTop = chat.scrollHeight;
}

function addUserMessage(text) {
  const chat = document.getElementById("sv-chat-window");
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

// ===========================
// GLOBAL DATA
// ===========================
let SECTIONS = [];
let CURRENT_SECTION = null;

let LAST_QUESTION = null;
let LAST_ANSWER = null;

// ===========================
// FEEDBACK BUTTONS
// ===========================
function showFeedbackButtons() {
  const chat = document.getElementById("sv-chat-window");

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
  addBotMessage("Great! 😊<br>Would you like to ask another question?");

  const chat = document.getElementById("sv-chat-window");
  const btn = document.createElement("button");
  btn.className = "sv-option-chip";
  btn.textContent = "Back to Categories";

  btn.onclick = () => showSections();

  const box = document.createElement("div");
  box.className = "sv-msg sv-msg-bot";
  box.appendChild(btn);
  chat.appendChild(box);
}

// ================================
// 🚨 NEW: REAL CONTACT SUPPORT FLOW
// ================================
async function handleNo() {
  addBotMessage("One moment… contacting support 🕓");

  // إرسال بيانات السؤال والجواب إلى API لإنشاء Ticket
  const formData = new FormData();
  formData.append("question", LAST_QUESTION || "(unknown)");
  formData.append("answer", LAST_ANSWER || "(unknown)");

  const res = await fetch("/chatbot/support", {
    method: "POST",
    body: formData
  });

  let data;
  try {
    data = await res.json();
  } catch (e) {
    addBotMessage("⚠️ Error contacting support.");
    return;
  }

  if (data.ok) {
    addBotMessage("A support agent will assist you shortly 🟣");

    // افتح صفحة التيكيت الجديدة
    window.location.href = `/support/ticket/${data.ticket_id}`;
  } else {
    addBotMessage("⚠️ Failed to create support ticket.");
  }
}

// ===========================
// SHOW MAIN CATEGORIES
// ===========================
function showSections() {
  clearSuggestions();

  const suggestions = document.getElementById("sv-suggestions");
  suggestions.innerHTML = "";

  SECTIONS.forEach(sec => {
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

// ===========================
// SHOW QUESTIONS
// ===========================
function showQuestionsInSection(section) {
  clearSuggestions();

  const suggestions = document.getElementById("sv-suggestions");
  suggestions.innerHTML = "";

  let faqs = section.faqs;

  if (!Array.isArray(faqs)) {
    Object.entries(faqs).forEach(([qText, obj]) => {
      const btn = document.createElement("button");
      btn.className = "sv-question-chip";
      btn.textContent = qText;

      btn.onclick = () => handleQuestionClick({
        label: qText,
        answer: obj.answer,
        options: obj.options || null
      });

      suggestions.appendChild(btn);
    });
  } else {
    faqs.forEach(item => {
      const btn = document.createElement("button");
      btn.className = "sv-question-chip";
      btn.textContent = item.question;

      btn.onclick = () => handleQuestionClick({
        label: item.question,
        answer: item.answer,
        options: null
      });

      suggestions.appendChild(btn);
    });
  }
}

// ===========================
// SELECT QUESTION
// ===========================
function handleQuestionClick(q) {
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
        addBotMessage(data.answer || "...");
        LAST_ANSWER = data.answer || "...";
        showFeedbackButtons();
      };

      wrapper.appendChild(btn);
    });

    box.appendChild(wrapper);
    chat.appendChild(box);
    chat.scrollTop = chat.scrollHeight;
  }
}

// ===========================
// INITIAL LOAD
// ===========================
document.addEventListener("DOMContentLoaded", async () => {
  const data = await loadTree();
  SECTIONS = data.sections || [];

  addBotMessage("👋 Hello! I’m the Sevor assistant.<br>Select a category to get started.");

  showSections();
});
