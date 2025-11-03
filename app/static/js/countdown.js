// app/static/js/countdown.js
// عدّاد تنازلي عام مع إيقاف ذكي أثناء المودالات أو حين تكون الصفحة بالخلفية.
// طريقة الاستخدام في القوالب:
//   <span class="countdown" data-deadline="{{ dispute_deadline_iso }}"></span>
// أو
//   <span data-countdown data-deadline-iso="{{ dispute_deadline_iso }}"></span>

(function () {
  "use strict";

  /* ========== Helpers ========== */
  function modalOpen() {
    // Bootstrap يضيف .modal-open على الـbody عند فتح مودال
    // وبعض الحالات لا يضيفها بسرعة على iOS، فنتحقق أيضًا من .modal.show
    return (
      (typeof document !== "undefined" &&
        document.body &&
        document.body.classList.contains("modal-open")) ||
      !!document.querySelector(".modal.show")
    );
  }

  function pad2(n) {
    n = Math.floor(Math.abs(n));
    return n < 10 ? "0" + n : "" + n;
  }

  function readISO(el) {
    // أولوية: data-deadline-iso, data-deadline, data-deadline_iso
    const v =
      el.getAttribute("data-deadline-iso") ||
      el.getAttribute("data-deadline") ||
      el.getAttribute("data-deadline_iso") ||
      "";
    return (v || "").trim();
  }

  function parseISO(iso) {
    if (!iso) return null;
    try {
      if (/^(none|null|undefined)$/i.test(iso)) return null;
      const d = new Date(iso);
      if (isNaN(d.getTime())) return null;
      return d;
    } catch (_) {
      return null;
    }
  }

  function formatRemaining(ms) {
    if (ms <= 0) return "انتهى الوقت";
    const totalSec = Math.floor(ms / 1000);
    const d = Math.floor(totalSec / 86400);
    const h = Math.floor((totalSec % 86400) / 3600);
    const m = Math.floor((totalSec % 3600) / 60);
    const s = totalSec % 60;

    const out = [];
    if (d > 0) out.push(pad2(d) + "ي");
    out.push(pad2(h) + "س");
    out.push(pad2(m) + "د");
    out.push(pad2(s) + "ث");
    return out.join(" ");
  }

  /* ========== State ========== */
  // نخزن جميع العناصر الفعالة هنا لتحديثها بمؤقّت واحد.
  const active = new Set(); // عناصر {el, deadline}

  function addElement(el) {
    if (!el || el.__countdownInit) return;
    const iso = readISO(el);
    const deadline = parseISO(iso);
    el.__countdownInit = true;

    if (!deadline) {
      el.textContent = el.getAttribute("data-countdown-empty") || "";
      return;
    }
    active.add({ el, deadline });
    // أول تحديث فوري
    updateElement(el, deadline);
  }

  function updateElement(el, deadline) {
    const ms = deadline.getTime() - Date.now();
    el.textContent = formatRemaining(ms);
    if (ms <= 0) {
      el.classList.add("countdown-finished");
      return false; // انتهى
    }
    return true;
  }

  function scan(root) {
    root = root || document;
    const nodes = root.querySelectorAll(
      ".countdown[data-deadline], .countdown[data-deadline-iso], [data-countdown][data-deadline], [data-countdown][data-deadline-iso]"
    );
    nodes.forEach(addElement);
  }

  /* ========== Global Ticker (1 لكل الصفحة) ========== */
  let ticking = false;
  function tickAll() {
    if (ticking) return;
    ticking = true;

    // نستخدم setTimeout بدورة ~1s، ونوقف التحديث إذا كان مودال مفتوح أو الصفحة بالخلفية
    (function loop() {
      try {
        if (!document.hidden && !modalOpen()) {
          // نحدّث كل العناصر الفعّالة
          for (const obj of Array.from(active)) {
            const alive = updateElement(obj.el, obj.deadline);
            if (!alive) active.delete(obj);
          }
        }
      } catch (_) {
        // تجاهل أخطاء عرضية
      } finally {
        // إن لم يبق عناصر، نستمر أيضًا لكن التكلفة شبه صفرية
        setTimeout(loop, 1000);
      }
    })();
  }

  /* ========== Bootstrap events awareness ========== */
  // عندما يُغلق المودال، نفعل تحديثًا سريعًا
  document.addEventListener("hidden.bs.modal", function () {
    // تحديث فوري بعد الإغلاق
    for (const obj of Array.from(active)) {
      updateElement(obj.el, obj.deadline);
    }
  });

  // عند العودة للصفحة من الخلفية
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) {
      for (const obj of Array.from(active)) {
        updateElement(obj.el, obj.deadline);
      }
    }
  });

  /* ========== Init ========== */
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      scan(document);
      tickAll();
    });
  } else {
    scan(document);
    tickAll();
  }

  // التقط العناصر التي تُضاف لاحقًا
  try {
    const mo = new MutationObserver(function (muts) {
      for (const m of muts) {
        for (const n of m.addedNodes || []) {
          if (!(n instanceof Element)) continue;
          if (
            n.matches &&
            (n.matches(".countdown[data-deadline], .countdown[data-deadline-iso]") ||
              n.matches("[data-countdown][data-deadline], [data-countdown][data-deadline-iso]"))
          ) {
            addElement(n);
          }
          // وابحث داخلها أيضًا
          scan(n);
        }
      }
    });
    mo.observe(document.documentElement || document.body, {
      childList: true,
      subtree: true,
    });
  } catch (_) {
    // بيئات قديمة: نتجاهل المراقبة
  }
})();
