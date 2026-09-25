/* SEVOR Privacy Center: page-local translations and lightweight interactions. */
(() => {
  "use strict";

  const translations = {
    en: {
      htmlLang: "en", dir: "ltr", languageName: "English",
      documentTitle: "Privacy Policy | SEVOR",
      documentDescription: "Learn how SEVOR handles the account, booking, rental, uploaded-photo, device, and usage information described in its Privacy Policy.",
      backHome: "Back to SEVOR", backHomeAria: "Return to the SEVOR home page",
      privacyCenter: "Privacy Center", heroTitle: "Privacy Policy",
      heroLead: "Learn, in clear terms, what the current SEVOR Privacy Policy says about the information connected to your use of the platform.",
      lastUpdated: "Last updated", updatedDate: "Pending legal confirmation", heroAction: "Explore your choices",
      summaryEyebrow: "At a glance", summaryTitle: "A clear privacy summary",
      summaryLead: "The highlights below reflect the information and purposes stated in SEVOR's current published policy.",
      summary: [
        { title: "Your data", body: "The policy identifies account, booking and rental details, uploaded photos, and device or usage information." },
        { title: "Why we use it", body: "To provide and improve rental services, verify identity, process bookings and payments, and communicate about an account." },
        { title: "Your choices", body: "The policy states that you may request access to, correction of, or deletion of personal data." },
        { title: "Privacy & security", body: "Safety and fraud prevention are among the stated reasons SEVOR uses information." }
      ],
      contentsLabel: "On this page", tocAria: "Privacy policy sections",
      toc: { introduction: "Introduction", collect: "Information we collect", use: "How we use information", rights: "Your privacy rights", deletion: "Account & data deletion", security: "Privacy & security", contact: "Contact us" },
      sections: {
        introduction: { title: "Introduction", body: "SEVOR operates a website and mobile application. This Privacy Policy explains how SEVOR collects, uses, and protects information connected to the platform." },
        collect: { title: "Information we collect", lead: "The current published policy identifies the following categories of information." },
        use: { title: "How we use information", lead: "SEVOR's current policy lists these purposes for using information." },
        rights: { title: "Your privacy rights", lead: "The current policy states that you may request the following actions regarding your personal data." },
        deletion: { title: "Account & data deletion" },
        security: { title: "Privacy & security", body: "The published policy identifies identity verification, booking and payment processing, safety, and fraud prevention as reasons for using information. It does not publish a specific technical security standard, so this page makes no such claim." },
        contact: { title: "Contact us", lead: "The current published policy displays the address below. Signed-in users can also use SEVOR's existing support form." }
      },
      categories: [
        { title: "Account information", body: "Name, email address, and phone number." },
        { title: "Booking & rental information", body: "Information connected to bookings and rentals." },
        { title: "Uploaded photos", body: "Photos uploaded for verification, pickup, and return." },
        { title: "Device & usage information", body: "Device information and usage data." }
      ],
      uses: ["Provide and improve rental services.", "Verify identity.", "Process bookings and payments.", "Enhance safety and help prevent fraud.", "Communicate about an account."],
      rights: [
        { title: "Access your data", body: "Request access to your personal data." },
        { title: "Correct information", body: "Request correction of your personal data." },
        { title: "Request deletion", body: "Request deletion of your personal data." }
      ],
      deletionCalloutTitle: "Use the existing account-deletion flow",
      deletionCalloutBody: "SEVOR has an existing account-deletion page for signed-in users. It requires sign-in and uses the platform's current deletion flow; this page does not promise the scope or timing of deletion beyond that flow.",
      deletionAction: "Open account deletion", supportAction: "Open support",
      contactCardTitle: "Privacy questions", policyAddressLabel: "Address listed in the current policy:", emailAction: "Email address",
      languageTitle: "Language", languageLead: "Choose your language for this Privacy Center.", languageGroupAria: "Choose a Privacy Center language", selectLanguage: "Choose language", languageSelected: "English selected.",
      footerNote: "This Privacy Center reflects the currently published SEVOR Privacy Policy.", footerTop: "Back to top", backTop: "Back to top", backTopAria: "Scroll back to the top of the Privacy Policy"
    },

    fr: {
      htmlLang: "fr", dir: "ltr", languageName: "Français",
      documentTitle: "Politique de confidentialité | SEVOR",
      documentDescription: "Découvrez comment SEVOR traite les informations de compte, de réservation, de location, de photos téléversées, d'appareil et d'utilisation décrites dans sa Politique de confidentialité.",
      backHome: "Retour à SEVOR", backHomeAria: "Retourner à la page d'accueil de SEVOR",
      privacyCenter: "Centre de confidentialité", heroTitle: "Politique de confidentialité",
      heroLead: "Découvrez clairement ce que la Politique de confidentialité actuellement publiée par SEVOR indique au sujet des informations liées à votre utilisation de la plateforme.",
      lastUpdated: "Dernière mise à jour", updatedDate: "En attente de confirmation juridique", heroAction: "Découvrir vos choix",
      summaryEyebrow: "En un coup d'œil", summaryTitle: "Un résumé clair de la confidentialité",
      summaryLead: "Les points ci-dessous reflètent les informations et les finalités indiquées dans la politique actuellement publiée par SEVOR.",
      summary: [
        { title: "Vos données", body: "La politique mentionne les informations de compte, de réservation et de location, les photos téléversées et les informations d'appareil ou d'utilisation." },
        { title: "Pourquoi les utiliser", body: "Pour fournir et améliorer les services de location, vérifier l'identité, traiter les réservations et paiements, et communiquer à propos d'un compte." },
        { title: "Vos choix", body: "La politique indique que vous pouvez demander l'accès à vos données personnelles, leur correction ou leur suppression." },
        { title: "Confidentialité et sécurité", body: "La sécurité et la prévention de la fraude font partie des finalités déclarées de l'utilisation des informations par SEVOR." }
      ],
      contentsLabel: "Sur cette page", tocAria: "Sections de la Politique de confidentialité",
      toc: { introduction: "Introduction", collect: "Informations collectées", use: "Utilisation des informations", rights: "Vos droits à la confidentialité", deletion: "Suppression du compte et des données", security: "Confidentialité et sécurité", contact: "Nous contacter" },
      sections: {
        introduction: { title: "Introduction", body: "SEVOR exploite un site web et une application mobile. Cette Politique de confidentialité explique comment SEVOR collecte, utilise et protège les informations liées à la plateforme." },
        collect: { title: "Informations collectées", lead: "La politique actuellement publiée identifie les catégories d'informations suivantes." },
        use: { title: "Utilisation des informations", lead: "La politique actuelle de SEVOR énumère ces finalités d'utilisation des informations." },
        rights: { title: "Vos droits à la confidentialité", lead: "La politique actuelle indique que vous pouvez demander les actions suivantes concernant vos données personnelles." },
        deletion: { title: "Suppression du compte et des données" },
        security: { title: "Confidentialité et sécurité", body: "La politique publiée mentionne la vérification d'identité, le traitement des réservations et paiements, la sécurité et la prévention de la fraude comme finalités d'utilisation des informations. Elle ne publie pas de norme technique de sécurité précise; cette page n'en revendique donc aucune." },
        contact: { title: "Nous contacter", lead: "La politique actuellement publiée affiche l'adresse ci-dessous. Les utilisateurs connectés peuvent aussi utiliser le formulaire d'assistance existant de SEVOR." }
      },
      categories: [
        { title: "Informations de compte", body: "Nom, adresse e-mail et numéro de téléphone." },
        { title: "Informations de réservation et de location", body: "Informations liées aux réservations et aux locations." },
        { title: "Photos téléversées", body: "Photos téléversées pour la vérification, la prise en charge et le retour." },
        { title: "Informations d'appareil et d'utilisation", body: "Informations d'appareil et données d'utilisation." }
      ],
      uses: ["Fournir et améliorer les services de location.", "Vérifier l'identité.", "Traiter les réservations et les paiements.", "Améliorer la sécurité et contribuer à prévenir la fraude.", "Communiquer au sujet d'un compte."],
      rights: [
        { title: "Accéder à vos données", body: "Demander l'accès à vos données personnelles." },
        { title: "Corriger vos informations", body: "Demander la correction de vos données personnelles." },
        { title: "Demander la suppression", body: "Demander la suppression de vos données personnelles." }
      ],
      deletionCalloutTitle: "Utiliser le parcours existant de suppression de compte",
      deletionCalloutBody: "SEVOR dispose d'une page existante de suppression de compte pour les utilisateurs connectés. Elle exige une connexion et utilise le parcours de suppression actuel de la plateforme; cette page ne promet pas la portée ni le délai de suppression au-delà de ce parcours.",
      deletionAction: "Ouvrir la suppression du compte", supportAction: "Ouvrir l'assistance",
      contactCardTitle: "Questions sur la confidentialité", policyAddressLabel: "Adresse indiquée dans la politique actuelle :", emailAction: "Adresse e-mail",
      languageTitle: "Langue", languageLead: "Choisissez votre langue pour ce Centre de confidentialité.", languageGroupAria: "Choisir une langue du Centre de confidentialité", selectLanguage: "Choisir la langue", languageSelected: "Français sélectionné.",
      footerNote: "Ce Centre de confidentialité reflète la Politique de confidentialité SEVOR actuellement publiée.", footerTop: "Retour en haut", backTop: "Retour en haut", backTopAria: "Revenir en haut de la Politique de confidentialité"
    },

    ar: {
      htmlLang: "ar", dir: "rtl", languageName: "العربية",
      documentTitle: "سياسة الخصوصية | SEVOR",
      documentDescription: "تعرّف على كيفية تعامل SEVOR مع معلومات الحساب والحجوزات والإيجارات والصور المرفوعة والجهاز والاستخدام الموضحة في سياسة الخصوصية.",
      backHome: "العودة إلى SEVOR", backHomeAria: "العودة إلى الصفحة الرئيسية في SEVOR",
      privacyCenter: "مركز الخصوصية", heroTitle: "سياسة الخصوصية",
      heroLead: "تعرّف بوضوح على ما تقوله سياسة الخصوصية المنشورة حاليًا لدى SEVOR عن المعلومات المرتبطة باستخدامك للمنصة.",
      lastUpdated: "آخر تحديث", updatedDate: "بانتظار التأكيد القانوني", heroAction: "استكشف خياراتك",
      summaryEyebrow: "نظرة سريعة", summaryTitle: "ملخص واضح للخصوصية",
      summaryLead: "تعكس النقاط التالية المعلومات والأغراض الواردة في سياسة SEVOR المنشورة حاليًا.",
      summary: [
        { title: "بياناتك", body: "تحدد السياسة معلومات الحساب والحجوزات والإيجارات والصور المرفوعة ومعلومات الجهاز أو الاستخدام." },
        { title: "لماذا نستخدمها", body: "لتقديم خدمات الإيجار وتحسينها، والتحقق من الهوية، ومعالجة الحجوزات والمدفوعات، والتواصل بشأن الحساب." },
        { title: "خياراتك", body: "تنص السياسة على أنه يمكنك طلب الوصول إلى بياناتك الشخصية أو تصحيحها أو حذفها." },
        { title: "الخصوصية والأمان", body: "تندرج السلامة ومنع الاحتيال ضمن الأغراض المعلنة لاستخدام SEVOR للمعلومات." }
      ],
      contentsLabel: "في هذه الصفحة", tocAria: "أقسام سياسة الخصوصية",
      toc: { introduction: "مقدمة", collect: "المعلومات التي نجمعها", use: "كيف نستخدم المعلومات", rights: "حقوقك في الخصوصية", deletion: "حذف الحساب والبيانات", security: "الخصوصية والأمان", contact: "اتصل بنا" },
      sections: {
        introduction: { title: "مقدمة", body: "تشغّل SEVOR موقعًا إلكترونيًا وتطبيقًا للهواتف المحمولة. تشرح سياسة الخصوصية هذه كيف تجمع SEVOR المعلومات المرتبطة بالمنصة وتستخدمها وتحميها." },
        collect: { title: "المعلومات التي نجمعها", lead: "تحدد السياسة المنشورة حاليًا فئات المعلومات التالية." },
        use: { title: "كيف نستخدم المعلومات", lead: "تسرد سياسة SEVOR الحالية هذه الأغراض لاستخدام المعلومات." },
        rights: { title: "حقوقك في الخصوصية", lead: "تنص السياسة الحالية على أنه يمكنك طلب الإجراءات التالية بشأن بياناتك الشخصية." },
        deletion: { title: "حذف الحساب والبيانات" },
        security: { title: "الخصوصية والأمان", body: "تذكر السياسة المنشورة التحقق من الهوية ومعالجة الحجوزات والمدفوعات والسلامة ومنع الاحتيال كأغراض لاستخدام المعلومات. وهي لا تنشر معيارًا تقنيًا محددًا للأمان، لذا لا تدّعي هذه الصفحة وجود مثل هذا المعيار." },
        contact: { title: "اتصل بنا", lead: "تعرض السياسة المنشورة حاليًا العنوان أدناه. كما يمكن للمستخدمين المسجلين استخدام نموذج الدعم الحالي في SEVOR." }
      },
      categories: [
        { title: "معلومات الحساب", body: "الاسم وعنوان البريد الإلكتروني ورقم الهاتف." },
        { title: "معلومات الحجز والإيجار", body: "المعلومات المرتبطة بالحجوزات والإيجارات." },
        { title: "الصور المرفوعة", body: "الصور المرفوعة للتحقق والاستلام والإرجاع." },
        { title: "معلومات الجهاز والاستخدام", body: "معلومات الجهاز وبيانات الاستخدام." }
      ],
      uses: ["تقديم خدمات الإيجار وتحسينها.", "التحقق من الهوية.", "معالجة الحجوزات والمدفوعات.", "تعزيز السلامة والمساعدة على منع الاحتيال.", "التواصل بشأن الحساب."],
      rights: [
        { title: "الوصول إلى بياناتك", body: "طلب الوصول إلى بياناتك الشخصية." },
        { title: "تصحيح المعلومات", body: "طلب تصحيح بياناتك الشخصية." },
        { title: "طلب الحذف", body: "طلب حذف بياناتك الشخصية." }
      ],
      deletionCalloutTitle: "استخدم مسار حذف الحساب الحالي",
      deletionCalloutBody: "لدى SEVOR صفحة حالية لحذف الحساب للمستخدمين المسجلين. تتطلب تسجيل الدخول وتستخدم مسار الحذف الحالي للمنصة؛ ولا تعد هذه الصفحة بنطاق الحذف أو توقيته بما يتجاوز ذلك المسار.",
      deletionAction: "فتح حذف الحساب", supportAction: "فتح الدعم",
      contactCardTitle: "أسئلة الخصوصية", policyAddressLabel: "العنوان المذكور في السياسة الحالية:", emailAction: "عنوان البريد الإلكتروني",
      languageTitle: "اللغة", languageLead: "اختر لغتك لمركز الخصوصية هذا.", languageGroupAria: "اختر لغة مركز الخصوصية", selectLanguage: "اختر اللغة", languageSelected: "تم اختيار العربية.",
      footerNote: "يعكس مركز الخصوصية هذا سياسة خصوصية SEVOR المنشورة حاليًا.", footerTop: "العودة إلى الأعلى", backTop: "العودة إلى الأعلى", backTopAria: "التمرير إلى أعلى سياسة الخصوصية"
    },

    hi: {
      htmlLang: "hi", dir: "ltr", languageName: "हिन्दी",
      documentTitle: "गोपनीयता नीति | SEVOR",
      documentDescription: "जानें कि SEVOR अपनी गोपनीयता नीति में वर्णित खाता, बुकिंग, किराये, अपलोड की गई तस्वीर, डिवाइस और उपयोग जानकारी को कैसे संभालता है।",
      backHome: "SEVOR पर वापस जाएँ", backHomeAria: "SEVOR होम पेज पर वापस जाएँ",
      privacyCenter: "गोपनीयता केंद्र", heroTitle: "गोपनीयता नीति",
      heroLead: "स्पष्ट रूप से जानें कि SEVOR की वर्तमान प्रकाशित गोपनीयता नीति प्लेटफ़ॉर्म के आपके उपयोग से जुड़ी जानकारी के बारे में क्या कहती है।",
      lastUpdated: "अंतिम अपडेट", updatedDate: "कानूनी पुष्टि लंबित", heroAction: "अपने विकल्प देखें",
      summaryEyebrow: "एक नज़र में", summaryTitle: "गोपनीयता का स्पष्ट सार",
      summaryLead: "नीचे दिए गए मुख्य बिंदु SEVOR की वर्तमान प्रकाशित नीति में बताई गई जानकारी और उद्देश्यों को दर्शाते हैं।",
      summary: [
        { title: "आपका डेटा", body: "नीति में खाता, बुकिंग और किराये के विवरण, अपलोड की गई तस्वीरें और डिवाइस या उपयोग की जानकारी का उल्लेख है।" },
        { title: "हम इसका उपयोग क्यों करते हैं", body: "किराये की सेवाएँ देने और बेहतर बनाने, पहचान सत्यापित करने, बुकिंग और भुगतान संसाधित करने और खाते के बारे में संवाद करने के लिए।" },
        { title: "आपके विकल्प", body: "नीति के अनुसार आप व्यक्तिगत डेटा तक पहुँच, उसके सुधार या हटाने का अनुरोध कर सकते हैं।" },
        { title: "गोपनीयता और सुरक्षा", body: "सुरक्षा और धोखाधड़ी की रोकथाम SEVOR द्वारा जानकारी के उपयोग के बताए गए कारणों में शामिल हैं।" }
      ],
      contentsLabel: "इस पृष्ठ पर", tocAria: "गोपनीयता नीति के अनुभाग",
      toc: { introduction: "परिचय", collect: "हम कौन-सी जानकारी एकत्र करते हैं", use: "हम जानकारी का उपयोग कैसे करते हैं", rights: "आपके गोपनीयता अधिकार", deletion: "खाता और डेटा हटाना", security: "गोपनीयता और सुरक्षा", contact: "हमसे संपर्क करें" },
      sections: {
        introduction: { title: "परिचय", body: "SEVOR एक वेबसाइट और मोबाइल एप्लिकेशन संचालित करता है। यह गोपनीयता नीति बताती है कि SEVOR प्लेटफ़ॉर्म से जुड़ी जानकारी को कैसे एकत्र करता है, उपयोग करता है और सुरक्षित रखने का प्रयास करता है।" },
        collect: { title: "हम कौन-सी जानकारी एकत्र करते हैं", lead: "वर्तमान प्रकाशित नीति निम्न जानकारी श्रेणियों की पहचान करती है।" },
        use: { title: "हम जानकारी का उपयोग कैसे करते हैं", lead: "SEVOR की वर्तमान नीति जानकारी के उपयोग के इन उद्देश्यों को सूचीबद्ध करती है।" },
        rights: { title: "आपके गोपनीयता अधिकार", lead: "वर्तमान नीति कहती है कि आप अपने व्यक्तिगत डेटा के संबंध में निम्न कार्यों का अनुरोध कर सकते हैं।" },
        deletion: { title: "खाता और डेटा हटाना" },
        security: { title: "गोपनीयता और सुरक्षा", body: "प्रकाशित नीति पहचान सत्यापन, बुकिंग और भुगतान प्रसंस्करण, सुरक्षा और धोखाधड़ी की रोकथाम को जानकारी उपयोग के कारणों के रूप में पहचानती है। यह किसी विशिष्ट तकनीकी सुरक्षा मानक को प्रकाशित नहीं करती, इसलिए यह पृष्ठ ऐसा कोई दावा नहीं करता।" },
        contact: { title: "हमसे संपर्क करें", lead: "वर्तमान प्रकाशित नीति नीचे दिया गया पता दिखाती है। साइन-इन किए हुए उपयोगकर्ता SEVOR के मौजूदा सहायता फ़ॉर्म का भी उपयोग कर सकते हैं।" }
      },
      categories: [
        { title: "खाता जानकारी", body: "नाम, ईमेल पता और फ़ोन नंबर।" },
        { title: "बुकिंग और किराये की जानकारी", body: "बुकिंग और किराये से जुड़ी जानकारी।" },
        { title: "अपलोड की गई तस्वीरें", body: "सत्यापन, पिकअप और वापसी के लिए अपलोड की गई तस्वीरें।" },
        { title: "डिवाइस और उपयोग जानकारी", body: "डिवाइस जानकारी और उपयोग डेटा।" }
      ],
      uses: ["किराये की सेवाएँ देना और बेहतर बनाना।", "पहचान सत्यापित करना।", "बुकिंग और भुगतान संसाधित करना।", "सुरक्षा बढ़ाना और धोखाधड़ी रोकने में सहायता करना।", "खाते के बारे में संवाद करना।"],
      rights: [
        { title: "अपने डेटा तक पहुँच", body: "अपने व्यक्तिगत डेटा तक पहुँच का अनुरोध करें।" },
        { title: "जानकारी सही कराना", body: "अपने व्यक्तिगत डेटा के सुधार का अनुरोध करें।" },
        { title: "हटाने का अनुरोध", body: "अपने व्यक्तिगत डेटा को हटाने का अनुरोध करें।" }
      ],
      deletionCalloutTitle: "मौजूदा खाता हटाने की प्रक्रिया का उपयोग करें",
      deletionCalloutBody: "SEVOR में साइन-इन किए उपयोगकर्ताओं के लिए मौजूदा खाता हटाने का पृष्ठ है। इसके लिए साइन-इन आवश्यक है और यह प्लेटफ़ॉर्म की वर्तमान हटाने की प्रक्रिया का उपयोग करता है; यह पृष्ठ उस प्रक्रिया से आगे हटाने के दायरे या समय का वादा नहीं करता।",
      deletionAction: "खाता हटाना खोलें", supportAction: "सहायता खोलें",
      contactCardTitle: "गोपनीयता संबंधी प्रश्न", policyAddressLabel: "वर्तमान नीति में दिया गया पता:", emailAction: "ईमेल पता",
      languageTitle: "भाषा", languageLead: "इस गोपनीयता केंद्र के लिए अपनी भाषा चुनें।", languageGroupAria: "गोपनीयता केंद्र की भाषा चुनें", selectLanguage: "भाषा चुनें", languageSelected: "हिन्दी चुनी गई।",
      footerNote: "यह गोपनीयता केंद्र वर्तमान में प्रकाशित SEVOR गोपनीयता नीति को दर्शाता है।", footerTop: "ऊपर जाएँ", backTop: "ऊपर जाएँ", backTopAria: "गोपनीयता नीति के शीर्ष पर वापस स्क्रॉल करें"
    },

    zh: {
      htmlLang: "zh-CN", dir: "ltr", languageName: "中文",
      documentTitle: "隐私政策 | SEVOR",
      documentDescription: "了解 SEVOR 如何处理其隐私政策中描述的账户、预订、租赁、上传照片、设备和使用信息。",
      backHome: "返回 SEVOR", backHomeAria: "返回 SEVOR 首页",
      privacyCenter: "隐私中心", heroTitle: "隐私政策",
      heroLead: "清楚了解 SEVOR 当前发布的隐私政策对与您使用平台相关信息的说明。",
      lastUpdated: "最后更新", updatedDate: "等待法律确认", heroAction: "了解您的选择",
      summaryEyebrow: "一目了然", summaryTitle: "清晰的隐私摘要",
      summaryLead: "以下要点反映了 SEVOR 当前已发布政策中说明的信息和用途。",
      summary: [
        { title: "您的数据", body: "政策列明了账户、预订和租赁详情、上传的照片以及设备或使用信息。" },
        { title: "我们为何使用它", body: "用于提供和改进租赁服务、验证身份、处理预订和付款，以及就账户进行沟通。" },
        { title: "您的选择", body: "政策说明您可以请求访问、更正或删除个人数据。" },
        { title: "隐私与安全", body: "安全和防欺诈是 SEVOR 使用信息的已说明原因之一。" }
      ],
      contentsLabel: "本页内容", tocAria: "隐私政策章节",
      toc: { introduction: "简介", collect: "我们收集的信息", use: "我们如何使用信息", rights: "您的隐私权利", deletion: "账户和数据删除", security: "隐私与安全", contact: "联系我们" },
      sections: {
        introduction: { title: "简介", body: "SEVOR 运营网站和移动应用程序。本隐私政策说明 SEVOR 如何收集、使用和保护与平台相关的信息。" },
        collect: { title: "我们收集的信息", lead: "当前发布的政策列出了以下信息类别。" },
        use: { title: "我们如何使用信息", lead: "SEVOR 当前政策列出了使用信息的以下目的。" },
        rights: { title: "您的隐私权利", lead: "当前政策说明，您可以就个人数据请求以下操作。" },
        deletion: { title: "账户和数据删除" },
        security: { title: "隐私与安全", body: "已发布的政策将身份验证、预订和付款处理、安全以及防欺诈列为使用信息的原因。该政策没有发布具体技术安全标准，因此本页面不会作出此类声明。" },
        contact: { title: "联系我们", lead: "当前发布的政策显示以下地址。已登录用户也可以使用 SEVOR 现有的支持表单。" }
      },
      categories: [
        { title: "账户信息", body: "姓名、电子邮件地址和电话号码。" },
        { title: "预订和租赁信息", body: "与预订和租赁相关的信息。" },
        { title: "上传的照片", body: "为验证、取件和归还而上传的照片。" },
        { title: "设备和使用信息", body: "设备信息和使用数据。" }
      ],
      uses: ["提供和改进租赁服务。", "验证身份。", "处理预订和付款。", "提升安全性并帮助防止欺诈。", "就账户进行沟通。"],
      rights: [
        { title: "访问您的数据", body: "请求访问您的个人数据。" },
        { title: "更正信息", body: "请求更正您的个人数据。" },
        { title: "请求删除", body: "请求删除您的个人数据。" }
      ],
      deletionCalloutTitle: "使用现有的账户删除流程",
      deletionCalloutBody: "SEVOR 为已登录用户提供现有的账户删除页面。该页面要求登录并使用平台当前的删除流程；本页面不会承诺该流程之外的删除范围或时间。",
      deletionAction: "打开账户删除", supportAction: "打开支持",
      contactCardTitle: "隐私问题", policyAddressLabel: "当前政策中列出的地址：", emailAction: "电子邮件地址",
      languageTitle: "语言", languageLead: "为此隐私中心选择您的语言。", languageGroupAria: "选择隐私中心语言", selectLanguage: "选择语言", languageSelected: "已选择中文。",
      footerNote: "本隐私中心反映当前已发布的 SEVOR 隐私政策。", footerTop: "返回顶部", backTop: "返回顶部", backTopAria: "滚动回隐私政策顶部"
    },

    es: {
      htmlLang: "es", dir: "ltr", languageName: "Español",
      documentTitle: "Política de privacidad | SEVOR",
      documentDescription: "Conoce cómo SEVOR gestiona la información de cuenta, reserva, alquiler, fotos cargadas, dispositivo y uso descrita en su Política de privacidad.",
      backHome: "Volver a SEVOR", backHomeAria: "Volver a la página de inicio de SEVOR",
      privacyCenter: "Centro de privacidad", heroTitle: "Política de privacidad",
      heroLead: "Conoce con claridad lo que dice la Política de privacidad publicada actualmente por SEVOR sobre la información relacionada con tu uso de la plataforma.",
      lastUpdated: "Última actualización", updatedDate: "Pendiente de confirmación legal", heroAction: "Explora tus opciones",
      summaryEyebrow: "De un vistazo", summaryTitle: "Un resumen claro de privacidad",
      summaryLead: "Los puntos siguientes reflejan la información y las finalidades indicadas en la política actualmente publicada por SEVOR.",
      summary: [
        { title: "Tus datos", body: "La política identifica detalles de cuenta, reserva y alquiler, fotos cargadas e información del dispositivo o de uso." },
        { title: "Por qué los usamos", body: "Para prestar y mejorar servicios de alquiler, verificar la identidad, procesar reservas y pagos, y comunicarnos sobre una cuenta." },
        { title: "Tus opciones", body: "La política indica que puedes solicitar acceso, corrección o eliminación de datos personales." },
        { title: "Privacidad y seguridad", body: "La seguridad y la prevención del fraude están entre los motivos declarados por los que SEVOR usa información." }
      ],
      contentsLabel: "En esta página", tocAria: "Secciones de la Política de privacidad",
      toc: { introduction: "Introducción", collect: "Información que recopilamos", use: "Cómo usamos la información", rights: "Tus derechos de privacidad", deletion: "Eliminación de cuenta y datos", security: "Privacidad y seguridad", contact: "Contáctanos" },
      sections: {
        introduction: { title: "Introducción", body: "SEVOR opera un sitio web y una aplicación móvil. Esta Política de privacidad explica cómo SEVOR recopila, usa y protege información relacionada con la plataforma." },
        collect: { title: "Información que recopilamos", lead: "La política publicada actualmente identifica las siguientes categorías de información." },
        use: { title: "Cómo usamos la información", lead: "La política actual de SEVOR enumera estas finalidades para el uso de información." },
        rights: { title: "Tus derechos de privacidad", lead: "La política actual indica que puedes solicitar las siguientes acciones respecto a tus datos personales." },
        deletion: { title: "Eliminación de cuenta y datos" },
        security: { title: "Privacidad y seguridad", body: "La política publicada identifica la verificación de identidad, el procesamiento de reservas y pagos, la seguridad y la prevención del fraude como motivos para usar información. No publica una norma técnica de seguridad específica, por lo que esta página no hace tal afirmación." },
        contact: { title: "Contáctanos", lead: "La política publicada actualmente muestra la dirección de abajo. Los usuarios que han iniciado sesión también pueden usar el formulario de soporte existente de SEVOR." }
      },
      categories: [
        { title: "Información de cuenta", body: "Nombre, dirección de correo electrónico y número de teléfono." },
        { title: "Información de reserva y alquiler", body: "Información relacionada con reservas y alquileres." },
        { title: "Fotos cargadas", body: "Fotos cargadas para verificación, recogida y devolución." },
        { title: "Información de dispositivo y uso", body: "Información del dispositivo y datos de uso." }
      ],
      uses: ["Prestar y mejorar servicios de alquiler.", "Verificar la identidad.", "Procesar reservas y pagos.", "Mejorar la seguridad y ayudar a prevenir el fraude.", "Comunicarnos sobre una cuenta."],
      rights: [
        { title: "Acceder a tus datos", body: "Solicitar acceso a tus datos personales." },
        { title: "Corregir información", body: "Solicitar la corrección de tus datos personales." },
        { title: "Solicitar eliminación", body: "Solicitar la eliminación de tus datos personales." }
      ],
      deletionCalloutTitle: "Usa el flujo existente de eliminación de cuenta",
      deletionCalloutBody: "SEVOR tiene una página existente de eliminación de cuenta para usuarios que han iniciado sesión. Requiere iniciar sesión y utiliza el flujo de eliminación actual de la plataforma; esta página no promete el alcance ni el plazo de eliminación más allá de ese flujo.",
      deletionAction: "Abrir eliminación de cuenta", supportAction: "Abrir soporte",
      contactCardTitle: "Preguntas sobre privacidad", policyAddressLabel: "Dirección indicada en la política actual:", emailAction: "Dirección de correo",
      languageTitle: "Idioma", languageLead: "Elige tu idioma para este Centro de privacidad.", languageGroupAria: "Elegir un idioma del Centro de privacidad", selectLanguage: "Elegir idioma", languageSelected: "Español seleccionado.",
      footerNote: "Este Centro de privacidad refleja la Política de privacidad de SEVOR publicada actualmente.", footerTop: "Volver arriba", backTop: "Volver arriba", backTopAria: "Volver al inicio de la Política de privacidad"
    },

    pt: {
      htmlLang: "pt", dir: "ltr", languageName: "Português",
      documentTitle: "Política de privacidade | SEVOR",
      documentDescription: "Saiba como a SEVOR trata as informações de conta, reserva, aluguel, fotos enviadas, dispositivo e uso descritas em sua Política de privacidade.",
      backHome: "Voltar à SEVOR", backHomeAria: "Voltar à página inicial da SEVOR",
      privacyCenter: "Centro de privacidade", heroTitle: "Política de privacidade",
      heroLead: "Entenda claramente o que a Política de privacidade atualmente publicada pela SEVOR diz sobre as informações relacionadas ao seu uso da plataforma.",
      lastUpdated: "Última atualização", updatedDate: "Aguardando confirmação jurídica", heroAction: "Conheça suas opções",
      summaryEyebrow: "Em resumo", summaryTitle: "Um resumo claro de privacidade",
      summaryLead: "Os destaques abaixo refletem as informações e finalidades indicadas na política atualmente publicada pela SEVOR.",
      summary: [
        { title: "Seus dados", body: "A política identifica detalhes de conta, reserva e aluguel, fotos enviadas e informações de dispositivo ou uso." },
        { title: "Por que usamos", body: "Para fornecer e melhorar serviços de aluguel, verificar identidade, processar reservas e pagamentos e comunicar sobre uma conta." },
        { title: "Suas escolhas", body: "A política informa que você pode solicitar acesso, correção ou exclusão de dados pessoais." },
        { title: "Privacidade e segurança", body: "Segurança e prevenção a fraudes estão entre as finalidades declaradas para o uso de informações pela SEVOR." }
      ],
      contentsLabel: "Nesta página", tocAria: "Seções da Política de privacidade",
      toc: { introduction: "Introdução", collect: "Informações que coletamos", use: "Como usamos as informações", rights: "Seus direitos de privacidade", deletion: "Exclusão de conta e dados", security: "Privacidade e segurança", contact: "Fale conosco" },
      sections: {
        introduction: { title: "Introdução", body: "A SEVOR opera um site e um aplicativo móvel. Esta Política de privacidade explica como a SEVOR coleta, usa e protege informações relacionadas à plataforma." },
        collect: { title: "Informações que coletamos", lead: "A política atualmente publicada identifica as seguintes categorias de informações." },
        use: { title: "Como usamos as informações", lead: "A política atual da SEVOR lista estas finalidades para o uso de informações." },
        rights: { title: "Seus direitos de privacidade", lead: "A política atual informa que você pode solicitar as seguintes ações em relação aos seus dados pessoais." },
        deletion: { title: "Exclusão de conta e dados" },
        security: { title: "Privacidade e segurança", body: "A política publicada identifica a verificação de identidade, o processamento de reservas e pagamentos, a segurança e a prevenção a fraudes como motivos para usar informações. Ela não publica um padrão técnico de segurança específico; por isso esta página não faz tal alegação." },
        contact: { title: "Fale conosco", lead: "A política atualmente publicada mostra o endereço abaixo. Usuários conectados também podem usar o formulário de suporte existente da SEVOR." }
      },
      categories: [
        { title: "Informações de conta", body: "Nome, endereço de e-mail e número de telefone." },
        { title: "Informações de reserva e aluguel", body: "Informações relacionadas a reservas e aluguéis." },
        { title: "Fotos enviadas", body: "Fotos enviadas para verificação, retirada e devolução." },
        { title: "Informações de dispositivo e uso", body: "Informações de dispositivo e dados de uso." }
      ],
      uses: ["Fornecer e melhorar serviços de aluguel.", "Verificar identidade.", "Processar reservas e pagamentos.", "Aumentar a segurança e ajudar a prevenir fraudes.", "Comunicar sobre uma conta."],
      rights: [
        { title: "Acessar seus dados", body: "Solicitar acesso aos seus dados pessoais." },
        { title: "Corrigir informações", body: "Solicitar correção dos seus dados pessoais." },
        { title: "Solicitar exclusão", body: "Solicitar exclusão dos seus dados pessoais." }
      ],
      deletionCalloutTitle: "Use o fluxo existente de exclusão de conta",
      deletionCalloutBody: "A SEVOR possui uma página existente de exclusão de conta para usuários conectados. Ela exige login e usa o fluxo atual de exclusão da plataforma; esta página não promete o escopo nem o prazo da exclusão além desse fluxo.",
      deletionAction: "Abrir exclusão de conta", supportAction: "Abrir suporte",
      contactCardTitle: "Dúvidas sobre privacidade", policyAddressLabel: "Endereço listado na política atual:", emailAction: "Endereço de e-mail",
      languageTitle: "Idioma", languageLead: "Escolha seu idioma para este Centro de privacidade.", languageGroupAria: "Escolher um idioma do Centro de privacidade", selectLanguage: "Escolher idioma", languageSelected: "Português selecionado.",
      footerNote: "Este Centro de privacidade reflete a Política de privacidade da SEVOR atualmente publicada.", footerTop: "Voltar ao topo", backTop: "Voltar ao topo", backTopAria: "Voltar ao topo da Política de privacidade"
    },

    ru: {
      htmlLang: "ru", dir: "ltr", languageName: "Русский",
      documentTitle: "Политика конфиденциальности | SEVOR",
      documentDescription: "Узнайте, как SEVOR обрабатывает сведения об учетной записи, бронировании, аренде, загруженных фото, устройстве и использовании, описанные в Политике конфиденциальности.",
      backHome: "Вернуться в SEVOR", backHomeAria: "Вернуться на главную страницу SEVOR",
      privacyCenter: "Центр конфиденциальности", heroTitle: "Политика конфиденциальности",
      heroLead: "В понятной форме узнайте, что текущая опубликованная Политика конфиденциальности SEVOR говорит об информации, связанной с использованием платформы.",
      lastUpdated: "Последнее обновление", updatedDate: "Ожидается юридическое подтверждение", heroAction: "Посмотреть ваши варианты",
      summaryEyebrow: "Кратко", summaryTitle: "Понятное резюме конфиденциальности",
      summaryLead: "Приведенные ниже пункты отражают сведения и цели, указанные в текущей опубликованной политике SEVOR.",
      summary: [
        { title: "Ваши данные", body: "Политика указывает данные учетной записи, бронирования и аренды, загруженные фотографии, а также сведения об устройстве или использовании." },
        { title: "Зачем мы их используем", body: "Чтобы предоставлять и улучшать услуги аренды, проверять личность, обрабатывать бронирования и платежи и сообщать сведения об учетной записи." },
        { title: "Ваши варианты", body: "Политика указывает, что вы можете запросить доступ к персональным данным, их исправление или удаление." },
        { title: "Конфиденциальность и безопасность", body: "Безопасность и предотвращение мошенничества входят в заявленные причины использования информации SEVOR." }
      ],
      contentsLabel: "На этой странице", tocAria: "Разделы Политики конфиденциальности",
      toc: { introduction: "Введение", collect: "Какие сведения мы собираем", use: "Как мы используем сведения", rights: "Ваши права на конфиденциальность", deletion: "Удаление учетной записи и данных", security: "Конфиденциальность и безопасность", contact: "Связаться с нами" },
      sections: {
        introduction: { title: "Введение", body: "SEVOR управляет веб-сайтом и мобильным приложением. Эта Политика конфиденциальности объясняет, как SEVOR собирает, использует и защищает информацию, связанную с платформой." },
        collect: { title: "Какие сведения мы собираем", lead: "Текущая опубликованная политика определяет следующие категории информации." },
        use: { title: "Как мы используем сведения", lead: "Текущая политика SEVOR перечисляет следующие цели использования информации." },
        rights: { title: "Ваши права на конфиденциальность", lead: "Текущая политика указывает, что вы можете запросить следующие действия в отношении ваших персональных данных." },
        deletion: { title: "Удаление учетной записи и данных" },
        security: { title: "Конфиденциальность и безопасность", body: "Опубликованная политика называет проверку личности, обработку бронирований и платежей, безопасность и предотвращение мошенничества причинами использования информации. В ней не указан конкретный технический стандарт безопасности, поэтому эта страница не делает такого заявления." },
        contact: { title: "Связаться с нами", lead: "В текущей опубликованной политике указан адрес ниже. Авторизованные пользователи также могут воспользоваться существующей формой поддержки SEVOR." }
      },
      categories: [
        { title: "Сведения об учетной записи", body: "Имя, адрес электронной почты и номер телефона." },
        { title: "Сведения о бронировании и аренде", body: "Информация, связанная с бронированиями и арендой." },
        { title: "Загруженные фотографии", body: "Фотографии, загруженные для проверки, получения и возврата." },
        { title: "Сведения об устройстве и использовании", body: "Сведения об устройстве и данные об использовании." }
      ],
      uses: ["Предоставлять и улучшать услуги аренды.", "Проверять личность.", "Обрабатывать бронирования и платежи.", "Повышать безопасность и помогать предотвращать мошенничество.", "Сообщать сведения об учетной записи."],
      rights: [
        { title: "Доступ к вашим данным", body: "Запросить доступ к своим персональным данным." },
        { title: "Исправить сведения", body: "Запросить исправление своих персональных данных." },
        { title: "Запросить удаление", body: "Запросить удаление своих персональных данных." }
      ],
      deletionCalloutTitle: "Используйте существующий процесс удаления учетной записи",
      deletionCalloutBody: "В SEVOR есть существующая страница удаления учетной записи для авторизованных пользователей. Она требует входа и использует текущий процесс удаления платформы; эта страница не обещает объем или сроки удаления за пределами этого процесса.",
      deletionAction: "Открыть удаление учетной записи", supportAction: "Открыть поддержку",
      contactCardTitle: "Вопросы о конфиденциальности", policyAddressLabel: "Адрес, указанный в текущей политике:", emailAction: "Адрес электронной почты",
      languageTitle: "Язык", languageLead: "Выберите язык для этого Центра конфиденциальности.", languageGroupAria: "Выберите язык Центра конфиденциальности", selectLanguage: "Выберите язык", languageSelected: "Выбран русский язык.",
      footerNote: "Этот Центр конфиденциальности отражает текущую опубликованную Политику конфиденциальности SEVOR.", footerTop: "Наверх", backTop: "Наверх", backTopAria: "Прокрутить к началу Политики конфиденциальности"
    },

    de: {
      htmlLang: "de", dir: "ltr", languageName: "Deutsch",
      documentTitle: "Datenschutzerklärung | SEVOR",
      documentDescription: "Erfahren Sie, wie SEVOR die in seiner Datenschutzerklärung beschriebenen Konto-, Buchungs-, Miet-, hochgeladenen Foto-, Geräte- und Nutzungsinformationen verarbeitet.",
      backHome: "Zurück zu SEVOR", backHomeAria: "Zur SEVOR-Startseite zurückkehren",
      privacyCenter: "Datenschutzzentrum", heroTitle: "Datenschutzerklärung",
      heroLead: "Erfahren Sie klar und verständlich, was die derzeit veröffentlichte Datenschutzerklärung von SEVOR über Informationen im Zusammenhang mit Ihrer Nutzung der Plattform aussagt.",
      lastUpdated: "Zuletzt aktualisiert", updatedDate: "Rechtliche Bestätigung ausstehend", heroAction: "Ihre Optionen ansehen",
      summaryEyebrow: "Auf einen Blick", summaryTitle: "Eine klare Datenschutz-Zusammenfassung",
      summaryLead: "Die folgenden Hinweise spiegeln die Informationen und Zwecke wider, die in der derzeit veröffentlichten SEVOR-Richtlinie genannt werden.",
      summary: [
        { title: "Ihre Daten", body: "Die Richtlinie nennt Konto-, Buchungs- und Mietdaten, hochgeladene Fotos sowie Geräte- oder Nutzungsinformationen." },
        { title: "Warum wir sie verwenden", body: "Um Mietdienste bereitzustellen und zu verbessern, die Identität zu prüfen, Buchungen und Zahlungen zu bearbeiten und über ein Konto zu kommunizieren." },
        { title: "Ihre Optionen", body: "Die Richtlinie besagt, dass Sie Zugang zu personenbezogenen Daten, deren Berichtigung oder Löschung anfordern können." },
        { title: "Datenschutz und Sicherheit", body: "Sicherheit und Betrugsprävention gehören zu den genannten Gründen, aus denen SEVOR Informationen verwendet." }
      ],
      contentsLabel: "Auf dieser Seite", tocAria: "Abschnitte der Datenschutzerklärung",
      toc: { introduction: "Einleitung", collect: "Von uns erhobene Informationen", use: "Wie wir Informationen verwenden", rights: "Ihre Datenschutzrechte", deletion: "Konto- und Datenlöschung", security: "Datenschutz und Sicherheit", contact: "Kontakt" },
      sections: {
        introduction: { title: "Einleitung", body: "SEVOR betreibt eine Website und eine mobile Anwendung. Diese Datenschutzerklärung erläutert, wie SEVOR mit Informationen im Zusammenhang mit der Plattform umgeht, sie erhebt, verwendet und schützt." },
        collect: { title: "Von uns erhobene Informationen", lead: "Die derzeit veröffentlichte Richtlinie nennt die folgenden Informationskategorien." },
        use: { title: "Wie wir Informationen verwenden", lead: "Die aktuelle SEVOR-Richtlinie nennt diese Zwecke für die Verwendung von Informationen." },
        rights: { title: "Ihre Datenschutzrechte", lead: "Die aktuelle Richtlinie besagt, dass Sie die folgenden Maßnahmen in Bezug auf Ihre personenbezogenen Daten anfordern können." },
        deletion: { title: "Konto- und Datenlöschung" },
        security: { title: "Datenschutz und Sicherheit", body: "Die veröffentlichte Richtlinie nennt Identitätsprüfung, Buchungs- und Zahlungsabwicklung, Sicherheit und Betrugsprävention als Gründe für die Verwendung von Informationen. Sie veröffentlicht keinen bestimmten technischen Sicherheitsstandard; diese Seite behauptet daher keinen solchen Standard." },
        contact: { title: "Kontakt", lead: "Die derzeit veröffentlichte Richtlinie zeigt die untenstehende Adresse. Angemeldete Nutzer können auch das bestehende Supportformular von SEVOR verwenden." }
      },
      categories: [
        { title: "Kontoinformationen", body: "Name, E-Mail-Adresse und Telefonnummer." },
        { title: "Buchungs- und Mietinformationen", body: "Informationen im Zusammenhang mit Buchungen und Vermietungen." },
        { title: "Hochgeladene Fotos", body: "Fotos, die zur Verifizierung, Abholung und Rückgabe hochgeladen wurden." },
        { title: "Geräte- und Nutzungsinformationen", body: "Geräteinformationen und Nutzungsdaten." }
      ],
      uses: ["Mietdienste bereitstellen und verbessern.", "Identität prüfen.", "Buchungen und Zahlungen bearbeiten.", "Sicherheit verbessern und Betrug verhindern helfen.", "Über ein Konto kommunizieren."],
      rights: [
        { title: "Auf Ihre Daten zugreifen", body: "Zugang zu Ihren personenbezogenen Daten anfordern." },
        { title: "Informationen berichtigen", body: "Berichtigung Ihrer personenbezogenen Daten anfordern." },
        { title: "Löschung anfordern", body: "Löschung Ihrer personenbezogenen Daten anfordern." }
      ],
      deletionCalloutTitle: "Verwenden Sie den bestehenden Prozess zur Kontolöschung",
      deletionCalloutBody: "SEVOR verfügt über eine bestehende Seite zur Kontolöschung für angemeldete Nutzer. Sie erfordert eine Anmeldung und verwendet den aktuellen Löschprozess der Plattform; diese Seite verspricht keinen Umfang oder Zeitpunkt der Löschung über diesen Prozess hinaus.",
      deletionAction: "Kontolöschung öffnen", supportAction: "Support öffnen",
      contactCardTitle: "Fragen zum Datenschutz", policyAddressLabel: "In der aktuellen Richtlinie aufgeführte Adresse:", emailAction: "E-Mail-Adresse",
      languageTitle: "Sprache", languageLead: "Wählen Sie Ihre Sprache für dieses Datenschutzzentrum.", languageGroupAria: "Sprache für das Datenschutzzentrum auswählen", selectLanguage: "Sprache auswählen", languageSelected: "Deutsch ausgewählt.",
      footerNote: "Dieses Datenschutzzentrum spiegelt die derzeit veröffentlichte SEVOR-Datenschutzerklärung wider.", footerTop: "Nach oben", backTop: "Nach oben", backTopAria: "Zum Anfang der Datenschutzerklärung scrollen"
    },

    it: {
      htmlLang: "it", dir: "ltr", languageName: "Italiano",
      documentTitle: "Informativa sulla privacy | SEVOR",
      documentDescription: "Scopri come SEVOR gestisce le informazioni su account, prenotazioni, noleggi, foto caricate, dispositivo e utilizzo descritte nella sua Informativa sulla privacy.",
      backHome: "Torna a SEVOR", backHomeAria: "Torna alla pagina iniziale di SEVOR",
      privacyCenter: "Centro privacy", heroTitle: "Informativa sulla privacy",
      heroLead: "Scopri con chiarezza cosa dice l'Informativa sulla privacy attualmente pubblicata da SEVOR sulle informazioni collegate al tuo utilizzo della piattaforma.",
      lastUpdated: "Ultimo aggiornamento", updatedDate: "In attesa di conferma legale", heroAction: "Esplora le tue opzioni",
      summaryEyebrow: "In breve", summaryTitle: "Un riepilogo chiaro della privacy",
      summaryLead: "I punti seguenti riflettono le informazioni e le finalità indicate nella politica SEVOR attualmente pubblicata.",
      summary: [
        { title: "I tuoi dati", body: "La politica identifica dettagli di account, prenotazione e noleggio, foto caricate e informazioni sul dispositivo o sull'utilizzo." },
        { title: "Perché li usiamo", body: "Per fornire e migliorare i servizi di noleggio, verificare l'identità, elaborare prenotazioni e pagamenti e comunicare in merito a un account." },
        { title: "Le tue opzioni", body: "La politica indica che puoi richiedere accesso, correzione o eliminazione dei dati personali." },
        { title: "Privacy e sicurezza", body: "Sicurezza e prevenzione delle frodi sono tra le finalità dichiarate per cui SEVOR utilizza informazioni." }
      ],
      contentsLabel: "In questa pagina", tocAria: "Sezioni dell'Informativa sulla privacy",
      toc: { introduction: "Introduzione", collect: "Informazioni raccolte", use: "Come utilizziamo le informazioni", rights: "I tuoi diritti sulla privacy", deletion: "Eliminazione di account e dati", security: "Privacy e sicurezza", contact: "Contattaci" },
      sections: {
        introduction: { title: "Introduzione", body: "SEVOR gestisce un sito web e un'applicazione mobile. Questa Informativa sulla privacy spiega come SEVOR raccoglie, utilizza e protegge le informazioni collegate alla piattaforma." },
        collect: { title: "Informazioni raccolte", lead: "La politica attualmente pubblicata identifica le seguenti categorie di informazioni." },
        use: { title: "Come utilizziamo le informazioni", lead: "L'attuale politica di SEVOR elenca queste finalità per l'utilizzo delle informazioni." },
        rights: { title: "I tuoi diritti sulla privacy", lead: "La politica attuale indica che puoi richiedere le seguenti azioni relative ai tuoi dati personali." },
        deletion: { title: "Eliminazione di account e dati" },
        security: { title: "Privacy e sicurezza", body: "La politica pubblicata identifica la verifica dell'identità, l'elaborazione di prenotazioni e pagamenti, la sicurezza e la prevenzione delle frodi come ragioni per l'uso delle informazioni. Non pubblica uno standard tecnico di sicurezza specifico; questa pagina non fa quindi tale affermazione." },
        contact: { title: "Contattaci", lead: "La politica attualmente pubblicata mostra l'indirizzo seguente. Gli utenti che hanno effettuato l'accesso possono anche usare il modulo di assistenza esistente di SEVOR." }
      },
      categories: [
        { title: "Informazioni sull'account", body: "Nome, indirizzo e-mail e numero di telefono." },
        { title: "Informazioni su prenotazioni e noleggi", body: "Informazioni collegate a prenotazioni e noleggi." },
        { title: "Foto caricate", body: "Foto caricate per verifica, ritiro e restituzione." },
        { title: "Informazioni su dispositivo e utilizzo", body: "Informazioni sul dispositivo e dati di utilizzo." }
      ],
      uses: ["Fornire e migliorare i servizi di noleggio.", "Verificare l'identità.", "Elaborare prenotazioni e pagamenti.", "Migliorare la sicurezza e contribuire a prevenire le frodi.", "Comunicare in merito a un account."],
      rights: [
        { title: "Accedere ai tuoi dati", body: "Richiedere accesso ai tuoi dati personali." },
        { title: "Correggere le informazioni", body: "Richiedere la correzione dei tuoi dati personali." },
        { title: "Richiedere l'eliminazione", body: "Richiedere l'eliminazione dei tuoi dati personali." }
      ],
      deletionCalloutTitle: "Usa il flusso esistente di eliminazione dell'account",
      deletionCalloutBody: "SEVOR dispone di una pagina esistente di eliminazione dell'account per gli utenti che hanno effettuato l'accesso. Richiede l'accesso e utilizza l'attuale flusso di eliminazione della piattaforma; questa pagina non promette l'ambito o i tempi dell'eliminazione oltre tale flusso.",
      deletionAction: "Apri eliminazione account", supportAction: "Apri assistenza",
      contactCardTitle: "Domande sulla privacy", policyAddressLabel: "Indirizzo indicato nella politica attuale:", emailAction: "Indirizzo e-mail",
      languageTitle: "Lingua", languageLead: "Scegli la lingua per questo Centro privacy.", languageGroupAria: "Scegli la lingua del Centro privacy", selectLanguage: "Scegli lingua", languageSelected: "Italiano selezionato.",
      footerNote: "Questo Centro privacy riflette l'Informativa sulla privacy SEVOR attualmente pubblicata.", footerTop: "Torna in alto", backTop: "Torna in alto", backTopAria: "Torna all'inizio dell'Informativa sulla privacy"
    }
  };

  const root = document.getElementById("privacy-center");
  if (!root) return;

  const storageKey = "sevor.privacy.language";
  const reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const getPath = (object, path) => path.split(".").reduce((value, part) => (value == null ? undefined : value[part]), object);
  const textNodes = [...root.querySelectorAll("[data-i18n]")];
  const ariaNodes = [...root.querySelectorAll("[data-i18n-aria]")];
  const languageButtons = [...root.querySelectorAll(".privacy-language[data-language]")];
  const tocLinks = [...root.querySelectorAll(".privacy-toc-link[data-section-link]")];
  const statusNode = document.getElementById("privacy-language-status");
  const progressBar = document.getElementById("privacy-progress-bar");
  const backTop = document.getElementById("privacy-back-top");

  const validateTranslations = () => {
    const requiredPaths = [...new Set([
      ...textNodes.map((node) => node.dataset.i18n),
      ...ariaNodes.map((node) => node.dataset.i18nAria)
    ])];
    Object.entries(translations).forEach(([language, copy]) => {
      requiredPaths.forEach((path) => {
        if (typeof getPath(copy, path) !== "string") {
          console.warn(`[SEVOR Privacy Center] Missing ${path} for ${language}.`);
        }
      });
    });
  };

  const updateDocumentMetadata = (copy) => {
    document.documentElement.lang = copy.htmlLang;
    document.documentElement.dir = copy.dir;
    document.title = copy.documentTitle;
    const description = document.querySelector('meta[name="description"]');
    if (description) description.setAttribute("content", copy.documentDescription);
  };

  const updateFixedControls = () => {
    const maxScroll = Math.max(0, document.documentElement.scrollHeight - window.innerHeight);
    const progress = maxScroll ? Math.min(1, Math.max(0, window.scrollY / maxScroll)) : 0;
    if (progressBar) progressBar.style.transform = `scaleX(${progress})`;
    if (backTop) {
      const visible = window.scrollY > 480;
      backTop.classList.toggle("is-visible", visible);
      backTop.tabIndex = visible ? 0 : -1;
      backTop.setAttribute("aria-hidden", String(!visible));
    }
  };

  const setActiveSection = (id) => {
    tocLinks.forEach((link) => link.classList.toggle("is-active", link.dataset.sectionLink === id));
  };

  const setupObservers = () => {
    const revealTargets = [...root.querySelectorAll("[data-privacy-reveal]")];
    if (!reduceMotion) {
      document.documentElement.classList.add("privacy-motion-ready");
      if ("IntersectionObserver" in window) {
        const revealObserver = new IntersectionObserver((entries, observer) => {
          entries.forEach((entry) => {
            if (!entry.isIntersecting) return;
            entry.target.classList.add("is-visible");
            observer.unobserve(entry.target);
          });
        }, { rootMargin: "0px 0px -8%", threshold: 0.06 });
        revealTargets.forEach((target) => revealObserver.observe(target));
      } else {
        revealTargets.forEach((target) => target.classList.add("is-visible"));
      }
    } else {
      revealTargets.forEach((target) => target.classList.add("is-visible"));
    }

    const sections = [...root.querySelectorAll(".privacy-section[id]")];
    if ("IntersectionObserver" in window && sections.length) {
      const tocObserver = new IntersectionObserver((entries) => {
        const visible = entries.filter((entry) => entry.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible[0]) setActiveSection(visible[0].target.id);
      }, { rootMargin: "-18% 0px -67%", threshold: 0 });
      sections.forEach((section) => tocObserver.observe(section));
    } else if (sections[0]) {
      setActiveSection(sections[0].id);
    }
  };

  const closeMobileContents = () => {
    const details = root.querySelector(".privacy-toc-mobile[open]");
    if (details) details.open = false;
  };

  const setLanguage = (language, announce = true) => {
    const code = Object.prototype.hasOwnProperty.call(translations, language) ? language : "en";
    const copy = translations[code];
    const apply = () => {
      root.dataset.language = code;
      root.dir = copy.dir;
      updateDocumentMetadata(copy);
      textNodes.forEach((node) => {
        const value = getPath(copy, node.dataset.i18n);
        if (typeof value === "string") node.textContent = value;
      });
      ariaNodes.forEach((node) => {
        const value = getPath(copy, node.dataset.i18nAria);
        if (typeof value === "string") node.setAttribute("aria-label", value);
      });
      root.querySelector(".privacy-toc")?.setAttribute("aria-label", copy.tocAria);
      languageButtons.forEach((button) => {
        const selected = button.dataset.language === code;
        const name = button.querySelector(".privacy-language__name")?.textContent || button.dataset.language;
        button.setAttribute("aria-pressed", String(selected));
        button.setAttribute("aria-label", `${copy.selectLanguage}: ${name}`);
      });
      if (statusNode) statusNode.textContent = announce ? copy.languageSelected : "";
      try { window.localStorage.setItem(storageKey, code); } catch (_) {}
      updateFixedControls();
    };

    if (announce && !reduceMotion) {
      root.classList.add("is-translating");
      window.setTimeout(() => {
        apply();
        window.requestAnimationFrame(() => root.classList.remove("is-translating"));
      }, 90);
    } else {
      apply();
    }
  };

  languageButtons.forEach((button) => button.addEventListener("click", () => setLanguage(button.dataset.language, true)));
  root.querySelectorAll('a[href^="#"]').forEach((link) => link.addEventListener("click", (event) => {
    const target = document.querySelector(link.getAttribute("href"));
    if (!target) return;
    event.preventDefault();
    target.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "start" });
    closeMobileContents();
  }));
  if (backTop) backTop.addEventListener("click", () => window.scrollTo({ top: 0, behavior: reduceMotion ? "auto" : "smooth" }));
  window.addEventListener("scroll", updateFixedControls, { passive: true });
  window.addEventListener("resize", updateFixedControls, { passive: true });

  let initialLanguage = "en";
  try {
    const stored = window.localStorage.getItem(storageKey);
    if (stored && translations[stored]) initialLanguage = stored;
  } catch (_) {}

  validateTranslations();
  setupObservers();
  setLanguage(initialLanguage, false);
  updateFixedControls();
})();
