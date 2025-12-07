// Load JSON tree
async function loadTree() {
  const res = await fetch("/chatbot/tree");
  return await res.json();
}

document.addEventListener("DOMContentLoaded", async () => {
  const questionsBox = document.getElementById("sv-questions");
  const answerBox = document.getElementById("sv-answer");

  const data = await loadTree();

  // Convert tree.json → simple list
  Object.keys(data).forEach(section => {
    const questions = data[section];

    Object.keys(questions).forEach(q => {
      const div = document.createElement("div");
      div.className = "sv-question";
      div.textContent = q;

      div.onclick = () => {
        answerBox.classList.remove("hidden");
        answerBox.innerHTML = questions[q].answer || "No answer found.";
        window.scrollTo({ top: 0, behavior: "smooth" });
      };

      questionsBox.appendChild(div);
    });

  });
});
