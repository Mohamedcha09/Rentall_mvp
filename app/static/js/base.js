/* =========================================
   TYPEAHEAD SEARCH (Home Search Input)
========================================= */

let typeaheadTimer = null;
const typeaheadInput = document.getElementById("searchInput");
const typeaheadPanel = document.getElementById("typeaheadPanel");

if (typeaheadInput) {
  typeaheadInput.addEventListener("input", () => {
    const q = typeaheadInput.value.trim();

    // Hide when empty
    if (!q) {
      typeaheadPanel.style.display = "none";
      return;
    }

    clearTimeout(typeaheadTimer);

    typeaheadTimer = setTimeout(async () => {
      try {
        const r = await fetch(`/api/typeahead?q=${encodeURIComponent(q)}`);
        const data = await r.json();

        typeaheadPanel.innerHTML = "";

        if (!data || !data.length) {
          typeaheadPanel.style.display = "none";
          return;
        }

        data.forEach(item => {
          const div = document.createElement("div");
          div.className = "typeahead-item";
          div.textContent = item.label;
          div.onclick = () => {
            window.location.href = item.url;
          };
          typeaheadPanel.appendChild(div);
        });

        typeaheadPanel.style.display = "block";
      } catch (err) {
        console.error("Typeahead error:", err);
      }
    }, 250);
  });
}

/* Close panel on outside click */
document.addEventListener("click", (ev) => {
  if (!typeaheadPanel || !typeaheadInput) return;
  if (!typeaheadPanel.contains(ev.target) && ev.target !== typeaheadInput) {
    typeaheadPanel.style.display = "none";
  }
});


/* =========================================
   CITY SUGGEST AUTOCOMPLETE
========================================= */

const cityInput = document.getElementById("cityInput");
const citySuggest = document.getElementById("citySuggest");

if (cityInput) {
  cityInput.addEventListener("input", async () => {
    const query = cityInput.value.trim();

    if (!query) {
      citySuggest.innerHTML = "";
      citySuggest.style.display = "none";
      return;
    }

    try {
      const r = await fetch(`/api/cities?q=${encodeURIComponent(query)}`);
      const data = await r.json();

      citySuggest.innerHTML = "";

      if (!data || !data.length) {
        citySuggest.style.display = "none";
        return;
      }

      data.forEach(c => {
        const div = document.createElement("div");
        div.className = "city-suggest-item";
        div.textContent = c.city;
        div.onclick = () => {
          cityInput.value = c.city;
          citySuggest.style.display = "none";
        };
        citySuggest.appendChild(div);
      });

      citySuggest.style.display = "block";
    } catch (err) {
      console.error("City suggest error:", err);
    }
  });
}

document.addEventListener("click", (ev) => {
  if (!citySuggest || !cityInput) return;
  if (!citySuggest.contains(ev.target) && ev.target !== cityInput) {
    citySuggest.style.display = "none";
  }
});

/* =========================================
   PROFILE SHEET (Bottom Panel)
========================================= */

const profileSheet = document.getElementById("profileSheet");
const profileScrim = document.getElementById("profileScrim");

function sheetOpen() {
  if (!profileSheet || !profileScrim) return;
  profileSheet.classList.add("is-open");
  profileScrim.classList.add("is-open");
}

function sheetClose() {
  if (!profileSheet || !profileScrim) return;
  profileSheet.classList.remove("is-open");
  profileScrim.classList.remove("is-open");
}

if (profileScrim) {
  profileScrim.addEventListener("click", sheetClose);
}

/* Escape key closes sheet */
document.addEventListener("keydown", (ev) => {
  if (ev.key === "Escape") sheetClose();
});

/* Open sheet from tabbar (mobile only) */
const profBtn = document.querySelector('.mobile-tabbar a[href="/profile"]');

if (profBtn) {
  profBtn.addEventListener("click", (ev) => {
    if (window.matchMedia("(max-width: 768px)").matches) {
      ev.preventDefault();
      sheetOpen();
    }
  });
}

/* =========================================
   AUTO TABBAR LIFT (Avoid overlap with FAB)
========================================= */

