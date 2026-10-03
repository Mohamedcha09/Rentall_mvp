# خطة اختبار توسعة كتالوج البحث (333 مرجعًا)

## الغرض والنطاق

هذه خطة تنفيذ واختبار محلية لتوسعة الكتالوج البحثي R01–R47. لا تُشغّل
على Render أوعلى قاعدة إنتاج، ولا تفترض أن وجود اسم في `rental_catalog.py`
يثبت أن الحفظ أوالفلاتر أوالواجهة تعمل. كل قاعدة بيانات في هذه الخطة هي
SQLite مؤقتة أوPostgreSQL معزولة صراحةً.

المصدر الفعلي الحالي هو:

```text
app/rental_catalog.py
  -> app/catalog_taxonomy.py:CATEGORY_TREE
  -> Category / Subcategory lookup rows (L1/L2)
  -> payload واحد لـ Create وEdit
  -> resolve_listing_hierarchy (تحقق وحفظ)
  -> Explore / Admin / Details / Search / Finder
```

المستوى الثالث ليس جدول lookup حاليًا: هو تعريف مركزي في
`CATEGORY_TREE`. لذلك اختبار migration يختبر صفوف L1/L2 فقط، واختبارات
المسار والتحقق تختبر L3 و`custom_third_level`.

## ما يغطيه الاختبار الحالي وما يجب إضافته

| المجال | موجود حاليًا | المطلوب بعد توسعة R01–R47 |
| --- | --- | --- |
| بنية الكتالوج | `tests/test_rental_catalog.py` يتحقق من العمق ≤ 3، الآباء، التكرارات، الترجمات، و`Other`. | إضافة اختبار baseline لا يسمح بفقد أي عقدة قديمة، واختبار كل مسار نشط في manifest. |
| payload النموذج | `tests/test_item_taxonomy.py` يطابق كامل `CATEGORY_TREE` في EN/FR/AR. | إبقاء الاختبار عامًا؛ لا تُستبدل المطابقة بقائمة أمثلة أوأعداد L3 قديمة ثابتة. |
| تحقق الخادم | resolver مع DB مؤقتة يقبل كل المسارات الحالية ويرفض الأب/الطفل المزور. | تشغيله لكل مسار نشط يشير إليه manifest، مع عينات واضحة من كل عائلة. |
| migration | migration قديم ثابت لـ L1/L2 واختبار ترقية SQLite ومسارات قديمة. | migration إضافي ثابت (لا تعديل migration مطبقة) واختبار parity بين مجموع snapshots والكتالوج النهائي. |
| دورة HTTP | Create → DB → Pending → Approve → Explore → Details → Edit موجودة لعينات رقمية/حافلة/فشار. | توسيع matrix بعينات R01–R47 وبفئة رئيسية جديدة حقيقية، دون إنشاء بيانات إنتاج. |
| Search / Finder | Search وFinder يقرآن `CATEGORY_TREE` والـlookup؛ توجد اختبارات aliases ونتائج منظمة. | اختبار aliases الجديدة، EN/FR/AR، وإثبات أن اسم العنوان وحده لا يتجاوز taxonomy المنظم. |
| واجهة مرئية | TestClient وقراءة HTML فقط. | لا يوجد Playwright/Selenium في المتطلبات الحالية؛ اختبار JavaScript الحقيقي وviewports يحتاج harness محلي منفصل، ولا يُعلن كمنفذ قبل إضافته وتشغيله. |

الأعداد الحالية في الاختبارات (مثل `701` L3 و`25` فروع ذات مستويين)
هي baseline قديم فقط. بعد إضافة العقد، يجب عدم تعديلها إلى عدد تخميني؛
يُستبدل أي assertion ثابت بحساب مشتق من الشجرة وmanifest المعتمد.

## عقد coverage manifest الإلزامي

يُنشأ ملف قابل للقراءة آليًا، مثل
`docs/rental_research_coverage_manifest.json`، بصف واحد لكل مدخل بحثي.
المفاتيح المطلوبة لكل صف هي:

```text
source_reference
source_label
research_family
final_status
canonical_category_id_or_slug
canonical_path
actual_level
rental_mode_or_component_mapping_if_relevant
activation_state
reason
source_urls
test_reference_or_blocker
```

