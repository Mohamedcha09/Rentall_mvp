// ===============
//  LOAD TREE
// ===============
async function loadTree() {
  const res = await fetch("/chatbot/tree");
  return await res.json();
}

// ===============
//  UI HELPERS
// ===============
function addBotMessage(text) {
  const chat = document.getElementById("sv-chat-window");
  const box = document.createElement("div");
  box.className = "sv-msg sv-msg-bot";
  box.innerHTML = text;
  chat.appendChild(box);
  chat.scrollTop = chat.scrollHeight;
}

function addUserMessage(text) {
  const chat = document.getElementById("sv-chat-window");
  const box = document.createElement("div");
  box.className = "sv-msg sv-msg-user";
  box.textContent = text;
  chat.appendChild(box);
  chat.scrollTop = chat.scrollHeight;
}

function clearSuggestions() {
  document.getElementById("sv-suggestions").innerHTML = "";
}

// ===============
//  MAIN LOGIC
// ===============
let ALL_QUESTIONS = [];

// بعد كل جواب يجب أن نسأل: هل أجاب هذا على سؤالك ؟
function showFeedbackButtons() {
  const chat = document.getElementById("sv-chat-window");

  const wrapper = document.createElement("div");
  wrapper.className = "sv-msg sv-msg-bot";

  wrapper.innerHTML = `
    <div class="sv-feedback-title">✔️ Est-ce que cela répond à votre question ?</div>
    <div class="sv-feedback-buttons">
      <button class="sv-yes-btn">Oui</button>
      <button class="sv-no-btn">Non</button>
    </div>
  `;

  chat.appendChild(wrapper);
  chat.scrollTop = chat.scrollHeight;

  wrapper.querySelector(".sv-yes-btn").onclick = handleYes;
  wrapper.querySelector(".sv-no-btn").onclick = handleNo;
}

// YES → نرجع لقائمة الأسئلة الأولى
function handleYes() {
  addBotMessage("Ravi de vous aider ! 😊<br>Voulez-vous poser une autre question ?");

  const chat = document.getElementById("sv-chat-window");

  const btn = document.createElement("button");
  btn.textContent = "Poser une autre question";
  btn.className = "sv-option-chip";

  btn.onclick = () => {
    loadInitialSuggestions();
  };

  const box = document.createElement("div");
  box.className = "sv-msg sv-msg-bot";
  box.appendChild(btn);
  chat.appendChild(box);
  chat.scrollTop = chat.scrollHeight;
}

// NO → نتحول مباشرة إلى /messages
function handleNo() {
  addBotMessage("Je comprends ! Nous sommes là pour vous aider ❤️");

  const chat = document.getElementById("sv-chat-window");
  const btn = document.createElement("button");
  btn.textContent = "Contact Support";
  btn.className = "sv-option-chip";

  btn.onclick = () => {
    window.location.href = "/messages";
  };

  const box = document.createElement("div");
  box.className = "sv-msg sv-msg-bot";
  box.appendChild(btn);
  chat.appendChild(box);
  chat.scrollTop = chat.scrollHeight;
}

// ===============
//  DISPLAY SUGGESTED QUESTIONS
// ===============
function loadInitialSuggestions() {
  const suggestions = document.getElementById("sv-suggestions");
  suggestions.innerHTML = "";

  ALL_QUESTIONS.forEach(q => {
    const chip = document.createElement("button");
    chip.className = "sv-question-chip";
    chip.textContent = q.label;

    chip.onclick = () => selectQuestion(q);

    suggestions.appendChild(chip);
  });
}

// ===============
//  WHEN USER SELECTS QUESTION
// ===============
function selectQuestion(q) {
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

    const inner = document.createElement("div");
    inner.className = "sv-options-wrapper";

    const title = document.createElement("div");
    title.className = "sv-options-title";
    title.textContent = "Choisissez un cas :";
    inner.appendChild(title);

    Object.entries(q.options).forEach(([label, data]) => {
      const btn = document.createElement("button");
      btn.className = "sv-option-chip";
      btn.textContent = label;

      btn.onclick = () => {
        addUserMessage(label);
        addBotMessage(data.answer || "...");
        showFeedbackButtons();
      };

      inner.appendChild(btn);
    });

    box.appendChild(inner);
    chat.appendChild(box);
    chat.scrollTop = chat.scrollHeight;
  }
}

// ===============
//  INITIAL LOAD
// ===============
document.addEventListener("DOMContentLoaded", async () => {
  const data = await loadTree();
  const sections = data.sections || [];

  sections.forEach(section => {
    const faqs = section.faqs;
    if (!Array.isArray(faqs)) {
      Object.entries(faqs).forEach(([question, obj]) => {
        ALL_QUESTIONS.push({
          label: question,
          answer: obj.answer,
          options: obj.options || null
        });
      });
    } else {
      faqs.forEach(item => {
        ALL_QUESTIONS.push({
          label: item.question,
          answer: item.answer,
          options: null
        });
      });
    }
  });

  // أول رسالة
  addBotMessage("👋 Bonjour! Je suis l’assistant Sevor.<br>Choisissez une question ci-dessous pour commencer.");

  loadInitialSuggestions();
});
