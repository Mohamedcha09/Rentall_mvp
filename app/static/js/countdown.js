/**
 * app/static/js/countdown.js
 * ---------------------------
 * سكربت بسيط لعرض عدّاد تنازلي لأي ديدلاين (Deadline)
 * يُستخدم في صفحات مثل:
 *   - المهلة قبل الإفراج التلقائي عن الوديعة (48h)
 *   - المهلة المتبقية للمالك لفتح بلاغ
 *   - المهلة المتبقية للـ Deposit Manager لاتخاذ القرار
 *
 * الطريقة:
 *   <span class="countdown" data-deadline="{{ booking.deadline_owner_report_at }}"></span>
 *
 * عند تحميل الصفحة سيُحوّل التاريخ إلى عدّاد تنازلي حي.
 */

function initCountdowns() {
  const els = document.querySelectorAll('.countdown');
  if (!els.length) return;

  els.forEach(el => {
    const deadlineStr = el.getAttribute('data-deadline');
    if (!deadlineStr) return;

    const deadline = new Date(deadlineStr);
    if (isNaN(deadline)) {
      el.textContent = "—";
      return;
    }

    function update() {
      const now = new Date();
      const diff = deadline - now;

      if (diff <= 0) {
        el.textContent = "انتهت المهلة ⏰";
        el.classList.add('text-danger');
        return;
      }

      const d = Math.floor(diff / (1000 * 60 * 60 * 24));
      const h = Math.floor((diff / (1000 * 60 * 60)) % 24);
      const m = Math.floor((diff / (1000 * 60)) % 60);
      const s = Math.floor((diff / 1000) % 60);

      const parts = [];
      if (d > 0) parts.push(`${d}ي`);
      if (h > 0 || d > 0) parts.push(`${h}س`);
      parts.push(`${m}د`);
      if (d === 0 && h === 0) parts.push(`${s}ث`);

      el.textContent = parts.join(" ");
      requestAnimationFrame(() => setTimeout(update, 1000));
    }

    update();
  });
}

// تشغيل العدّادات عند تحميل الصفحة
document.addEventListener('DOMContentLoaded', initCountdowns);