`canonical_category_id_or_slug` هنا هو هوية الكتالوج الداخلية/القيمة
canonical، وليس ID قاعدة إنتاج. لا يُسجل أي اتصال أوسر في هذا الملف.

### اختبار العدّ والهوية

يضاف اختبار مستقل، مثل `tests/test_rental_research_manifest.py`، يبني
مجموعة references المتوقعة التالية ثم يطابقها بالمجموعة الموجودة بلا نقص
أوتكرار:

| العائلة | العدد | العائلة | العدد |
| --- | ---: | --- | ---: |
| R01 | 8 | R02 | 4 |
| R03 | 6 | R04 | 6 |
| R05 | 8 | R06 | 2 |
| R07 | 6 | R08 | 1 |
| R09 | 1 | R10 | 3 |
| R11 | 1 | R12 | 3 |
| R13 | 16 | R14 | 13 |
| R15 | 10 | R16 | 10 |
| R17 | 5 | R18 | 10 |
| R19 | 15 | R20 | 10 |
| R21 | 13 | R22 | 10 |
| R23 | 6 | R24 | 12 |
| R25 | 7 | R26 | 8 |
| R27 | 9 | R28 | 14 |
| R29 | 9 | R30 | 6 |
| R31 | 6 | R32 | 7 |
| R33 | 8 | R34 | 5 |
| R35 | 3 | R36 | 10 |
| R37 | 11 | R38 | 4 |
| R39 | 8 | R40 | 2 |
| R41 | 5 | R42 | 9 |
| R43 | 7 | R44 | 7 |
| R45 | 1 | R46 | 4 |
| R47 | 4 | **الإجمالي** | **333** |

الاختبار يجب أن يثبت أيضًا الآتي:

- `len(rows) == 333` و`len({source_reference}) == 333`.
- كل reference يطابق الصيغة `RNN-NN` وهو ضمن نطاق عائلته الصحيح.
- `final_status` واحد فقط من: `ADDED`, `EXISTING`, `ALIAS_MAPPED`,
  `KIT_COMPONENT_MAPPED`, `RENTAL_MODE_MAPPED`, `REVIEW_REQUIRED`, أو
  `BLOCKED_WITH_REASON`.
- كل صف له `source_label` وسبب غير فارغ ورابط مصدر واحد على الأقل؛ الروابط
  تتعامل كبيانات توثيقية فقط ولا تُجلب أثناء test suite.
- لا يسمح بـ`ADDED` أو`EXISTING` أو`ALIAS_MAPPED` لمسار غير موجود في
  `CATEGORY_TREE`، ولا بـ`actual_level` خارج 1/2/3 أوmode/component mapping
  الصحيح.
- `KIT_COMPONENT_MAPPED` يشير إلى طقم أوأصل قابل للتأجير موجود، مع سبب
  يوضح أن المكوّن ليس إعلانًا مستقلًا مثبتًا.
- `RENTAL_MODE_MAPPED` يحدد الأصل/المساحة الفعلية وطريقة العرض (مثلاً
  in-site workstation أوcrewed charter) بدل إنشاء L4.
- `REVIEW_REQUIRED` و`BLOCKED_WITH_REASON` يحتاجان blocker محددًا وحالة
  تفعيل غير نشطة؛ لا يمران بعبارة عامة مثل “complex”.
- كل صف نشط له `test_reference_or_blocker` يشير إلى test path/parameterized
  case؛ الصف المراجع فقط يشير إلى سياسة gating التي تمنع عرضه كحجز ذاتي.

## اختبارات الشجرة والـbaseline

### 1. عدم فقد الكتالوج السابق

قبل تعديل البيانات، يُخزن export بلا أسرار للشجرة الحالية في
`docs/rental_taxonomy_before_2026-10-03.json`. يضيف الاختبار التالي:

1. يحمّل baseline ويحول العقد إلى paths canonical.
2. يحمّل الشجرة الجديدة من `CATEGORY_TREE`.
3. يثبت أن كل L1/L2/L3 قديم موجود تحت الأب نفسه، أوأن التحويل موثق في
   compatibility map محدد ومختبر؛ لا يُسمح بإعادة تصنيف `Item`.
