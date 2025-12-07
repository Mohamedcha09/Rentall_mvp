// 1) Load JSON tree from backend
async function loadTree() {
  const res = await fetch("/chatbot/tree");
  return await res.json();
}

// 2) Helpers to add messages
function addBotMessage(chatWindow, html) {
  const msg = document.createElement("div");
  msg.className = "sv-msg sv-msg-bot";
  msg.innerHTML = html;
  chatWindow.appendChild(msg);
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

function addUserMessage(chatWindow, text) {
  const msg = document.createElement("div");
  msg.className = "sv-msg sv-msg-user";
  msg.textContent = text;
  chatWindow.appendChild(msg);
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

document.addEventListener("DOMContentLoaded", async () => {
  const chatWindow   = document.getElementById("sv-chat-window");
  const suggestions  = document.getElementById("sv-suggestions");

  if (!chatWindow || !suggestions) return;

  // 🧠 3) Load data from tree.json
  const data = await loadTree();
  const sections = data.sections || [];

  // نحول كل الأسئلة إلى قائمة بسيطة
  const allQuestions = [];

  sections.forEach(section => {
    const faqs = section.faqs;

    // CASE 1: faqs = object (question → {answer, options})
    if (!Array.isArray(faqs)) {
      Object.entries(faqs).forEach(([question, obj]) => {
        allQuestions.push({
          label: question,
          answer: obj.answer || null,
          options: obj.options || null
        });
      });
    }
    // CASE 2: faqs = array of {question, answer}
    else {
      faqs.forEach(item => {
        allQuestions.push({
          label: item.question,
          answer: item.answer || null,
          options: null
        });
      });
    }
  });

  // 4) رسالة ترحيب أولى (بوت)
  addBotMessage(
    chatWindow,
    "👋 Bonjour! Je suis l’assistant Sevor.<br>Choisissez une question fréquente ci-dessous pour commencer."
  );

  // 5) نرسم الـ chips للأسئلة
  allQuestions.forEach(q => {
    const chip = document.createElement("button");
    chip.className = "sv-question-chip";
    chip.textContent = q.label;

    chip.onclick = () => handleQuestionClick(chatWindow, q);

    suggestions.appendChild(chip);
  });
});

// 6) عند الضغط على سؤال
function handleQuestionClick(chatWindow, q) {
  // رسالة المستخدم
  addUserMessage(chatWindow, q.label);

  // جواب البوت الأساسي
  if (q.answer) {
    addBotMessage(chatWindow, q.answer);
  }

  // إذا كان عنده خيارات (options)
  if (q.options) {
    const wrapper = document.createElement("div");
    wrapper.className = "sv-msg sv-msg-bot";

    const inner = document.createElement("div");
    inner.className = "sv-options-wrapper";

    const title = document.createElement("div");
    title.className = "sv-options-title";
    title.textContent = "Choisissez un cas :";
    inner.appendChild(title);

    Object.entries(q.options).forEach(([optLabel, optData]) => {
      const btn = document.createElement("button");
      btn.className = "sv-option-chip";
      btn.textContent = optLabel;

      btn.onclick = () => {
        // المستخدم يختار الخيار
        addUserMessage(chatWindow, optLabel);
        // البوت يرد بالجواب
        addBotMessage(chatWindow, optData.answer || "...");
      };

      inner.appendChild(btn);
    });

    wrapper.appendChild(inner);
    chatWindow.appendChild(wrapper);
    chatWindow.scrollTop = chatWindow.scrollHeight;
  }
}