function computeTabbarLift() {
  try {
    const tabbar = document.querySelector(".mobile-tabbar");
    if (!tabbar) return;

    const rect = tabbar.getBoundingClientRect();
    const h = rect.height || 64;

    document.documentElement.style.setProperty("--sv-tabbar", h + "px");

  } catch (e) {
    console.error("tabbar lift error:", e);
  }
}

window.addEventListener("resize", computeTabbarLift);
window.addEventListener("load", computeTabbarLift);

computeTabbarLift();

/* =========================================
   FIX SAFE AREA (top/bottom)
========================================= */

function applySafeArea() {
  const top = parseInt(getComputedStyle(document.documentElement).getPropertyValue("--safe-top")) || 0;
  const bottom = parseInt(getComputedStyle(document.documentElement).getPropertyValue("--safe-bottom")) || 0;

  document.documentElement.style.setProperty("--safe-top", top + "px");
  document.documentElement.style.setProperty("--safe-bottom", bottom + "px");
}

applySafeArea();

/* =========================================
   NOTIFICATIONS — POPUP PANEL
========================================= */

const notifOpen = document.getElementById("notifOpen");
const notifPanel = document.getElementById("notifPanel");

if (notifOpen && notifPanel) {
  notifOpen.addEventListener("click", (ev) => {
    ev.stopPropagation();

    if (notifPanel.style.display === "block") {
      notifPanel.style.display = "none";
    } else {
      notifPanel.style.display = "block";
    }
  });

  /* Close notif panel when clicking outside */
  document.addEventListener("click", (ev) => {
    if (!notifPanel.contains(ev.target) && ev.target !== notifOpen) {
      notifPanel.style.display = "none";
    }
  });
}


/* =========================================
   NOTIFICATIONS — POLLING (every 20s)
========================================= */

async function pollNotifications() {
  const badge = document.getElementById("notifBadge");
  if (!badge) return;

  try {
    const r = await fetch("/api/notifications/unread");
    const data = await r.json();

    const unread = data.unread || 0;

    if (unread > 0) {
      badge.textContent = unread;
      badge.style.display = "flex";
    } else {
      badge.style.display = "none";
    }

  } catch (err) {
    console.error("notif poll error:", err);
  }
}

/* Run immediately */
pollNotifications();

/* Every 20 seconds */
setInterval(pollNotifications, 20000);


/* =========================================
   LOAD NOTIFICATION LIST WHEN PANEL OPENS
========================================= */

async function loadNotifList() {
  if (!notifPanel) return;

  try {
    const r = await fetch("/api/notifications/list");
    const data = await r.json();

    notifPanel.innerHTML = "";

    if (!data || !data.length) {
      notifPanel.innerHTML = `<div class="text-muted" style="padding:14px;text-align:center;">No notifications</div>`;
      return;
    }

    data.forEach(n => {
      const div = document.createElement("div");
      div.className = "notif-item";
      div.textContent = n.message;
      div.onclick = () => {
        window.location.href = n.url;
      };
      notifPanel.appendChild(div);
    });

  } catch (err) {
    console.error("notif list error:", err);
  }
}

if (notifOpen) {
  notifOpen.addEventListener("click", loadNotifList);
}

/* =========================================
   QUICK MENU (Floating Mini Menu)
========================================= */

const quickMenu = document.getElementById("quickMenu");
let quickMenuOpen = false;

function toggleQuickMenu() {
  if (!quickMenu) return;

  quickMenuOpen = !quickMenuOpen;

  if (quickMenuOpen) {
    quickMenu.style.display = "flex";
    quickMenu.classList.add("is-open");
  } else {
    quickMenu.classList.remove("is-open");
    setTimeout(() => {
      quickMenu.style.display = "none";
    }, 180);
  }
}

/* Toggle from FAB */
const fabAdd = document.getElementById("fabAdd");

if (fabAdd && quickMenu) {
  fabAdd.addEventListener("click", (ev) => {
    ev.preventDefault();
    toggleQuickMenu();
  });
}

/* Close menu when clicking outside */
document.addEventListener("click", (ev) => {
  if (!quickMenu) return;
  if (!quickMenu.contains(ev.target) && ev.target !== fabAdd) {
    quickMenuOpen = false;
    quickMenu.classList.remove("is-open");
    quickMenu.style.display = "none";
  }
});


/* =========================================
   MOBILE TABBAR SCROLL BEHAVIOR
   Hide tabbar when scrolling down, show when up
========================================= */

