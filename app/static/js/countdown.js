// app/static/js/countdown.js
// عدّاد تنازلي عام.
// الاستعمال في أي قالب:
//   <span class="countdown" data-deadline="{{ dispute_deadline_iso }}"></span>
// أو
//   <span data-countdown data-deadline-iso="{{ dispute_deadline_iso }}"></span>
//
// سيعرض: "01ي 05س 22د 10ث" أو "انتهى الوقت" عند الانتهاء.

(function () {
  "use strict";

  // تنسيق رقمين (مثلاً 7 -> "07")
  function pad2(n) {
    n = Math.floor(Math.abs(n));
    return n < 10 ? "0" + n : "" + n;
  }

  // يحاول قراءة قيمة ISO من عنصر
  function readISO(el) {
    // أولوية: data-deadline-iso, data-deadline, data-deadline_iso
    const v =
      el.getAttribute("data-deadline-iso") ||
      el.getAttribute("data-deadline") ||
      el.getAttribute("data-deadline_iso") ||
      "";
    return (v || "").trim();
  }

  // يحول ISO إلى كائن Date (مع تحمّل بسيط للأخطاء)
  function parseISO(iso) {
    if (!iso) return null;
    try {
      // بعض القوالب قد تمرر "None" أو "null"
      if (/^(none|null|undefined)$/i.test(iso)) return null;
      const d = new Date(iso);
      if (isNaN(d.getTime())) return null;
      return d;
    } catch (_) {
      return null;
    }
  }

  // يحسب الفرق ويعيد نص عربي مختصر
  function formatRemaining(ms) {
    if (ms <= 0) return "انتهى الوقت";
    const totalSec = Math.floor(ms / 1000);
    const d = Math.floor(totalSec / 86400);
    const h = Math.floor((totalSec % 86400) / 3600);
    const m = Math.floor((totalSec % 3600) / 60);
    const s = totalSec % 60;

    // شكل مختصر: 01ي 05س 22د 10ث — نخفي الأيام إن كانت 0
    let out = [];
    if (d > 0) out.push(pad2(d) + "ي");
    out.push(pad2(h) + "س");
    out.push(pad2(m) + "د");
    out.push(pad2(s) + "ث");
    return out.join(" ");
  }

  // يحدّث عنصر واحد
  function tickElement(el, deadline) {
    const now = Date.now();
    const ms = deadline.getTime() - now;
    el.textContent = formatRemaining(ms);
    if (ms <= 0) {
      el.classList.add("countdown-finished");
      return false; // توقّف هذا العنصر
    }
    return true;
  }

  // يهيّئ عدّاد لعنصر معيّن
  function initOne(el) {
    if (!el || el.__countdownInit) return;
    const iso = readISO(el);
    const deadline = parseISO(iso);
    if (!deadline) {
      el.textContent = el.getAttribute("data-countdown-empty") || ""; // اتركه فارغاً
      return;
    }
    el.__countdownInit = true;
    // أول تحديث فوراً
    tickElement(el, deadline);
    // ثم كل ثانية
    const iv = setInterval(function () {
      const alive = tickElement(el, deadline);
      if (!alive) clearInterval(iv);
    }, 1000);
  }

  // يبحث عن كل العناصر المطابقة ويبدأها
  function initAll(root) {
    root = root || document;
    const nodes = root.querySelectorAll(
      ".countdown[data-deadline], .countdown[data-deadline-iso], [data-countdown][data-deadline], [data-countdown][data-deadline-iso]"
    );
    nodes.forEach(initOne);
  }

  // تشغيل عند جاهزية DOM
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      initAll(document);
    });
  } else {
    initAll(document);
  }

  // دعم العناصر المُضافة ديناميكياً
  const mo = new MutationObserver(function (muts) {
    for (const m of muts) {
      if (m.addedNodes && m.addedNodes.length) {
        m.addedNodes.forEach(function (n) {
          if (!(n instanceof Element)) return;
          if (
            n.matches &&
            (n.matches(".countdown[data-deadline], .countdown[data-deadline-iso]") ||
              n.matches("[data-countdown][data-deadline], [data-countdown][data-deadline-iso]"))
          ) {
            initOne(n);
          }
          // أيضاً افحص داخله
          initAll(n);
        });
      }
    }
  });
  try {
    mo.observe(document.documentElement || document.body, {
      childList: true,
      subtree: true,
    });
  } catch (_) {
    // لا شيء
  }
})();