{% extends "base.html" %}
{% from "_badges.html" import render_badges %}
{% block content %}

<style>
  /* بطاقات وعناصر الواجهة */
  .glass-card{background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.12);border-radius:14px;backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);box-shadow:0 8px 24px rgba(0,0,0,.2);transition:transform .18s,box-shadow .18s,border-color .18s}
  .glass-card:hover{transform:translateY(-2px);box-shadow:0 14px 36px rgba(0,0,0,.28);border-color:rgba(255,255,255,.18)}
  .glass-btn{border:1px solid rgba(255,255,255,.18);background:linear-gradient(180deg,rgba(255,255,255,.10),rgba(255,255,255,.04));backdrop-filter:blur(6px);-webkit-backdrop-filter:blur(6px);color:#eaf0ff}
  .glass-btn:hover{border-color:rgba(255,255,255,.30);color:#fff}
  .chip{font-size:12px;padding:6px 10px;border-radius:999px;border:1px solid rgba(148,163,184,.25);background:rgba(148,163,184,.10)}
  .grid-items{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:16px}
  .item-img{width:100%;height:200px;object-fit:cover;display:block;background:rgba(0,0,0,.18)}
  @media (max-width:480px){.item-img{height:180px}}
  .price-badge{position:absolute;bottom:10px;left:10px;font-weight:800;padding:6px 10px;border-radius:12px;background:rgba(2,6,23,.65);border:1px solid rgba(148,163,184,.35);backdrop-filter:blur(6px)}
  .owner-line{display:flex;align-items:center;gap:8px;min-height:28px}
  .avatar{width:26px;height:26px;border-radius:50%;object-fit:cover;box-shadow:0 0 0 2px rgba(255,255,255,.12)}
  .toolbar{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
  .pill{padding:8px 12px;border-radius:999px;border:1px solid rgba(255,255,255,.12);background:rgba(255,255,255,.04);color:#eaf0ff;text-decoration:none}
  .pill.active{border-color:rgba(99,102,241,.6);background:rgba(99,102,241,.18)}

  /* ===== شريط الموقع (نفس روح home لكن باسم items-*) ===== */
  .items-locbar{
    --loc-bg:#fff;--loc-border:rgba(0,0,0,.08);--loc-shadow:0 8px 24px rgba(0,0,0,.06);
    --loc-radius:18px;--loc-pad:14px;--loc-primary:#5b4bff;--loc-primary-ink:#fff;--loc-danger:#e5484d;
    background:var(--loc-bg);border:1px solid var(--loc-border);border-radius:var(--loc-radius);
    box-shadow:var(--loc-shadow);padding:calc(var(--loc-pad) + 2px) var(--loc-pad);margin-block:16px
  }
  .items-locbar .form-control{height:48px;border-radius:999px;border:1px solid var(--loc-border);background:#fafafa;transition:border-color .2s,box-shadow .2s;padding-inline:16px}
  .items-locbar .form-control:focus{border-color:color-mix(in oklab,var(--loc-primary) 40%, #999);box-shadow:0 0 0 4px color-mix(in oklab,var(--loc-primary) 16%, transparent);background:#fff}
  #itemsUseGPS.btn{height:48px;border-radius:999px;border:1px solid var(--loc-border);background:#f6f7fb;color:#111;font-weight:700}
  #itemsUseGPS.btn:hover{background:#eef0f6}
  #itemsClearGPS.btn{height:auto;border:none;padding:6px 8px 0;color:var(--loc-danger);font-weight:700;text-decoration:none}
  #itemsClearGPS.btn:hover{opacity:.85}
  .items-locbar .btn.btn-primary{height:48px;border-radius:999px;background:var(--loc-primary);color:var(--loc-primary-ink);border:none;font-weight:800;box-shadow:0 10px 24px rgba(91,75,255,.18)}
  #itemsCitySugg{border-radius:12px;border:1px solid var(--loc-border);box-shadow:var(--loc-shadow);overflow:hidden}
  #itemsCitySugg>div{font-size:.95rem;color:#111;border-top:1px solid rgba(0,0,0,.04)}
  #itemsCitySugg>div:first-child{border-top:none}
  #itemsCitySugg>div:hover{background:#f7f7fb}
</style>

<section class="container" style="max-width:1200px;margin:auto">

  <div class="d-flex align-items-center justify-content-between mb-3" style="gap:8px">
    <div class="d-flex align-items-center" style="gap:10px">
      <h2 class="mb-0">العناصر</h2>
      <span class="chip">
        {% if current_category %}التصنيف: <b>{{ current_category }}</b>{% else %}كل التصنيفات{% endif %}
      </span>
      <span class="chip">الترتيب: {% if current_sort == 'new' %}الأحدث{% else %}عشوائي{% endif %}</span>
    </div>

    <div class="toolbar">
      <a class="pill {% if not current_category %}active{% endif %}" href="/items">الكل</a>
      {% for cat in categories %}
        {% set key = cat.key if cat.key is defined else (cat.code if cat.code is defined else cat) %}
        {% set label = cat.label if cat.label is defined else (cat.name if cat.name is defined else key) %}
        <a class="pill {% if current_category == key %}active{% endif %}" href="/items?category={{ key }}{% if selected_city %}&city={{ selected_city | urlencode }}{% endif %}{% if lat %}&lat={{ lat }}{% endif %}{% if lng %}&lng={{ lng }}{% endif %}">{{ label }}</a>
      {% endfor %}
      {% set base_q = (current_category and ('&category=' ~ current_category)) or '' %}
      <a class="pill {% if current_sort != 'new' %}active{% endif %}" href="/items?sort=random{{ base_q }}{% if selected_city %}&city={{ selected_city | urlencode }}{% endif %}{% if lat %}&lat={{ lat }}{% endif %}{% if lng %}&lng={{ lng }}{% endif %}">عشوائي</a>
      <a class="pill {% if current_sort == 'new' %}active{% endif %}" href="/items?sort=new{{ base_q }}{% if selected_city %}&city={{ selected_city | urlencode }}{% endif %}{% if lat %}&lat={{ lat }}{% endif %}{% if lng %}&lng={{ lng }}{% endif %}">الأحدث</a>
    </div>
  </div>

  <!-- ✅ شريط الموقع (مدينة / استخدم موقعي / إلغاء / تطبيق) -->
  <form class="row g-2 align-items-center items-locbar" id="itemsLocForm" action="/items" method="get" role="search">
    <div class="col-12 col-md-6 position-relative">
      <input type="text" class="form-control" id="itemsCityInput" name="city" placeholder="اكتب المدينة / المنطقة …" autocomplete="off" value="{{ selected_city or '' }}">
      <div id="itemsCitySugg" class="bg-white mt-1" style="display:none; position:absolute; z-index:1000; max-height:260px; overflow:auto; inset-inline:0;"></div>
    </div>
    <div class="col-6 col-md-3 d-grid">
      <button type="button" id="itemsUseGPS" class="btn btn-outline-secondary">📍 استخدم موقعي</button>
      <button type="button" id="itemsClearGPS" class="btn btn-link btn-sm mt-1">❌ إلغاء موقعي</button>
    </div>
    <div class="col-6 col-md-3 d-grid">
      <button class="btn btn-primary" type="submit">تطبيق</button>
    </div>

    <!-- حقول خفية + حفظ category/sort -->
    <input type="hidden" id="itemsLat" name="lat" value="{{ lat or '' }}">
    <input type="hidden" id="itemsLng" name="lng" value="{{ lng or '' }}">
    {% if current_category %}<input type="hidden" name="category" value="{{ current_category }}">{% endif %}
    {% if current_sort %}<input type="hidden" name="sort" value="{{ current_sort }}">{% endif %}
  </form>

  {% if items and items|length %}
    <div class="grid-items">
      {% for it in items %}
        <article class="glass-card">
          <a href="/items/{{ it.id }}" style="display:block; position:relative">
            {% if it.image_path %}
              <img src="{{ it.image_path | media_url }}" class="item-img" alt="item" loading="lazy" referrerpolicy="no-referrer">
            {% else %}
              <div class="item-img d-grid place-items-center text-muted">لا صورة</div>
            {% endif %}
            {% if it.price_per_day is defined %}<span class="price-badge">{{ it.price_per_day }} د/يوم</span>{% endif %}
          </a>

          <div class="p-3">
            <div class="small text-muted mb-1">{{ it.category_label }}{% if it.city %} • {{ it.city }}{% endif %}</div>
            <h5 class="mb-2 text-truncate" title="{{ it.title }}">{{ it.title }}</h5>

            <div class="owner-line mb-2" title="{{ it.owner.first_name }} {{ it.owner.last_name }}">
              {% if it.owner and it.owner.avatar_path %}
                <img class="avatar" src="{{ it.owner.avatar_path | media_url }}" alt="">
              {% endif %}
              <div class="text-muted small text-truncate" style="max-width:70%">{{ it.owner.first_name }} {{ it.owner.last_name }}</div>
              <div style="margin-inline-start:auto">{{ render_badges(it.owner_badges, 18) }}</div>
            </div>

            <div class="d-flex justify-content-between align-items-center">
              <a href="/items/{{ it.id }}" class="btn btn-sm glass-btn">تفاصيل</a>
              <a href="/messages/start?user_id={{ it.owner_id }}&item_id={{ it.id }}" class="btn btn-sm btn-outline-primary">تواصل</a>
            </div>
          </div>
        </article>
      {% endfor %}
    </div>
  {% else %}
    <p class="text-muted">لا توجد عناصر ضمن هذا التصنيف.</p>
  {% endif %}
</section>

<script>
(function itemsLocBar(){
  const form   = document.getElementById('itemsLocForm');
  const cityEl = document.getElementById('itemsCityInput');
  const latEl  = document.getElementById('itemsLat');
  const lngEl  = document.getElementById('itemsLng');
  const gpsBtn = document.getElementById('itemsUseGPS');
  const clearBtn = document.getElementById('itemsClearGPS');
  const sugg   = document.getElementById('itemsCitySugg');

  function setCookie(n,v,d=180){try{const e=new Date();e.setTime(e.getTime()+d*864e5);document.cookie=n+"="+encodeURIComponent(v||"")+";expires="+e.toUTCString()+";path=/;SameSite=Lax";}catch(_){}} 
  function getCookie(n){const m=document.cookie.match(new RegExp('(?:^| )'+n+'=([^;]+)'));return m?decodeURIComponent(m[1]):"";}
  function delCookie(n){try{document.cookie=n+"=;expires=Thu, 01 Jan 1970 00:00:00 GMT;path=/;SameSite=Lax";}catch(_){}} 

  // تهيئة من الكوكي/URL
  try{
    const u = new URL(location.href);
    const c = u.searchParams.get('city') || getCookie('city') || "";
    const lat = u.searchParams.get('lat') || getCookie('lat') || "";
    const lng = u.searchParams.get('lng') || getCookie('lng') || "";
    if(cityEl) cityEl.value = c;
    if(latEl)  latEl.value  = lat;
    if(lngEl)  lngEl.value  = lng;
  }catch(_){}

  // 📍 استخدم موقعي
  gpsBtn?.addEventListener('click', ()=>{
    if(!navigator.geolocation){ alert('المتصفح لا يدعم تحديد الموقع.'); return; }
    navigator.geolocation.getCurrentPosition(pos=>{
      const lat=pos.coords.latitude, lng=pos.coords.longitude;
      setCookie('lat',lat); setCookie('lng',lng); setCookie('city',"");
      cityEl.value=""; latEl.value=lat; lngEl.value=lng;
      const u=new URL(location.href);
      u.searchParams.set('lat',lat); u.searchParams.set('lng',lng); u.searchParams.delete('city');
      location.href=u.toString();
    }, ()=>alert('تعذّر الحصول على موقعك.'));
  });

  // ❌ إلغاء موقعي
  clearBtn?.addEventListener('click', ()=>{
    delCookie('lat'); delCookie('lng');
    const u=new URL(location.href);
    u.searchParams.delete('lat'); u.searchParams.delete('lng');
    if(!(cityEl?.value||"").trim()){ delCookie('city'); u.searchParams.delete('city'); }
    location.href=u.toString();
  });

  // حفظ المدينة يدويًا
  cityEl?.addEventListener('change', ()=>{
    setCookie('city',(cityEl.value||"").trim());
    setCookie('lat',""); setCookie('lng',"");
  });

  /* ===== اقتراح مدينة واحدة + لغة الإدخال ===== */
  let t=null;
  function hideSugg(){ if(sugg){ sugg.style.display='none'; sugg.innerHTML=''; } }
  function showSugg(){ if(sugg){ sugg.style.display='block'; } }
  function detectLang(q){
    const s=(q||'').trim();
    if (/[\u0600-\u06FF]/.test(s)) return 'ar';
    const fr = /[àâäæçéèêëîïôœùûüÿÀÂÄÆÇÉÈÊËÎÏÔŒÙÛÜŸ]/.test(s)
            || /\b(le|la|les|de|des|du|aux|au|à|sur|saint|sainte|chez)\b/i.test(s);
    return fr ? 'fr' : 'en';
  }
  const ALLOWED = new Set(['city','town','village','municipality']);
  const FALLBACK = new Set(['state','province']);
  function normalizePlace(p){
    const a=p.address||{}, type=(p.type||'').toLowerCase(), cc=(a.country_code||'').toLowerCase();
    const city=a.city||a.town||a.village||a.municipality||a.state||a.province||(p.display_name||'').split(',')[0];
    const prioMap={city:1,town:2,village:3,municipality:3,state:6,province:6,administrative:8,county:8,region:8};
    return {city,country:a.country||'',cc,lat:p.lat,lon:p.lon,type,prio:(prioMap[type]??9)};
  }
  function pickBestUnique(list){
    const best=new Map();
    for(const p of list){
      const n=normalizePlace(p);
      if(!n.city||!n.cc) continue;
      const key=n.city.trim().toLowerCase()+'|'+n.cc;
      const prev=best.get(key);
      if(!prev || n.prio<prev.prio) best.set(key,n);
    }
    return Array.from(best.values());
  }

  cityEl?.addEventListener('input', function(){
    clearTimeout(t);
    const q=this.value.trim();
    if(q.length<2){ hideSugg(); return; }
    t=setTimeout(async ()=>{
      try{
        const lang=detectLang(q);
        const url='https://nominatim.openstreetmap.org/search'
          + '?format=json&addressdetails=1&limit=30'
          + '&accept-language='+encodeURIComponent(lang)
          + '&q='+encodeURIComponent(q);
        const r=await fetch(url,{headers:{'Accept':'application/json'}});
        if(!r.ok){ hideSugg(); return; }
        let data=await r.json();
        let f=data.filter(x=>ALLOWED.has((x.type||'').toLowerCase()));
        if(!f.length) f=data.filter(x=>FALLBACK.has((x.type||'').toLowerCase()));
        if(!f.length) f=data;
        const u=pickBestUnique(f).sort((a,b)=>a.prio-b.prio);
        const best=u[0];
        if(!best){ hideSugg(); return; }
        const label=(best.city||'').trim()+(best.country?`, ${best.country}`:'');
        sugg.innerHTML=`<div class="py-2 px-2" data-best="1" style="cursor:pointer"><i class="bi bi-geo-alt"></i> <span>${label}</span></div>`;
        sugg.dataset.lat=best.lat||''; sugg.dataset.lon=best.lon||'';
        showSugg();
      }catch(_){ hideSugg(); }
    },250);
  });

  // اختيار الاقتراح الوحيد
  sugg?.addEventListener('click', ()=>{
    const label=(sugg.querySelector('[data-best] span')?.textContent||'').trim();
    const lat=sugg.dataset.lat||''; const lon=sugg.dataset.lon||'';
    if(!label) return;
    cityEl.value=label; latEl.value=lat; lngEl.value=lon;
    setCookie('city',label); setCookie('lat',lat); setCookie('lng',lon);
    const u=new URL(location.href);
    // الحفاظ على category/sort
    u.searchParams.set('city',label);
    u.searchParams.set('lat',lat);
    u.searchParams.set('lng',lon);
    const cat=form.querySelector('[name="category"]')?.value;
    const sort=form.querySelector('[name="sort"]')?.value;
    if(cat) u.searchParams.set('category',cat);
    if(sort) u.searchParams.set('sort',sort);
    location.href=u.toString();
  });

  // إخفاء القائمة عند النقر خارجها
  document.addEventListener('click',(e)=>{
    if(!sugg) return;
    if(!sugg.contains(e.target) && e.target!==cityEl){ hideSugg(); }
  });

  // زر "تطبيق"
  form?.addEventListener('submit', function(e){
    e.preventDefault();
    const c=(cityEl?.value||"").trim();
    const lat=(latEl?.value||"").trim();
    const lng=(lngEl?.value||"").trim();
    const u=new URL(location.href);
    // نظّف ثم أضف القيم
    ['city','lat','lng'].forEach(k=>u.searchParams.delete(k));
    if(lat && lng){
      setCookie('lat',lat); setCookie('lng',lng); setCookie('city',c||"");
      u.searchParams.set('lat',lat); u.searchParams.set('lng',lng);
      if(c) u.searchParams.set('city',c);
    }else if(c){
      setCookie('city',c); setCookie('lat',""); setCookie('lng',"");
      u.searchParams.set('city',c);
    }else{
      delCookie('city'); delCookie('lat'); delCookie('lng');
    }
    // حافظ على category/sort
    const cat=form.querySelector('[name="category"]')?.value;
    const sort=form.querySelector('[name="sort"]')?.value;
    if(cat) u.searchParams.set('category',cat);
    if(sort) u.searchParams.set('sort',sort);
    location.href=u.toString();
  });
})();
</script>

{% endblock %}