let lastScroll = 0;
const tabbar = document.querySelector(".mobile-tabbar");

window.addEventListener("scroll", () => {
  if (!tabbar) return;

  const y = window.scrollY;

  if (y > lastScroll + 20) {
    // scrolling down → hide
    document.documentElement.style.setProperty("--tabbar-lift", "-80px");
  } else if (y < lastScroll - 20) {
    // scrolling up → show
    document.documentElement.style.setProperty("--tabbar-lift", "0px");
  }

  lastScroll = y;
});


/* =========================================
   FAB FOLLOW TABBAR (on scroll)
========================================= */

function updateFabPosition() {
  const fab = document.getElementById("fabAdd");
  if (!fab || !tabbar) return;

  const lift = getComputedStyle(document.documentElement).getPropertyValue("--tabbar-lift");

  // FAB moves with the tabbar
  fab.style.transform = `translateY(${lift})`;
}

window.addEventListener("scroll", updateFabPosition);
window.addEventListener("resize", updateFabPosition);
setInterval(updateFabPosition, 500);


/* =========================================
   CLOSE SHEETS OR MENUS WHEN NAVIGATING
========================================= */

document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "hidden") {
    toggleQuickMenu(false);
    sheetClose();
  }
});

/* =========================================
   IMMERSIVE BACK BUTTON LOGIC
========================================= */

// Attach immersive back button if found
document.addEventListener("DOMContentLoaded", () => {
  const backBtn = document.querySelector(".immersive-back");
  if (backBtn) {
    backBtn.addEventListener("click", (e) => {
      e.preventDefault();
      history.back();
    });
  }
});


/* =========================================
   SAFE-AREA CALCULATION (iOS Notch Fix)
========================================= */

(function computeSafeArea() {
  var root = document.documentElement;

  function computeSafe() {
    var safe = 0;
    try {
      var probe = document.createElement("div");
      probe.style.cssText =
        "position:fixed; bottom:0; left:0; right:0; " +
        "height:constant(safe-area-inset-bottom); " +
        "height:env(safe-area-inset-bottom); " +
        "pointer-events:none; opacity:0;";
      document.body.appendChild(probe);
      safe = Math.max(0, probe.getBoundingClientRect().height || 0);
      probe.remove();
    } catch (_) {}

    var isIOS = /iphone|ipod|ipad/i.test(navigator.userAgent);
    var isStandalone =
      window.navigator.standalone === true ||
      (window.matchMedia &&
        window.matchMedia("(display-mode: standalone)").matches);

    if (isIOS && isStandalone && safe < 8) safe = 16;

    root.style.setProperty("--safe-bottom", safe + "px");
  }

  computeSafe();
  window.addEventListener("resize", computeSafe);

  if (window.visualViewport) {
    visualViewport.addEventListener("resize", computeSafe);
    visualViewport.addEventListener("scroll", computeSafe);
  }
})();


/* =========================================
   FIX BODY data-path (used for hiding topbar in /messages)
========================================= */

document.addEventListener("DOMContentLoaded", function () {
  try {
    document.body.setAttribute("data-path", location.pathname);
  } catch (e) {}
});


/* =========================================
   FIRST VISIT — COUNTRY PICKER OVERLAY
========================================= */

// يعتمد على وجود geo_pick.html داخل الصفحة
(function initCountryPicker(){
  try {
    const exists = document.querySelector("#geoPicker");
    if (!exists) return;

    const closeBtn = exists.querySelector(".geo-close");
    closeBtn?.addEventListener("click", () => {
      exists.style.display = "none";
    });

  } catch (_) {}
})();


/* =========================================
   UPDATE TABBAR OFFSET (duplicate from HTML logic)
========================================= */

(function(){
  function setFabOffset(){
    var bar = document.querySelector('.mobile-tabbar');
    var h = 64;
    if (bar){
      var r = bar.getBoundingClientRect();
      h = Math.max(48, Math.round(r.height || 64));
    }
    document.documentElement.style.setProperty('--sv-tabbar', h + 'px');
  }
  setFabOffset();
  window.addEventListener('resize', setFabOffset);
  window.addEventListener('orientationchange', setFabOffset);
  setTimeout(setFabOffset, 100);
  setTimeout(setFabOffset, 500);
})();
