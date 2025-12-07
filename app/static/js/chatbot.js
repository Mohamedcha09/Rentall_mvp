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

function handleNo() {
  addBotMessage("I understand ❤️ We're here to help.");

  const chat = document.getElementById("sv-chat-window");
  const btn = document.createElement("button");
  btn.className = "sv-option-chip";
  btn.textContent = "Contact Support";

  btn.onclick = () => (window.location.href = "/messages");

  const box = document.createElement("div");
  box.className = "sv-msg sv-msg-bot";
  box.appendChild(btn);
  chat.appendChild(box);
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
// SHOW QUESTIONS IN SELECTED SECTION
// ===========================
function showQuestionsInSection(section) {
  clearSuggestions();

  const suggestions = document.getElementById("sv-suggestions");
  suggestions.innerHTML = "";

  let faqs = section.faqs;

  // Object-based FAQs
  if (!Array.isArray(faqs)) {
    Object.entries(faqs).forEach(([question, obj]) => {
      const btn = document.createElement("button");
      btn.className = "sv-question-chip";
      btn.textContent = question;

      btn.onclick = () => handleQuestionClick({
        label: question,
        answer: obj.answer,
        options: obj.options || null
      });

      suggestions.appendChild(btn);
    });
  }
  // Array-based FAQs
  else {
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
// USER SELECTS A QUESTION
// ===========================
function handleQuestionClick(q) {
  addUserMessage(q.label);
  clearSuggestions();

  if (q.answer) {
    addBotMessage(q.answer);
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

  // 🔥 ENGLISH INTRO
  addBotMessage("👋 Hello! I’m the Sevor assistant.<br>Select a category to get started.");

  showSections();
});
