// ===============================
//  LOAD CHATBOT TREE
// ===============================
let SV_TREE = null;

async function loadTree() {
  if (SV_TREE) return SV_TREE;
  try {
    const res = await fetch("/chatbot/tree");
    SV_TREE = await res.json();
    return SV_TREE;
  } catch (err) {
    console.error("Failed to load chatbot tree:", err);
  }
}

// ===============================
//  ELEMENTS
// ===============================
const sectionList = document.getElementById("sv-chatbot-section-list");
const questionList = document.getElementById("sv-chatbot-question-list");
const answerBox = document.getElementById("sv-chatbot-answer-inner");

// ===============================
//  INITIAL LOAD
// ===============================
document.addEventListener("DOMContentLoaded", () => {
  loadSections();
});

// ===============================
//  LOAD SECTIONS
// ===============================
async function loadSections() {
  const data = await loadTree();
  if (!data) return;

  sectionList.innerHTML = "";
  questionList.innerHTML = "";
  answerBox.innerHTML = `<div class="sv-chatbot-empty">Select a question to view the answer.</div>`;

  Object.keys(data).forEach(section => {
    const li = document.createElement("li");
    li.className = "sv-chatbot-pill";
    li.textContent = section;

    li.onclick = () => selectSection(section);

    sectionList.appendChild(li);
  });
}

// ===============================
//  SELECT SECTION
// ===============================
function selectSection(sectionName) {
  const sectionData = SV_TREE[sectionName];

  [...sectionList.children].forEach(el => el.classList.remove("is-active"));
  const found = [...sectionList.children].find(el => el.textContent === sectionName);
  if (found) found.classList.add("is-active");

  questionList.innerHTML = "";
  answerBox.innerHTML = `<div class="sv-chatbot-empty">Select a question to view the answer.</div>`;

  Object.keys(sectionData).forEach(q => {
    const li = document.createElement("li");
    li.className = "sv-chatbot-question";
    li.textContent = q;

    li.onclick = () => selectQuestion(sectionName, q);

    questionList.appendChild(li);
  });
}

// ===============================
//  SELECT QUESTION
// ===============================
function selectQuestion(sectionName, questionText) {
  const qData = SV_TREE[sectionName][questionText];

  [...questionList.children].forEach(el => el.classList.remove("is-active"));
  const found = [...questionList.children].find(el => el.textContent === questionText);
  if (found) found.classList.add("is-active");

  if (qData.answer) {
    showAnswer(qData.answer);
    return;
  }

  if (qData.options) {
    showOptions(qData.options);
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
function showOptions(options) {
  answerBox.innerHTML = "";

  const title = document.createElement("div");
  title.className = "sv-chatbot-answer-text";
  title.style.fontWeight = "700";
  title.textContent = "Select a more specific question:";
  title.style.marginBottom = "10px";
  answerBox.appendChild(title);

  Object.keys(options).forEach(opt => {
    const div = document.createElement("div");
    div.className = "sv-chatbot-option";
    div.textContent = opt;

    div.onclick = () => {
      [...answerBox.querySelectorAll(".sv-chatbot-option")]
        .forEach(el => el.classList.remove("is-active"));

      div.classList.add("is-active");
      showAnswer(options[opt].answer);
    };

    answerBox.appendChild(div);
  });
}
