// Load JSON tree
async function loadTree() {
    const res = await fetch("/chatbot/tree");
    return await res.json();
}

document.addEventListener("DOMContentLoaded", async () => {

    const questionsBox = document.getElementById("sv-questions");
    const answerBox = document.getElementById("sv-answer");

    const data = await loadTree();
    const sections = data.sections;   // <-- الخلل هنا كان

    sections.forEach(section => {

        const faqs = section.faqs;

        // CASE 1: FAQs is an OBJECT
        if (!Array.isArray(faqs)) {
            Object.entries(faqs).forEach(([question, obj]) => {

                const div = document.createElement("div");
                div.className = "sv-question";
                div.textContent = question;

                div.onclick = () => {
                    answerBox.classList.remove("hidden");

                    if (obj.answer) {
                        answerBox.innerHTML = obj.answer;
                    }
                    else if (obj.options) {
                        answerBox.innerHTML = createOptionsHTML(obj.options);
                    }
                    else {
                        answerBox.innerHTML = "No answer found.";
                    }

                    window.scrollTo({ top: 0, behavior: "smooth" });
                };

                questionsBox.appendChild(div);
            });
        }

        // CASE 2: FAQs is an ARRAY
        else {
            faqs.forEach(item => {

                const div = document.createElement("div");
                div.className = "sv-question";
                div.textContent = item.question;

                div.onclick = () => {
                    answerBox.classList.remove("hidden");
                    answerBox.innerHTML = item.answer || "No answer found.";
                    window.scrollTo({ top: 0, behavior: "smooth" });
                };

                questionsBox.appendChild(div);
            });
        }

    });
});


// Helper: Render options list (Airbnb-style follow-up questions)
function createOptionsHTML(optionsObj) {
    let html = `<div class='sv-options-title'>Choisissez un cas :</div>`;

    Object.entries(optionsObj).forEach(([optName, optData]) => {
        html += `
            <div class='sv-option-item'>
                <strong>${optName}</strong><br>
                <div>${optData.answer}</div>
            </div>
            <br>
        `;
    });

    return html;
}