4. يثبت بقاء aliases القديمة وترجمة العقد القائمة كما هي.

### 2. topology data-driven

يمدد اختبار `test_rental_catalog.py` بحيث يثبت:

- لا L1 أوL2 أوL3 فارغ؛ ولا sibling مكرر case-insensitively تحت الأب نفسه.
- لا child بلا parent، ولا cycle، ولا عمق أكبر من ثلاثة.
- لا يُضاف `Other` بمفرده: عند وجوده يكون آخر L3 وله sibling حقيقي واحد
  على الأقل.
- الفروع ذات المستويين تبقى خالية من L3، وليس لها third-level مخفي مطلوب.
- كل عقدة نشطة لها label EN/FR/AR غير فارغ؛ قيمة `en` هي القيمة canonical
  التي تحفظ، لا الترجمة.
- كل مسار active في manifest موجود في الشجرة؛ status alias/component/mode
  لا يخلق عقدة duplicate لمجرد اختلاف المفرد/الجمع أوطريقة الاستخدام.

## اختبارات migration والـlookup parity

لا يعدّل الاختبار migration تاريخية مطبقة مثل
`20261004_expand_rental_catalog.py`. عند إضافة L1/L2 جديدة، تُنشأ migration
إضافية ذات snapshot ثابت و`down_revision` صحيح بعد رأس الكتالوج المحلي.

الاختبارات المطلوبة:

1. **Static snapshot parity:** اجمع snapshot L1/L2 القديم مع delta الجديد
   في الاختبار، ثم طابق الناتج تمامًا مع `rental_seed_rows()` النهائي. لا
   تستورد migration الكتالوج الحي وقت التنفيذ.
2. **Upgrade from a pre-delta isolated DB:** أنشئ SQLite مؤقتة فيها
   `categories`, `subcategories`, `items` وصفوف legacy، ثم شغّل Alembic إلى
   الرأس المحلي. تحقق من وجود كل L1/L2 النشط، ومن عدم إنشاء L3 lookup table.
3. **Idempotency/no duplication:** ابدأ بصفوف canonical موجودة وبـalias
   صالح واحد، ثم شغّل الترقية. تحقق أن ID الأب والـItem القديم لم يتغيرا وأن
   كل L2 مطلوب موجود مرة واحدة فقط تحت الأب الصحيح.
4. **Failure safety:** DB فيها duplicate case-insensitive أوparent alias
   غامض يجب أن يرفض الترحيل قبل كتابة جزئية؛ لا يحذف أويعيد ترقيم أي صف.
5. **Schema compatibility:** تحقق من استمرار الأعمدة nullable:
   `subcategory`, `third_level`, `custom_third_level` وفهرس taxonomy، ومن
   بقاء عنصر قديم بلا L3 قابلًا للقراءة والتعديل.
6. **اختياري موثق:** نفّذ نفس الترقية على PostgreSQL محلية/CI معزولة إن
   توفرت. SQLite لا يثبت كل فروق PostgreSQL؛ غياب هذا الاختبار يُذكر صراحة.

## Create وEdit والتحقق على الخادم

اختبار payload الحالي يجب أن يبقى عامًا: أنشئ lookup rows مؤقتة لكل L1/L2
من `CATEGORY_TREE` ثم تحقق في كل لغة أن payload المعروض يحوي نفس L1/L2/L3
والـIDs الخاصة بالمستوى الثاني.

يضاف إليه أوإلى test مستقل ما يلي:

1. loop لكل branch نشط: مرّر `category`, `subcategory_id` وL3 إن وجدت إلى
   `resolve_listing_hierarchy` وتحقق من حفظ القيم الأربع المنفصلة، لا
   hierarchy string.
2. لكل فرع ثنائي: `third_level` و`custom_third_level` الفارغان يتحولان إلى
   `None`. تمرير خدمة قديمة/مزورة يعيد validation error.
3. لكل فرع L3: خدمة صحيحة تقبل؛ خدمة من sibling آخر ترفض؛ `Other` يتطلب
   `custom_third_level` بطول مسموح؛ custom text مع خدمة غير `Other` يرفض.
