// ===============================
//  SEVOR CHATBOT ENGINE
// ===============================

let SV_TREE = null;

// HTML Elements
const panel = document.getElementById("sv-chatbot-panel");
const toggleBtn = document.getElementById("sv-chatbot-toggle");
const closeBtn = document.querySelector(".sv-chatbot-close");

const sectionList = document.getElementById("sv-chatbot-section-list");
const questionList = document.getElementById("sv-chatbot-question-list");
const answerBox = document.getElementById("sv-chatbot-answer-inner");

// ===============================
//  PANEL OPEN / CLOSE
// ===============================
toggleBtn.onclick = () => {
  panel.hidden = !panel.hidden;
  if (!panel.hidden) loadSections();
};

closeBtn.onclick = () => {
  panel.hidden = true;
};

// ===============================
//  FETCH JSON TREE
// ===============================
async function loadTree() {
  if (SV_TREE) return SV_TREE;
  try {
    const res = await fetch("/chatbot/tree");
    SV_TREE = await res.json();
    return SV_TREE;
  } catch (err) {
    console.error("Chatbot JSON error:", err);
  }
}

async function loadSections() {
  const data = await loadTree();
  sectionList.innerHTML = "";
  questionList.innerHTML = "";
  answerBox.innerHTML = `<div class="sv-chatbot-empty">Select a question to view the answer.</div>`;

  Object.keys(data).forEach((section) => {
    const li = document.createElement("li");
    li.textContent = section;
    li.className = "sv-chatbot-pill";
    li.onclick = () => selectSection(section);
    sectionList.appendChild(li);
  });
}

// ===============================
//  SELECT SECTION
// ===============================
function selectSection(sectionName) {
  const sectionData = SV_TREE[sectionName];

  // Highlight selection
  [...sectionList.children].forEach((el) => el.classList.remove("is-active"));
  [...sectionList.children]
    .find((el) => el.textContent === sectionName)
    ?.classList.add("is-active");

  // Reset column 2 + 3
  questionList.innerHTML = "";
  answerBox.innerHTML = `<div class="sv-chatbot-empty">Select a question to view the answer.</div>`;

  const questions = Object.keys(sectionData);

  questions.forEach((q) => {
    const li = document.createElement("li");
    li.textContent = q;
    li.className = "sv-chatbot-question";
    li.onclick = () => selectQuestion(sectionName, q);
    questionList.appendChild(li);
  });
}

// ===============================
//  SELECT QUESTION
// ===============================
function selectQuestion(sectionName, questionText) {
  const questionData = SV_TREE[sectionName][questionText];

  // Highlight selection
  [...questionList.children].forEach((el) =>
    el.classList.remove("is-active")
  );
  [...questionList.children]
    .find((el) => el.textContent === questionText)
    ?.classList.add("is-active");

  // If the question has simple answer
  if (questionData.answer) {
    showAnswer(questionData.answer);
    return;
  }

  // If question has options (sub-questions)
  if (questionData.options) {
    showOptions(sectionName, questionText, questionData.options);
    return;
  }
}

// ===============================
//  SHOW SIMPLE ANSWER
// ===============================
function showAnswer(text) {
  answerBox.innerHTML = "";
  const div = document.createElement("div");
  div.className = "sv-chatbot-answer-text";
  div.textContent = text;
  answerBox.appendChild(div);
}

// ===============================
//  SHOW SUB OPTIONS
// ===============================
function showOptions(sectionName, questionText, options) {
  answerBox.innerHTML = "";

  const title = document.createElement("div");
  title.className = "sv-chatbot-answer-text";
  title.style.fontWeight = "700";
  title.style.marginBottom = "8px";
  title.textContent = "Select a more specific question:";
  answerBox.appendChild(title);

  Object.keys(options).forEach((opt) => {
    const div = document.createElement("div");
    div.className = "sv-chatbot-option";
    div.textContent = opt;

    div.onclick = () => {
      // Highlight active option
      [...answerBox.querySelectorAll(".sv-chatbot-option")].forEach((el) =>
        el.classList.remove("is-active")
      );
      div.classList.add("is-active");

      // Show answer
      showAnswer(options[opt].answer);
    };

    answerBox.appendChild(div);
  });
}
