{% extends "base.html" %}
{% block content %}

<section class="container-xxl">

  <!-- هيدر البروفايل -->
  <div class="card mb-3">
    <div class="card-body d-flex justify-content-between align-items-center gap-3 flex-wrap">

      <!-- الاسم + الأوسمة -->
      <div class="d-flex align-items-center gap-3 flex-wrap">
        <div>
          <h2 class="m-0 d-flex align-items-center gap-2">
            <span class="fw-bold text-truncate">{{ (user_obj.first_name ~ ' ' ~ user_obj.last_name).strip() or '—' }}</span>

            {% if is_verified %}
              <span class="chip chip-verify">
                <i class="bi bi-patch-check-fill"></i>
                <span>موثَّق</span>
              </span>
            {% endif %}

            {% if is_newbie %}
              <span class="chip chip-new">
                <i class="bi bi-stars"></i>
                <span>جديد</span>
              </span>
            {% endif %}
          </h2>

          <div class="small text-muted mt-1 d-flex align-items-center gap-2 flex-wrap">
            <span class="d-inline-flex align-items-center gap-1">
              <i class="bi bi-calendar2-week"></i>
              انضم: {{ user_obj.created_at }}
            </span>
            <span class="d-inline-flex align-items-center gap-1">
              <i class="bi bi-box-seam"></i>
              عناصر: {{ items_count }}
            </span>
            <span class="d-inline-flex align-items-center gap-1">
              <i class="bi bi-star-half"></i>
              تقييم: {{ rating_avg or 0 }} ({{ reviews_count }} مراجعة)
            </span>
          </div>
        </div>
      </div>

      <!-- أفاتار -->
      <div class="flex-shrink-0">
        {% if user_obj.avatar_path %}
          <img src="/{{ user_obj.avatar_path }}" alt="" class="rounded-circle" style="width:76px;height:76px;object-fit:cover;border:1px solid var(--border)">
        {% else %}
          <div class="rounded-circle d-grid place-items-center" style="width:76px;height:76px;background:var(--surface);border:1px solid var(--border);font-weight:800;">
            {{ (user_obj.first_name or 'U')[:1] }}
          </div>
        {% endif %}
      </div>
    </div>
  </div>

  <!-- تبويبات بسيطة -->
  <ul class="nav nav-pills mb-3 gap-2 flex-wrap">
    <li class="nav-item"><a class="nav-link active" href="#items" data-bs-toggle="tab">العناصر</a></li>
    <li class="nav-item"><a class="nav-link" href="#about" data-bs-toggle="tab">حول المستخدم</a></li>
    <li class="nav-item"><a class="nav-link" href="#reviews" data-bs-toggle="tab">التقييمات</a></li>
  </ul>

  <div class="tab-content">

    <!-- عناصر المالك -->
    <div class="tab-pane fade show active" id="items">
      {% if items %}
        <div class="home-grid">
          {% for it in items %}
            <article class="card spot">
              <div class="spot-media">
                {% if it.image_path %}
                  <img src="/{{ it.image_path }}" alt="">
                {% endif %}
                <div class="spot-overlay"></div>
                <div class="price-badge"><strong>{{ it.price_per_day }}</strong><span> د/يوم</span></div>
                <div class="category-chip">{{ it.category or '' }}</div>
              </div>
              <div class="card-body">
                <h5 class="spot-title" title="{{ it.title }}">{{ it.title }}</h5>
                <div class="spot-footer d-flex justify-content-between align-items-center">
                  <div class="small text-muted">🏙️ {{ it.city or '—' }}</div>
                  <a href="/items/{{ it.id }}" class="btn btn-sm btn-primary">تفاصيل</a>
                </div>
              </div>
            </article>
          {% endfor %}
        </div>
      {% else %}
        <div class="text-center text-muted py-5">لا توجد عناصر معروضة لهذا المستخدم حاليًا.</div>
      {% endif %}
    </div>

    <!-- حول -->
    <div class="tab-pane fade" id="about">
      <div class="card">
        <div class="card-body">
          <div class="small text-muted">معلومات عامة:</div>
          <ul class="m-0 mt-2 small">
            <li>المعرف: {{ user_obj.id }}</li>
            <li>الحالة: {{ user_obj.status or '—' }}</li>
            <li>تاريخ الانضمام: {{ user_obj.created_at }}</li>
          </ul>
        </div>
      </div>
    </div>

    <!-- التقييمات -->
    <div class="tab-pane fade" id="reviews">
      <div class="card">
        <div class="card-body text-muted text-center">
          <div class="mb-2">تقييم متوسط: {{ rating_avg or 0 }}</div>
          <div>({{ reviews_count }} مراجعة)</div>
          <div class="small mt-3">ميزة التقييمات ستُستكمل لاحقًا.</div>
        </div>
      </div>
    </div>

  </div>
</section>

{% endblock %}