4. إنشاء جديد لا يقبل L1 بلا L2 عندما توجد L2 في الـlookup، ولا يقبل L3
   ناقصًا في branch يحتاجها.
5. تغيير L1 أوL2 في POST يزيل L3 وcustom القديمين من القيمة المحفوظة.
6. validation error من route يعيد HTML مع L1/L2/L3 الصحيحة والقيمة السابقة
   الصحيحة، بدل أن يعيد قائمة ناقصة.
7. JavaScript client-side يعالج reset بصريًا، لكن الخادم هو الحكم النهائي؛
   لذا هذا الاختبار لا يعتمد فقط على `FormData` أوDOM.

## matrix دورة الإعلان HTTP حقيقية محليًا

يُوسع `tests/test_item_taxonomy_route_flow.py` أويضاف ملف جديد. كل case
يستخدم TestClient وSQLite مؤقتة ويمر بهذا التسلسل:

```text
GET Create -> POST Create -> read Item from DB -> Pending HTML
-> POST Approve -> Explore L1/L2/L3 -> Details -> GET/Edit POST -> read DB
```

يجب أن يغطي minimum matrix التالي، بحسب الحالة النهائية في manifest:

| العينة | المسار المتوقع | الدليل المطلوب |
| --- | --- | --- |
| R01 | Food → Donut/Popcorn → Mini Doughnut Maker أوPopcorn Machine | حفظ L3 وفلتر لا يعرض sibling. |
| R08 | Tools/Construction → Geotextile Tools → Portable Geotextile Sewing Machine | إنشاء وحفظ وفصل المسار عن خياطة الاستوديو. |
| R13/R16 | Automotive Tools → Torque Wrenches أوPipe Tools → Pipe Freezing Machines | رفض child تابع للأب الآخر. |
| R15 | Floor Installation → Carpet Knee Kickers | ظهور بعد approval عند L1/L2/L3 فقط. |
| R34 | POS → Thermal Badge Printers | Admin وDetails يعرضان المسار نفسه. |
| R45 | Vehicles → Vehicle Travel Accessories → Roof Cargo Boxes | لا يطابق فئة مركبة أخرى بالعنوان فقط. |
| R09/R41 | Craft/Spaces → Heat Press Workstation | يثبت rental mode كمساحة/استخدام في الموقع، لا يخلق L4. |
| R33 | Agriculture → Small-Harvest Processing → Honey Extractor Kits | المكونات kit-mapped لا تظهر كأنها L3 مستقلة. |
| L1 جديد | مثال نشط فعلي من expansion، مثل Test & Measurement إن بقي نشطًا | يظهر في Create وExplore حتى مع zero listings قبل إنشاء test item. |
| فرع قديم موسّع | Vehicles → Cars → نوع جديد | Item قديم `Vehicles → Cars` بلا L3 ما زال قابلًا للتعديل. |
| فرع ثنائي قديم | Baby & Kids → Car Seats أوالمسار الفعلي | لا يظهر L3 ولا يصبح required. |
| Digital regression | Digital Accounts → Movies & Streaming → Amazon Prime Video | استمرار الحفظ والفلترة بعد التوسعة. |
| Other | branch L3 → Other → custom value | حفظ custom فقط ضمن Other وعرضه في Admin/Details. |

لكل case يجب أن يثبت Explore:

- L1 يعرض descendants الموافق عليها فقط.
- L2 يعرض descendants لتلك L2 فقط.
- L3 يعرض `third_level` المطابق فقط، ولا يعرض sibling أوrow قديم بلا L3.
- `pending` لا يظهر عامًا قبل approve.
- approval لا يبدل أي من `category`, `subcategory`, `third_level`,
  `custom_third_level`.

## التوافق مع عناصر قديمة

تُحفظ هذه الحالات في tests مستقلة لأنها لا ينبغي أن تضيع عند زيادة عدد
الفروع:

- Item قديم باسم L1 alias (`vehicle`) بلا L2 يبقى ظاهرًا تحت الأب canonical
  وقابلًا لحفظ تعديل title فقط.
- Item قديم `Vehicles → Cars` بلا L3 يبقى تحت Cars، ولا يطابق Sports Cars
  أوأي child محدد.
- Item قديم في L2 أضيفت لها L3: GET Edit وvalidation error ثم POST بلا تغيير
  يحافظان على blank L3؛ اختيار نوع جديد فقط هو ما يملأه.
- انتقال item حديث من branch L3 إلى branch ثنائي يمسح `third_level` و
  `custom_third_level` في DB، وليس في HTML فقط.

## Search وFinder دون قواعد خاصة لكل منتج

تضاف tests parameterized مأخوذة من manifest لا من ifs في route:

1. `_taxonomy_alias_index()` يضم canonical وFR وAR وaliases لكل عقدة نشطة.
   يمسح cache داخل الاختبار قبل وبعد fixture عند تغيير الشجرة.
2. `/search` يجد item بالـcanonical وبالترجمة العربية والفرنسية وبـalias
   موثق، عبر الحقول المنظمة `category/subcategory/third_level/custom_third_level`.
3. Finder يبني lexicon من `configured_catalog_rows()` ومن lookup rows؛ فرع
   جديد بلا Listings يبقى concept قابلًا للاكتشاف وليس شرطًا أن يولّد result.
4. عنوان يحتوي كلمة مثل “carpet” أواسم leaf آخر لا يجب أن يتغلب على taxonomy
   المنظم لعنصر في فئة غير مطابقة.
5. aliases للمكونات والـrental modes توجه إلى الأصل/المساحة المعتمدة أوتطلب
   clarification، ولا تنشئ product category وهمية.

## اللغة وواجهة الاختيار

اختبارات TestClient الممكنة محليًا يجب أن تثبت في EN/FR/AR:

- label مترجم، و`option.value` يظل canonical نفسه.
- labels العامة تتغير حسب presentation (`Vehicle Type`, `Equipment Type`,
  `Space / Unit Type`, `Service / Platform`) ولا تسمى كل L3 خدمة رقمية.
- Create وEdit يعيدان payload ذاته بالهوية نفسها، بما في ذلك after validation
  error وlegacy Edit.
- long labels تظهر في HTML مع `label for` الصحيح وsearch inputs native
  المرتبطة بـARIA، من دون assertion على screenshot غير منفذ.

لا توجد مكتبة متصفح حقيقية في `requirements.txt` الحالية؛ لذلك لا تكفي
اختبارات HTML لإثبات تشغيل `change` handlers أوالعرض على 320/360/375/390/430
px. إن أضيف Playwright محليًا لاحقًا، يُنفذ smoke suite منفصلة ضد server
محلي وDB مؤقتة للتحقق من:

1. اختيار L1 ثم L2 ثم L3 يغيّر الخيارات ويزيل القيم القديمة.
2. حقل البحث داخل select يصبح متاحًا عندما تتجاوز القائمة threshold الحالي.
3. `Other` يظهر/يخفي custom input بشكل صحيح.
4. RTL والأسماء الطويلة لا تحدث overflow أفقيًا في viewports المطلوبة.
5. keyboard focus وlabels يعملان في Create وEdit.

حتى ذلك الوقت توصف هذه العناصر بأنها **غير مختبرة بصريًا**، لا بأنها ناجحة.

## ترتيب تنفيذ الاختبارات محليًا

1. أنشئ baseline وmanifest أولًا، ثم شغّل اختبارات manifest/topology قبل
   تعديل routes.
2. أضف migration delta ثابتة، ثم شغّل parity وupgrade/idempotency على DB
   مؤقتة.
3. شغّل resolver/payload لكل مسار نشط.
4. شغّل matrix HTTP ثم Search/Finder.
5. شغّل suites الموجودة أيضًا كي تكشف regression في Digital Accounts:

```powershell
python -m unittest tests.test_rental_catalog tests.test_item_taxonomy tests.test_item_taxonomy_route_flow
python -m unittest tests.test_finder
```

لا تُشغّل هذه الأوامر إلا بعد ضبط `DATABASE_URL` على ملف مؤقت/بيئة اختبار
معزولة. لا تستخدم اتصالًا محليًا غير معروف الوجهة، ولا يتم ضمن هذه الخطة
أي نشر أوGit write أوRender migration.

