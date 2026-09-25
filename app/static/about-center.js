(() => {
  "use strict";
  const root = document.getElementById("about-center");
  if (!root) return;
  const storageKey = "sevor.about.language";
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const en = {
    languageName: "English",
    lang: "en",
    dir: "ltr",
    pageTitle: "About SEVOR | Rent what you need",
    metaDescription: "Discover SEVOR, a rental marketplace for finding temporary access to useful items and making suitable items available for rent.",
    homeAria: "Return to the SEVOR home page",
    localNavAria: "About SEVOR sections",
    tabListAria: "Choose a SEVOR journey",
    languageGroupAria: "Choose an About language",
    flywheelAria: "SEVOR marketplace loop",
    backTopAria: "Back to the top of this page",
    languageSelected: "{language} selected for this About page.",
    homeLink: "Back to SEVOR",
    kicker: "A rental marketplace",
    heroTitle: "Rent what you need. Earn from what you own.",
    heroLead: "SEVOR helps people and companies discover temporary access to useful things and make suitable items available for rent.",
    exploreCta: "Explore rentals",
    listCta: "List an item",
    registerCta: "Create an account",
    orbitRentTitle: "Find access",
    orbitRentBody: "For a day, project, trip, or occasion.",
    orbitListTitle: "Share availability",
    orbitListBody: "Make a suitable item available.",
    orbitNote: "One marketplace for rental opportunities.",
    navOverview: "Overview",
    navHow: "How it works",
    navRenters: "For renters",
    navOwners: "For owners",
    navBusiness: "For companies",
    navTrust: "Trust",
    navVision: "Vision",
    overviewEyebrow: "What is SEVOR?",
    overviewTitle: "A marketplace for temporary access.",
    overviewLead: "SEVOR connects renters looking for something to use for a limited time with owners and providers who have suitable items available to rent.",
    overviewCards: [
      { title: "Renters", body: "People or organizations seeking access to an item for a defined period." },
      { title: "Owners & providers", body: "Individuals or companies making suitable items available through listings." },
      { title: "Rental opportunities", body: "A place to discover, review, request, and complete rentals when listings are available." }
    ],
    problemQuote: "Why buy something you may only need for a short time?",
    problemBody: "A tool, camera, vehicle, device, or other item may be useful for a day, a week, a project, or an occasion. Ownership can make sense in some situations; in others, temporary access may be worth exploring.",
    problemPoint1: "Discover rental options when they are available.",
    problemPoint2: "Help suitable unused items become useful to someone else.",
    compareEyebrow: "A practical choice",
    compareTitle: "Rent and buy solve different needs.",
    buyLabel: "BUY",
    buyTitle: "Choose ownership",
    buy: ["Pay the full purchase price.", "Keep the item.", "Store and maintain it.", "Useful when ownership makes sense."],
    rentLabel: "RENT",
    rentTitle: "Choose temporary access",
    rent: ["Pay for agreed temporary access.", "Use the item during the rental period.", "Return it afterward.", "Useful when temporary access makes more sense."],
    audienceEyebrow: "Who is SEVOR for?",
    audienceTitle: "Made for people and companies taking part in rentals.",
    audienceLead: "SEVOR supports individual and company account types. Available listings, not a promise about every category, determine what each person can find.",
    audienceCards: [
      { title: "Individuals", body: "People looking for temporary access to useful things." },
      { title: "Renters", body: "Users who compare listings, review details, and make booking requests." },
      { title: "Owners", body: "People who want to make suitable items available when they are not using them." },
      { title: "Companies", body: "Company accounts can use the same marketplace flow for suitable rental listings and needs." }
    ],
    relationshipsEyebrow: "One marketplace, multiple relationships",
    relationshipsTitle: "Rent from people or companies when matching listings are available.",
    relationshipsLead: "The current account and booking model does not limit a booking to one account-type pairing. These relationships are possible through the same rental flow.",
    relationships: [
      { title: "Individual → Individual", body: "A rental between individual accounts." },
      { title: "Company → Individual", body: "An individual renting from a company account." },
      { title: "Individual → Company", body: "A company renting from an individual account." },
      { title: "Company → Company", body: "A rental between company accounts." }
    ],
    howEyebrow: "How SEVOR works",
    howTitle: "Choose the journey that fits your next step.",
    howLead: "These two views reflect the current listing and booking flow without changing how the platform works.",
    rentTab: "I want to rent",
    listTab: "I want to list",
    rentSteps: [
      { title: "Explore", body: "Search and filter available listings." },
      { title: "Review", body: "Read listing details, pricing, location, and ratings." },
      { title: "Request", body: "Choose dates and submit a booking request." },
      { title: "Complete the rental", body: "After an owner decision, follow the current payment, pickup, return, and review steps where applicable." }
    ],
    listSteps: [
      { title: "Prepare", body: "Use an approved account and choose a suitable item to list." },
      { title: "Create", body: "Add photos, details, location, category, and daily price." },
      { title: "Manage requests", body: "Review booking requests and respond through the current flow." },
      { title: "Complete rentals", body: "Coordinate the rental steps, evidence, and feedback where they apply." }
    ],
    rentersEyebrow: "For renters",
    rentersTitle: "Find the right temporary access for the moment.",
    rentersLead: "Browse current listings, compare what is available, review details, and continue through the booking flow when a listing fits.",
    renterCards: [
      { title: "Discover", body: "Explore listings using the available search and filters.", point1: "Compare listing details.", point2: "See individual or company listings when available." },
      { title: "Book", body: "Select dates and request a booking through the platform.", point1: "An owner can accept or reject a request.", point2: "Some accepted bookings can include a security amount." },
      { title: "Build experience", body: "Use the booking, messaging, evidence, and review tools available for the rental.", point1: "Follow pickup and return steps when required.", point2: "Leave booking-linked feedback after eligible rentals." }
    ],
    ownersEyebrow: "For owners",
    ownersTitle: "Make suitable items available when you are not using them.",
    ownersLead: "A completed rental can create a rental-income opportunity for an owner. It is not a promise of income, demand, or a particular result.",
    ownerCards: [
      { title: "Create a clear listing", body: "Add the information that helps renters understand a suitable item.", point1: "Photos and item details.", point2: "Category, city, and daily price." },
      { title: "Respond to requests", body: "Review incoming booking requests and use the current decision flow.", point1: "Accept or reject a request.", point2: "Set a deposit where the booking flow allows it." },
      { title: "Create an opportunity", body: "A suitable unused asset may earn rental income when a rental is completed.", point1: "Keep account payout preferences current.", point2: "Use evidence and feedback tools where relevant." }
    ],
    businessEyebrow: "For companies",
    businessTitle: "Company accounts can take part in the same rental marketplace.",
    businessLead: "SEVOR currently recognizes individual and company account types. A company can use the existing listing and booking flow for suitable rental needs or offers; this page does not imply separate enterprise tools.",
    businessQuote: "A company can be an owner, a renter, or both—depending on the available listings and its needs.",
    businessBody: "Suitable equipment or assets can be made available through listings. A company that needs temporary access can also explore the same marketplace. The platform’s booking model is shared rather than a separate business-only flow.",
    businessPoint1: "Company registration includes a company-proof step.",
    businessPoint2: "Explore can filter listings from companies or individuals.",
    categoriesEyebrow: "What can you rent?",
    categoriesTitle: "Explore categories used by SEVOR today.",
    categoriesLead: "The marketplace can show listings across these high-level categories; actual availability depends on current listings.",
    categories: ["Vehicles", "Housing & Stays", "Electronics", "Furniture", "Clothing", "Tools & Equipment", "Other"],
    trustEyebrow: "Built around practical trust tools",
    trustTitle: "Tools that support informed rental decisions.",
    trustLead: "SEVOR includes mechanisms that help users document, communicate about, and manage rentals. They support the process; they are not a guarantee of any outcome.",
    trustCards: [
      { title: "Identity & company verification", body: "The platform collects verification documents, including ID card, driver’s licence, passport, and company proof, with review paths." },
      { title: "Booking records", body: "Booking requests, decisions, and rental-related steps are recorded within the current flow." },
      { title: "Rental communication", body: "Item-linked messaging helps eligible participants communicate about a rental." },
      { title: "Evidence paths", body: "Pickup, return, and deposit-related evidence tools exist where the rental flow requires them." },
      { title: "Reviews & ratings", body: "Booking-linked feedback helps users learn from previous rental experiences without guaranteeing quality." },
      { title: "Support & reports", body: "Support tickets and listing-report paths are available through the existing platform tools." }
    ],
    paymentsQuote: "Accepted online bookings use the current PayPal payment flow.",
    paymentsBody: "Owners can maintain payout preferences for Interac, PayPal, or Wise in the current account settings. The current payout workflow is manual, so this page makes no promise about timing, availability, or a payout result.",
    paymentsPoint1: "A security amount can apply to some bookings.",
    paymentsPoint2: "Deposit evidence and review paths apply where relevant.",
    visionEyebrow: "Access over ownership",
    visionTitle: "Built with a flexible, global vision for rentals.",
    visionLead: "SEVOR is designed to make rental discovery and access more flexible for people and companies. When a suitable item already exists and is made available, temporary rental can be an alternative to buying something new for some uses.",
    visionCards: [
      { title: "Access what you need", body: "Find temporary access when a listing matches a need." },
      { title: "Use more of what exists", body: "Suitable assets can become useful when their owners make them available." },
      { title: "Grow useful choice", body: "More relevant listings can create more opportunities to discover rentals." }
    ],
    whyEyebrow: "Why SEVOR?",
    whyTitle: "A simple marketplace loop.",
    whyLead: "No counters or guaranteed results—just the practical relationship between useful listings and rental opportunities.",
    flywheel: ["More useful items are listed", "More choice for renters", "More completed rentals can create more owner opportunities"],
    finalEyebrow: "Your next rental",
    finalTitle: "Ready to rent differently?",
    finalLead: "Explore what is available now, or make a suitable item available through a listing.",
    languageTitle: "Choose your About language",
    languageLead: "Your preference is kept for this About page when you return.",
    footerNote: "SEVOR is a marketplace: availability depends on current listings.",
    privacyLink: "Privacy Center",
    backTop: "Back to top"
  };
  const completeLocale = (locale) => ({ ...en, ...locale });

  const fr = completeLocale({
    languageName: "Français",
    lang: "fr",
    pageTitle: "À propos de SEVOR | Louez ce dont vous avez besoin",
    metaDescription: "Découvrez SEVOR, une place de marché de location pour trouver un accès temporaire à des biens utiles et proposer des articles adaptés à la location.",
    homeAria: "Retour à la page d’accueil SEVOR",
    localNavAria: "Sections À propos de SEVOR",
    tabListAria: "Choisir un parcours SEVOR",
    languageGroupAria: "Choisir une langue pour À propos",
    flywheelAria: "Boucle de la place de marché SEVOR",
    backTopAria: "Retour en haut de cette page",
    languageSelected: "{language} est sélectionné pour cette page À propos.",
    homeLink: "Retour à SEVOR",
    kicker: "Une place de marché de location",
    heroTitle: "Louez ce dont vous avez besoin. Gagnez de l’argent avec ce que vous possédez.",
    heroLead: "SEVOR aide les particuliers et les entreprises à trouver un accès temporaire à des biens utiles et à proposer à la location des articles adaptés.",
    exploreCta: "Explorer les locations",
    listCta: "Mettre un article en ligne",
    registerCta: "Créer un compte",
    orbitRentTitle: "Trouver un accès",
    orbitRentBody: "Pour une journée, un projet, un voyage ou une occasion.",
    orbitListTitle: "Partager la disponibilité",
    orbitListBody: "Rendre un article adapté disponible.",
    orbitNote: "Une seule place de marché pour les occasions de location.",
    navOverview: "Vue d’ensemble",
    navHow: "Fonctionnement",
    navRenters: "Pour les locataires",
    navOwners: "Pour les propriétaires",
    navBusiness: "Pour les entreprises",
    navTrust: "Confiance",
    navVision: "Vision",
    overviewEyebrow: "Qu’est-ce que SEVOR ?",
    overviewTitle: "Une place de marché pour un accès temporaire.",
    overviewLead: "SEVOR met en relation des locataires qui cherchent à utiliser quelque chose pendant une période limitée avec des propriétaires et fournisseurs disposant d’articles adaptés à louer.",
    overviewCards: [
      { title: "Locataires", body: "Des personnes ou organisations qui cherchent à accéder à un article pour une période définie." },
      { title: "Propriétaires et fournisseurs", body: "Des particuliers ou entreprises qui rendent des articles adaptés disponibles par des annonces." },
      { title: "Occasions de location", body: "Un espace pour découvrir, examiner, demander et réaliser des locations lorsque des annonces sont disponibles." }
    ],
    problemQuote: "Pourquoi acheter quelque chose dont vous pourriez n’avoir besoin que peu de temps ?",
    problemBody: "Un outil, un appareil photo, un véhicule, un appareil ou un autre article peut être utile pour une journée, une semaine, un projet ou une occasion. La propriété peut avoir du sens dans certaines situations ; dans d’autres, l’accès temporaire peut valoir la peine d’être envisagé.",
    problemPoint1: "Découvrez les options de location lorsqu’elles sont disponibles.",
    problemPoint2: "Aidez des articles adaptés et inutilisés à devenir utiles à quelqu’un d’autre.",
    compareEyebrow: "Un choix pratique",
    compareTitle: "Louer et acheter répondent à des besoins différents.",
    buyLabel: "ACHETER",
    buyTitle: "Choisir la propriété",
    buy: ["Payer le prix d’achat complet.", "Conserver l’article.", "Le ranger et l’entretenir.", "Utile lorsque la propriété a du sens."],
    rentLabel: "LOUER",
    rentTitle: "Choisir l’accès temporaire",
    rent: ["Payer pour l’accès temporaire convenu.", "Utiliser l’article pendant la période de location.", "Le restituer ensuite.", "Utile lorsque l’accès temporaire a davantage de sens."],
    audienceEyebrow: "À qui s’adresse SEVOR ?",
    audienceTitle: "Pensé pour les particuliers et les entreprises qui participent à des locations.",
    audienceLead: "SEVOR prend en charge les types de compte individuel et entreprise. Les annonces disponibles, et non une promesse concernant chaque catégorie, déterminent ce que chacun peut trouver.",
    audienceCards: [
      { title: "Particuliers", body: "Des personnes qui recherchent un accès temporaire à des biens utiles." },
      { title: "Locataires", body: "Des utilisateurs qui comparent les annonces, examinent les détails et font des demandes de réservation." },
      { title: "Propriétaires", body: "Des personnes qui souhaitent rendre des articles adaptés disponibles lorsqu’elles ne les utilisent pas." },
      { title: "Entreprises", body: "Les comptes d’entreprise peuvent utiliser le même parcours de marché pour des offres et besoins de location adaptés." }
    ],
    relationshipsEyebrow: "Une place de marché, plusieurs relations",
    relationshipsTitle: "Louez auprès de particuliers ou d’entreprises lorsque des annonces correspondantes sont disponibles.",
    relationshipsLead: "Le modèle actuel de compte et de réservation ne limite pas une réservation à une combinaison de types de comptes. Ces relations sont possibles dans le même parcours de location.",
    relationships: [
      { title: "Particulier → Particulier", body: "Une location entre comptes individuels." },
      { title: "Entreprise → Particulier", body: "Un particulier qui loue auprès d’un compte d’entreprise." },
      { title: "Particulier → Entreprise", body: "Une entreprise qui loue auprès d’un compte individuel." },
      { title: "Entreprise → Entreprise", body: "Une location entre comptes d’entreprise." }
    ],
    howEyebrow: "Comment fonctionne SEVOR",
    howTitle: "Choisissez le parcours qui correspond à votre prochaine étape.",
    howLead: "Ces deux vues reflètent le flux actuel de mise en ligne et de réservation, sans modifier le fonctionnement de la plateforme.",
    rentTab: "Je veux louer",
    listTab: "Je veux proposer",
    rentSteps: [
      { title: "Explorer", body: "Recherchez et filtrez les annonces disponibles." },
      { title: "Examiner", body: "Lisez les détails, le prix, le lieu et les évaluations." },
      { title: "Demander", body: "Choisissez des dates et envoyez une demande de réservation." },
      { title: "Réaliser la location", body: "Après la décision du propriétaire, suivez les étapes actuelles de paiement, prise en charge, retour et avis lorsque nécessaire." }
    ],
    listSteps: [
      { title: "Préparer", body: "Utilisez un compte approuvé et choisissez un article adapté à proposer." },
      { title: "Créer", body: "Ajoutez photos, détails, emplacement, catégorie et prix quotidien." },
      { title: "Gérer les demandes", body: "Examinez les demandes de réservation et répondez dans le flux actuel." },
      { title: "Réaliser les locations", body: "Coordonnez les étapes de location, les preuves et les avis lorsqu’ils s’appliquent." }
    ],
    rentersEyebrow: "Pour les locataires",
    rentersTitle: "Trouvez l’accès temporaire adapté au moment présent.",
    rentersLead: "Parcourez les annonces actuelles, comparez ce qui est disponible, consultez les détails et poursuivez dans le parcours de réservation lorsqu’une annonce convient.",
    renterCards: [
      { title: "Découvrir", body: "Explorez les annonces avec la recherche et les filtres disponibles.", point1: "Comparez les détails des annonces.", point2: "Voyez les annonces de particuliers ou d’entreprises lorsqu’elles sont disponibles." },
      { title: "Réserver", body: "Sélectionnez des dates et demandez une réservation par la plateforme.", point1: "Un propriétaire peut accepter ou refuser une demande.", point2: "Certaines réservations acceptées peuvent inclure un montant de garantie." },
      { title: "Construire son expérience", body: "Utilisez les outils de réservation, messagerie, preuve et avis disponibles pour la location.", point1: "Suivez les étapes de prise en charge et de retour lorsqu’elles sont requises.", point2: "Laissez un avis lié à la réservation après les locations admissibles." }
    ],
    ownersEyebrow: "Pour les propriétaires",
    ownersTitle: "Rendez des articles adaptés disponibles lorsque vous ne les utilisez pas.",
    ownersLead: "Une location finalisée peut créer une possibilité de revenus locatifs pour un propriétaire. Elle ne constitue pas une promesse de revenus, de demande ni de résultat particulier.",
    ownerCards: [
      { title: "Créer une annonce claire", body: "Ajoutez les informations qui aident les locataires à comprendre un article adapté.", point1: "Photos et détails de l’article.", point2: "Catégorie, ville et prix quotidien." },
      { title: "Répondre aux demandes", body: "Examinez les demandes de réservation reçues et utilisez le flux de décision actuel.", point1: "Acceptez ou refusez une demande.", point2: "Fixez un dépôt lorsque le flux de réservation le permet." },
      { title: "Créer une opportunité", body: "Un actif adapté et inutilisé peut produire un revenu locatif lorsqu’une location est finalisée.", point1: "Gardez les préférences de versement du compte à jour.", point2: "Utilisez les outils de preuve et d’avis lorsque cela est pertinent." }
    ],
    businessEyebrow: "Pour les entreprises",
    businessTitle: "Les comptes d’entreprise peuvent participer à la même place de marché de location.",
    businessLead: "SEVOR reconnaît actuellement les types de comptes individuel et entreprise. Une entreprise peut utiliser le parcours existant de mise en ligne et de réservation pour des besoins ou offres de location adaptés ; cette page ne sous-entend pas l’existence d’outils distincts pour les entreprises.",
    businessQuote: "Une entreprise peut être propriétaire, locataire ou les deux, selon les annonces disponibles et ses besoins.",
    businessBody: "Des équipements ou actifs adaptés peuvent être proposés par des annonces. Une entreprise qui a besoin d’un accès temporaire peut également explorer la même place de marché. Le modèle de réservation est partagé plutôt qu’un parcours réservé aux entreprises.",
    businessPoint1: "L’inscription d’une entreprise comprend une étape de justificatif d’entreprise.",
    businessPoint2: "Explorer peut filtrer les annonces d’entreprises ou de particuliers.",
    categoriesEyebrow: "Que pouvez-vous louer ?",
    categoriesTitle: "Découvrez les catégories actuellement utilisées par SEVOR.",
    categoriesLead: "La place de marché peut afficher des annonces dans ces catégories générales ; la disponibilité réelle dépend des annonces actuelles.",
    categories: ["Véhicules", "Hébergement et séjours", "Électronique", "Mobilier", "Vêtements", "Outils et équipement", "Autre"],
    trustEyebrow: "Conçu autour d’outils de confiance pratiques",
    trustTitle: "Des outils qui soutiennent des décisions de location éclairées.",
    trustLead: "SEVOR comprend des mécanismes qui aident les utilisateurs à documenter, à communiquer au sujet des locations et à les gérer. Ils soutiennent le processus ; ils ne garantissent aucun résultat.",
    trustCards: [
      { title: "Vérification d’identité et d’entreprise", body: "La plateforme collecte des documents de vérification, dont une carte d’identité, un permis, un passeport et un justificatif d’entreprise, avec des voies d’examen." },
      { title: "Dossiers de réservation", body: "Les demandes, décisions et étapes liées à la location sont consignées dans le flux actuel." },
      { title: "Communication de location", body: "La messagerie liée à l’article aide les participants admissibles à communiquer au sujet d’une location." },
      { title: "Voies de preuve", body: "Des outils de preuve pour la prise en charge, le retour et le dépôt existent lorsque le flux de location les requiert." },
      { title: "Avis et évaluations", body: "Les retours liés à une réservation aident à comprendre des expériences passées sans garantir la qualité." },
      { title: "Assistance et signalements", body: "Des tickets d’assistance et des voies de signalement d’annonces sont disponibles via les outils existants." }
    ],
    paymentsQuote: "Les réservations en ligne acceptées utilisent le flux de paiement PayPal actuel.",
    paymentsBody: "Les propriétaires peuvent conserver leurs préférences de versement pour Interac, PayPal ou Wise dans les paramètres actuels de leur compte. Le processus actuel de versement est manuel ; cette page ne fait donc aucune promesse quant au délai, à la disponibilité ou au résultat d’un versement.",
    paymentsPoint1: "Un montant de garantie peut s’appliquer à certaines réservations.",
    paymentsPoint2: "Les preuves relatives au dépôt et les voies d’examen s’appliquent selon le cas.",
    visionEyebrow: "L’accès plutôt que la propriété",
    visionTitle: "Pensé dans une perspective flexible et mondiale de la location.",
    visionLead: "SEVOR est conçu pour rendre plus flexible la découverte de locations et l’accès pour les particuliers et les entreprises. Lorsqu’un article adapté existe déjà et est mis à disposition, la location temporaire peut, pour certains usages, être une solution de rechange à l’achat d’un article neuf.",
    visionCards: [
      { title: "Accéder à ce dont vous avez besoin", body: "Trouvez un accès temporaire lorsqu’une annonce répond à un besoin." },
      { title: "Utiliser davantage ce qui existe", body: "Des actifs adaptés peuvent devenir utiles lorsque leurs propriétaires les rendent disponibles." },
      { title: "Développer un choix utile", body: "Des annonces plus pertinentes peuvent créer davantage d’occasions de découvrir des locations." }
    ],
    whyEyebrow: "Pourquoi SEVOR ?",
    whyTitle: "Une boucle simple de place de marché.",
    whyLead: "Aucun compteur ni résultat garanti : seulement le lien pratique entre des annonces utiles et des possibilités de location.",
    flywheel: ["Davantage d’articles utiles sont mis en ligne", "Davantage de choix pour les locataires", "Davantage de locations finalisées peuvent créer davantage de possibilités pour les propriétaires"],
    finalEyebrow: "Votre prochaine location",
    finalTitle: "Prêt à louer autrement ?",
    finalLead: "Découvrez ce qui est disponible maintenant, ou rendez un article adapté disponible au moyen d’une annonce.",
    languageTitle: "Choisissez la langue de votre page À propos",
    languageLead: "Votre préférence est conservée pour cette page À propos lorsque vous revenez.",
    footerNote: "SEVOR est une place de marché : la disponibilité dépend des annonces actuelles.",
    privacyLink: "Centre de confidentialité",
    backTop: "Retour en haut"
  });

  const es = completeLocale({
    languageName: "Español", lang: "es", dir: "ltr",
    pageTitle: "Acerca de SEVOR | Alquila lo que necesitas",
    metaDescription: "Descubre SEVOR, un mercado de alquiler para encontrar acceso temporal a objetos útiles y poner artículos adecuados en alquiler.",
    homeAria: "Volver a la página de inicio de SEVOR", localNavAria: "Secciones Acerca de SEVOR", tabListAria: "Elegir un recorrido de SEVOR", languageGroupAria: "Elegir un idioma para Acerca de", flywheelAria: "Ciclo del mercado SEVOR", backTopAria: "Volver al inicio de esta página", languageSelected: "{language} seleccionado para esta página Acerca de.",
    homeLink: "Volver a SEVOR", kicker: "Un mercado de alquiler", heroTitle: "Alquila lo que necesitas. Obtén ingresos con lo que tienes.", heroLead: "SEVOR ayuda a personas y empresas a descubrir acceso temporal a objetos útiles y a poner artículos adecuados en alquiler.", exploreCta: "Explorar alquileres", listCta: "Publicar un artículo", registerCta: "Crear una cuenta",
    orbitRentTitle: "Encontrar acceso", orbitRentBody: "Para un día, proyecto, viaje u ocasión.", orbitListTitle: "Compartir disponibilidad", orbitListBody: "Poner un artículo adecuado a disposición.", orbitNote: "Un mercado para oportunidades de alquiler.",
    navOverview: "Resumen", navHow: "Cómo funciona", navRenters: "Para quienes alquilan", navOwners: "Para propietarios", navBusiness: "Para empresas", navTrust: "Confianza", navVision: "Visión",
    overviewEyebrow: "¿Qué es SEVOR?", overviewTitle: "Un mercado para el acceso temporal.", overviewLead: "SEVOR conecta a personas que buscan algo para usar durante un tiempo limitado con propietarios y proveedores que tienen artículos adecuados disponibles para alquilar.",
    overviewCards: [
      { title: "Quienes alquilan", body: "Personas u organizaciones que buscan acceso a un artículo durante un periodo definido." },
      { title: "Propietarios y proveedores", body: "Personas o empresas que ponen artículos adecuados a disposición mediante anuncios." },
      { title: "Oportunidades de alquiler", body: "Un lugar para descubrir, revisar, solicitar y completar alquileres cuando hay anuncios disponibles." }
    ],
    problemQuote: "¿Por qué comprar algo que quizá solo necesites durante poco tiempo?", problemBody: "Una herramienta, cámara, vehículo, dispositivo u otro artículo puede ser útil durante un día, una semana, un proyecto o una ocasión. La propiedad tiene sentido en algunas situaciones; en otras, puede valer la pena explorar el acceso temporal.", problemPoint1: "Descubre opciones de alquiler cuando estén disponibles.", problemPoint2: "Ayuda a que artículos adecuados sin uso sean útiles para otra persona.",
    compareEyebrow: "Una elección práctica", compareTitle: "Alquilar y comprar resuelven necesidades diferentes.", buyLabel: "COMPRAR", buyTitle: "Elegir la propiedad", buy: ["Pagar el precio total de compra.", "Conservar el artículo.", "Guardarlo y mantenerlo.", "Útil cuando la propiedad tiene sentido."], rentLabel: "ALQUILAR", rentTitle: "Elegir el acceso temporal", rent: ["Pagar por el acceso temporal acordado.", "Usar el artículo durante el periodo de alquiler.", "Devolverlo después.", "Útil cuando el acceso temporal tiene más sentido."],
    audienceEyebrow: "¿Para quién es SEVOR?", audienceTitle: "Hecho para personas y empresas que participan en alquileres.", audienceLead: "SEVOR admite tipos de cuenta individuales y de empresa. Los anuncios disponibles, y no una promesa sobre cada categoría, determinan lo que puede encontrar cada persona.",
    audienceCards: [
      { title: "Personas", body: "Personas que buscan acceso temporal a objetos útiles." },
      { title: "Quienes alquilan", body: "Usuarios que comparan anuncios, revisan detalles y hacen solicitudes de reserva." },
      { title: "Propietarios", body: "Personas que quieren poner artículos adecuados a disposición cuando no los usan." },
      { title: "Empresas", body: "Las cuentas de empresa pueden usar el mismo flujo de mercado para ofertas y necesidades de alquiler adecuadas." }
    ],
    relationshipsEyebrow: "Un mercado, varias relaciones", relationshipsTitle: "Alquila a personas o empresas cuando haya anuncios que coincidan.", relationshipsLead: "El modelo actual de cuentas y reservas no limita una reserva a una combinación de tipos de cuenta. Estas relaciones son posibles mediante el mismo flujo de alquiler.",
    relationships: [
      { title: "Persona → Persona", body: "Un alquiler entre cuentas individuales." },
      { title: "Empresa → Persona", body: "Una persona que alquila a una cuenta de empresa." },
      { title: "Persona → Empresa", body: "Una empresa que alquila a una cuenta individual." },
      { title: "Empresa → Empresa", body: "Un alquiler entre cuentas de empresa." }
    ],
    howEyebrow: "Cómo funciona SEVOR", howTitle: "Elige el recorrido que se ajuste a tu próximo paso.", howLead: "Estas dos vistas reflejan el flujo actual de anuncios y reservas sin cambiar el funcionamiento de la plataforma.", rentTab: "Quiero alquilar", listTab: "Quiero publicar",
    rentSteps: [
      { title: "Explorar", body: "Busca y filtra los anuncios disponibles." },
      { title: "Revisar", body: "Lee detalles, precio, ubicación y valoraciones." },
      { title: "Solicitar", body: "Elige fechas y envía una solicitud de reserva." },
      { title: "Completar el alquiler", body: "Tras la decisión del propietario, sigue los pasos actuales de pago, recogida, devolución y reseña cuando corresponda." }
    ],
    listSteps: [
      { title: "Preparar", body: "Usa una cuenta aprobada y elige un artículo adecuado para publicar." },
      { title: "Crear", body: "Añade fotos, detalles, ubicación, categoría y precio diario." },
      { title: "Gestionar solicitudes", body: "Revisa solicitudes de reserva y responde con el flujo actual." },
      { title: "Completar alquileres", body: "Coordina los pasos de alquiler, pruebas y comentarios cuando correspondan." }
    ],
    rentersEyebrow: "Para quienes alquilan", rentersTitle: "Encuentra el acceso temporal adecuado para este momento.", rentersLead: "Explora los anuncios actuales, compara lo disponible, revisa los detalles y sigue el flujo de reserva cuando un anuncio se ajuste a lo que buscas.",
    renterCards: [
      { title: "Descubrir", body: "Explora anuncios con la búsqueda y los filtros disponibles.", point1: "Compara los detalles de los anuncios.", point2: "Consulta anuncios de personas o empresas cuando estén disponibles." },
      { title: "Reservar", body: "Selecciona fechas y solicita una reserva a través de la plataforma.", point1: "Un propietario puede aceptar o rechazar una solicitud.", point2: "Algunas reservas aceptadas pueden incluir un importe de garantía." },
      { title: "Crear experiencia", body: "Usa las herramientas de reserva, mensajes, pruebas y reseñas disponibles para el alquiler.", point1: "Sigue los pasos de recogida y devolución cuando sean necesarios.", point2: "Deja comentarios vinculados a la reserva después de alquileres elegibles." }
    ],
    ownersEyebrow: "Para propietarios", ownersTitle: "Pon artículos adecuados a disposición cuando no los estés usando.", ownersLead: "Un alquiler completado puede crear una oportunidad de ingresos por alquiler para un propietario. No es una promesa de ingresos, demanda ni un resultado concreto.",
    ownerCards: [
      { title: "Crear un anuncio claro", body: "Añade información que ayude a quienes alquilan a comprender un artículo adecuado.", point1: "Fotos y detalles del artículo.", point2: "Categoría, ciudad y precio diario." },
      { title: "Responder solicitudes", body: "Revisa las solicitudes de reserva recibidas y usa el flujo de decisión actual.", point1: "Acepta o rechaza una solicitud.", point2: "Establece un depósito cuando el flujo de reserva lo permita." },
      { title: "Crear una oportunidad", body: "Un activo adecuado sin uso puede generar ingresos por alquiler cuando se completa un alquiler.", point1: "Mantén actualizadas las preferencias de cobro de la cuenta.", point2: "Usa herramientas de prueba y comentarios cuando sean pertinentes." }
    ],
    businessEyebrow: "Para empresas", businessTitle: "Las cuentas de empresa pueden participar en el mismo mercado de alquiler.", businessLead: "SEVOR reconoce actualmente los tipos de cuenta individual y de empresa. Una empresa puede usar el flujo existente de anuncios y reservas para necesidades u ofertas de alquiler adecuadas; esta página no implica herramientas empresariales independientes.", businessQuote: "Una empresa puede ser propietaria, arrendataria o ambas cosas, según los anuncios disponibles y sus necesidades.", businessBody: "El equipo o los activos adecuados pueden ponerse a disposición mediante anuncios. Una empresa que necesita acceso temporal también puede explorar el mismo mercado. El modelo de reserva es compartido, no un flujo exclusivo para empresas.", businessPoint1: "El registro de empresa incluye un paso de comprobación empresarial.", businessPoint2: "Explorar puede filtrar anuncios de empresas o de personas.",
    categoriesEyebrow: "¿Qué puedes alquilar?", categoriesTitle: "Explora las categorías que SEVOR utiliza hoy.", categoriesLead: "El mercado puede mostrar anuncios en estas categorías generales; la disponibilidad real depende de los anuncios actuales.", categories: ["Vehículos", "Alojamiento y estancias", "Electrónica", "Muebles", "Ropa", "Herramientas y equipo", "Otros"],
    trustEyebrow: "Creado con herramientas de confianza prácticas", trustTitle: "Herramientas que respaldan decisiones de alquiler informadas.", trustLead: "SEVOR incluye mecanismos que ayudan a los usuarios a documentar, comunicarse sobre y gestionar los alquileres. Respaldan el proceso; no garantizan ningún resultado.",
    trustCards: [
      { title: "Verificación de identidad y empresa", body: "La plataforma recopila documentos de verificación, incluidos documento de identidad, licencia de conducir, pasaporte y comprobante de empresa, con vías de revisión." },
      { title: "Registros de reserva", body: "Las solicitudes, decisiones y pasos relacionados con el alquiler se registran en el flujo actual." },
      { title: "Comunicación de alquiler", body: "La mensajería vinculada al artículo ayuda a participantes elegibles a comunicarse sobre un alquiler." },
      { title: "Vías de prueba", body: "Existen herramientas de prueba para recogida, devolución y depósito cuando el flujo de alquiler las requiere." },
      { title: "Reseñas y valoraciones", body: "Los comentarios vinculados a la reserva ayudan a conocer experiencias anteriores sin garantizar calidad." },
      { title: "Soporte y reportes", body: "Hay tickets de soporte y vías para reportar anuncios mediante las herramientas existentes." }
    ],
    paymentsQuote: "Las reservas en línea aceptadas utilizan el flujo de pago actual de PayPal.", paymentsBody: "Los propietarios pueden mantener sus preferencias de cobro para Interac, PayPal o Wise en la configuración actual de su cuenta. El flujo actual de pagos es manual, por lo que esta página no promete plazos, disponibilidad ni un resultado de pago.", paymentsPoint1: "Se puede aplicar un importe de garantía a algunas reservas.", paymentsPoint2: "Las pruebas relativas al depósito y las vías de revisión se aplican cuando corresponda.",
    visionEyebrow: "Acceso por encima de propiedad", visionTitle: "Creado con una visión flexible y global de los alquileres.", visionLead: "SEVOR está diseñado para hacer más flexible el descubrimiento de alquileres y el acceso para personas y empresas. Cuando ya existe un artículo adecuado y se pone a disposición, el alquiler temporal puede ser una alternativa a comprar algo nuevo para algunos usos.",
    visionCards: [
      { title: "Accede a lo que necesitas", body: "Encuentra acceso temporal cuando un anuncio coincida con una necesidad." },
      { title: "Usa más de lo que ya existe", body: "Los activos adecuados pueden ser útiles cuando sus propietarios los ponen a disposición." },
      { title: "Amplía las opciones útiles", body: "Más anuncios relevantes pueden crear más oportunidades de descubrir alquileres." }
    ],
    whyEyebrow: "¿Por qué SEVOR?", whyTitle: "Un ciclo sencillo de mercado.", whyLead: "Sin contadores ni resultados garantizados: solo la relación práctica entre anuncios útiles y oportunidades de alquiler.", flywheel: ["Se publican más artículos útiles", "Más opciones para quienes alquilan", "Más alquileres completados pueden crear más oportunidades para los propietarios"],
    finalEyebrow: "Tu próximo alquiler", finalTitle: "¿Listo para alquilar de otra manera?", finalLead: "Explora lo que está disponible ahora o pon un artículo adecuado a disposición mediante un anuncio.", languageTitle: "Elige el idioma de Acerca de", languageLead: "Tu preferencia se conserva para esta página cuando vuelvas.", footerNote: "SEVOR es un mercado: la disponibilidad depende de los anuncios actuales.", privacyLink: "Centro de privacidad", backTop: "Volver arriba"
  });

  const pt = completeLocale({
    languageName: "Português", lang: "pt", dir: "ltr",
    pageTitle: "Sobre a SEVOR | Alugue o que você precisa",
    metaDescription: "Conheça a SEVOR, um marketplace de aluguel para encontrar acesso temporário a itens úteis e disponibilizar artigos adequados para aluguel.",
    homeAria: "Voltar à página inicial da SEVOR", localNavAria: "Seções Sobre a SEVOR", tabListAria: "Escolher uma jornada SEVOR", languageGroupAria: "Escolher um idioma para a página Sobre", flywheelAria: "Ciclo do marketplace SEVOR", backTopAria: "Voltar ao início desta página", languageSelected: "{language} selecionado para esta página Sobre.",
    homeLink: "Voltar à SEVOR", kicker: "Um marketplace de aluguel", heroTitle: "Alugue o que você precisa. Ganhe com o que você possui.", heroLead: "SEVOR ajuda pessoas e empresas a descobrir acesso temporário a itens úteis e a disponibilizar itens adequados para aluguel.", exploreCta: "Explorar aluguéis", listCta: "Anunciar um item", registerCta: "Criar uma conta",
    orbitRentTitle: "Encontrar acesso", orbitRentBody: "Para um dia, projeto, viagem ou ocasião.", orbitListTitle: "Compartilhar disponibilidade", orbitListBody: "Disponibilize um item adequado.", orbitNote: "Um marketplace para oportunidades de aluguel.",
    navOverview: "Visão geral", navHow: "Como funciona", navRenters: "Para locatários", navOwners: "Para proprietários", navBusiness: "Para empresas", navTrust: "Confiança", navVision: "Visão",
    overviewEyebrow: "O que é a SEVOR?", overviewTitle: "Um marketplace para acesso temporário.", overviewLead: "SEVOR conecta locatários que procuram algo para usar por um período limitado a proprietários e fornecedores que têm itens adequados disponíveis para aluguel.",
    overviewCards: [
      { title: "Locatários", body: "Pessoas ou organizações que buscam acesso a um item por um período definido." },
      { title: "Proprietários e fornecedores", body: "Pessoas ou empresas que disponibilizam itens adequados por meio de anúncios." },
      { title: "Oportunidades de aluguel", body: "Um lugar para descobrir, analisar, solicitar e concluir aluguéis quando há anúncios disponíveis." }
    ],
    problemQuote: "Por que comprar algo de que você talvez precise apenas por pouco tempo?", problemBody: "Uma ferramenta, câmera, veículo, dispositivo ou outro item pode ser útil por um dia, uma semana, um projeto ou uma ocasião. Ter a propriedade faz sentido em algumas situações; em outras, vale explorar o acesso temporário.", problemPoint1: "Descubra opções de aluguel quando estiverem disponíveis.", problemPoint2: "Ajude itens adequados e sem uso a se tornarem úteis para outra pessoa.",
    compareEyebrow: "Uma escolha prática", compareTitle: "Alugar e comprar atendem a necessidades diferentes.", buyLabel: "COMPRAR", buyTitle: "Escolher a propriedade", buy: ["Pague o preço integral de compra.", "Fique com o item.", "Guarde-o e faça sua manutenção.", "Útil quando ter a propriedade faz sentido."], rentLabel: "ALUGAR", rentTitle: "Escolher o acesso temporário", rent: ["Pague pelo acesso temporário acordado.", "Use o item durante o período de aluguel.", "Devolva-o depois.", "Útil quando o acesso temporário faz mais sentido."],
    audienceEyebrow: "Para quem é a SEVOR?", audienceTitle: "Feito para pessoas e empresas que participam de aluguéis.", audienceLead: "SEVOR oferece suporte a tipos de conta individual e empresarial. Os anúncios disponíveis — e não uma promessa sobre cada categoria — determinam o que cada pessoa pode encontrar.",
    audienceCards: [
      { title: "Pessoas", body: "Pessoas que buscam acesso temporário a itens úteis." },
      { title: "Locatários", body: "Usuários que comparam anúncios, analisam detalhes e fazem solicitações de reserva." },
      { title: "Proprietários", body: "Pessoas que querem disponibilizar itens adequados quando não os estão usando." },
      { title: "Empresas", body: "Contas empresariais podem usar o mesmo fluxo do marketplace para ofertas e necessidades de aluguel adequadas." }
    ],
    relationshipsEyebrow: "Um marketplace, várias relações", relationshipsTitle: "Alugue de pessoas ou empresas quando houver anúncios correspondentes.", relationshipsLead: "O modelo atual de conta e reserva não limita uma reserva a uma combinação de tipos de conta. Essas relações são possíveis pelo mesmo fluxo de aluguel.",
    relationships: [
      { title: "Pessoa → Pessoa", body: "Um aluguel entre contas individuais." },
      { title: "Empresa → Pessoa", body: "Uma pessoa alugando de uma conta empresarial." },
      { title: "Pessoa → Empresa", body: "Uma empresa alugando de uma conta individual." },
      { title: "Empresa → Empresa", body: "Um aluguel entre contas empresariais." }
    ],
    howEyebrow: "Como a SEVOR funciona", howTitle: "Escolha a jornada que se encaixa em sua próxima etapa.", howLead: "Estas duas visões refletem o fluxo atual de anúncios e reservas sem mudar o funcionamento da plataforma.", rentTab: "Quero alugar", listTab: "Quero anunciar",
    rentSteps: [
      { title: "Explorar", body: "Pesquise e filtre anúncios disponíveis." },
      { title: "Analisar", body: "Leia detalhes, preço, localização e avaliações." },
      { title: "Solicitar", body: "Escolha datas e envie uma solicitação de reserva." },
      { title: "Concluir o aluguel", body: "Após a decisão do proprietário, siga as etapas atuais de pagamento, retirada, devolução e avaliação quando aplicáveis." }
    ],
    listSteps: [
      { title: "Preparar", body: "Use uma conta aprovada e escolha um item adequado para anunciar." },
      { title: "Criar", body: "Adicione fotos, detalhes, localização, categoria e preço diário." },
      { title: "Gerenciar solicitações", body: "Analise pedidos de reserva e responda pelo fluxo atual." },
      { title: "Concluir aluguéis", body: "Coordene as etapas do aluguel, evidências e feedback quando se aplicarem." }
    ],
    rentersEyebrow: "Para locatários", rentersTitle: "Encontre o acesso temporário certo para o momento.", rentersLead: "Navegue pelos anúncios atuais, compare o que está disponível, analise os detalhes e siga o fluxo de reserva quando um anúncio atender à sua necessidade.",
    renterCards: [
      { title: "Descobrir", body: "Explore anúncios com a busca e os filtros disponíveis.", point1: "Compare os detalhes dos anúncios.", point2: "Veja anúncios de pessoas ou empresas quando disponíveis." },
      { title: "Reservar", body: "Selecione datas e solicite uma reserva pela plataforma.", point1: "Um proprietário pode aceitar ou recusar uma solicitação.", point2: "Algumas reservas aceitas podem incluir um valor de garantia." },
      { title: "Construir experiência", body: "Use as ferramentas de reserva, mensagens, evidências e avaliações disponíveis para o aluguel.", point1: "Siga as etapas de retirada e devolução quando exigidas.", point2: "Deixe feedback vinculado à reserva após aluguéis elegíveis." }
    ],
    ownersEyebrow: "Para proprietários", ownersTitle: "Disponibilize itens adequados quando não estiver usando-os.", ownersLead: "Um aluguel concluído pode criar uma oportunidade de renda de aluguel para um proprietário. Isso não é uma promessa de renda, demanda nem de resultado específico.",
    ownerCards: [
      { title: "Criar um anúncio claro", body: "Adicione informações que ajudem locatários a entender um item adequado.", point1: "Fotos e detalhes do item.", point2: "Categoria, cidade e preço diário." },
      { title: "Responder às solicitações", body: "Analise pedidos de reserva recebidos e use o fluxo atual de decisão.", point1: "Aceite ou recuse uma solicitação.", point2: "Defina uma caução quando o fluxo de reserva permitir." },
      { title: "Criar uma oportunidade", body: "Um ativo adequado e sem uso pode gerar renda de aluguel quando um aluguel é concluído.", point1: "Mantenha atualizadas as preferências de repasse da conta.", point2: "Use ferramentas de evidência e feedback quando relevantes." }
    ],
    businessEyebrow: "Para empresas", businessTitle: "Contas empresariais podem participar do mesmo marketplace de aluguel.", businessLead: "SEVOR atualmente reconhece os tipos de conta individual e empresarial. Uma empresa pode usar o fluxo existente de anúncios e reservas para necessidades ou ofertas de aluguel adequadas; esta página não implica ferramentas empresariais separadas.", businessQuote: "Uma empresa pode ser proprietária, locatária ou ambas, dependendo dos anúncios disponíveis e de suas necessidades.", businessBody: "Equipamentos ou ativos adequados podem ser disponibilizados por meio de anúncios. Uma empresa que precisa de acesso temporário também pode explorar o mesmo marketplace. O modelo de reserva é compartilhado, e não um fluxo exclusivo para empresas.", businessPoint1: "O cadastro de empresa inclui uma etapa de comprovação empresarial.", businessPoint2: "Explorar pode filtrar anúncios de empresas ou pessoas físicas.",
    categoriesEyebrow: "O que você pode alugar?", categoriesTitle: "Explore as categorias usadas atualmente pela SEVOR.", categoriesLead: "O marketplace pode mostrar anúncios nestas categorias gerais; a disponibilidade real depende dos anúncios atuais.", categories: ["Veículos", "Hospedagem e estadias", "Eletrônicos", "Móveis", "Vestuário", "Ferramentas e equipamentos", "Outros"],
    trustEyebrow: "Construído com ferramentas práticas de confiança", trustTitle: "Ferramentas que apoiam decisões de aluguel bem informadas.", trustLead: "SEVOR inclui mecanismos que ajudam os usuários a documentar, comunicar-se sobre e gerenciar aluguéis. Eles apoiam o processo; não são garantia de nenhum resultado.",
    trustCards: [
      { title: "Verificação de identidade e empresa", body: "A plataforma coleta documentos de verificação, incluindo identidade, carteira de motorista, passaporte e comprovante empresarial, com caminhos de análise." },
      { title: "Registros de reserva", body: "Solicitações, decisões e etapas relacionadas ao aluguel são registradas no fluxo atual." },
      { title: "Comunicação de aluguel", body: "Mensagens vinculadas ao item ajudam participantes elegíveis a comunicar-se sobre um aluguel." },
      { title: "Caminhos de evidência", body: "Há ferramentas de evidência para retirada, devolução e caução quando o fluxo de aluguel as exige." },
      { title: "Avaliações e classificações", body: "Feedback vinculado à reserva ajuda usuários a conhecer experiências anteriores sem garantir qualidade." },
      { title: "Suporte e denúncias", body: "Chamados de suporte e caminhos para denunciar anúncios estão disponíveis nas ferramentas existentes." }
    ],
    paymentsQuote: "Reservas on-line aceitas usam o fluxo de pagamento PayPal atual.", paymentsBody: "Os proprietários podem manter suas preferências de repasse para Interac, PayPal ou Wise nas configurações atuais da conta. O fluxo atual de repasses é manual, portanto esta página não promete prazo, disponibilidade ou resultado de um repasse.", paymentsPoint1: "Um valor de garantia pode se aplicar a algumas reservas.", paymentsPoint2: "Evidências de caução e caminhos de análise se aplicam quando relevantes.",
    visionEyebrow: "Acesso acima da propriedade", visionTitle: "Construído com uma visão flexível e global para aluguéis.", visionLead: "SEVOR foi projetado para tornar mais flexíveis a descoberta de aluguéis e o acesso para pessoas e empresas. Quando um item adequado já existe e é disponibilizado, o aluguel temporário pode ser uma alternativa à compra de algo novo para alguns usos.",
    visionCards: [
      { title: "Acesse o que você precisa", body: "Encontre acesso temporário quando um anúncio atender a uma necessidade." },
      { title: "Use mais do que já existe", body: "Ativos adequados podem tornar-se úteis quando seus proprietários os disponibilizam." },
      { title: "Amplie opções úteis", body: "Mais anúncios relevantes podem criar mais oportunidades para descobrir aluguéis." }
    ],
    whyEyebrow: "Por que a SEVOR?", whyTitle: "Um ciclo simples de marketplace.", whyLead: "Sem contadores nem resultados garantidos — apenas a relação prática entre anúncios úteis e oportunidades de aluguel.", flywheel: ["Mais itens úteis são anunciados", "Mais opções para locatários", "Mais aluguéis concluídos podem criar mais oportunidades para proprietários"],
    finalEyebrow: "Seu próximo aluguel", finalTitle: "Pronto para alugar de outra forma?", finalLead: "Explore o que está disponível agora ou disponibilize um item adequado por meio de um anúncio.", languageTitle: "Escolha o idioma da página Sobre", languageLead: "Sua preferência é guardada para esta página quando você voltar.", footerNote: "SEVOR é um marketplace: a disponibilidade depende dos anúncios atuais.", privacyLink: "Central de privacidade", backTop: "Voltar ao topo"
  });

  const ar = completeLocale({
    languageName: "العربية", lang: "ar", dir: "rtl",
    pageTitle: "حول SEVOR | استأجر ما تحتاج إليه", metaDescription: "تعرّف على SEVOR، سوق للإيجار يساعد على العثور على وصول مؤقت إلى أشياء مفيدة وإتاحة عناصر مناسبة للإيجار.",
    homeAria: "العودة إلى الصفحة الرئيسية لـ SEVOR", localNavAria: "أقسام حول SEVOR", tabListAria: "اختر مسار SEVOR", languageGroupAria: "اختر لغة صفحة حول SEVOR", flywheelAria: "حلقة سوق SEVOR", backTopAria: "العودة إلى أعلى الصفحة", languageSelected: "تم اختيار {language} لهذه الصفحة.",
    homeLink: "العودة إلى SEVOR", kicker: "سوق للإيجار", heroTitle: "استأجر ما تحتاج إليه. واكسب مما تملكه.", heroLead: "تساعد SEVOR الأفراد والشركات على العثور على إمكانية وصول مؤقت إلى أشياء مفيدة، وإتاحة العناصر المناسبة للإيجار.", exploreCta: "استكشف الإيجارات", listCta: "أضف عنصرًا للإيجار", registerCta: "أنشئ حسابًا",
    orbitRentTitle: "اعثر على إمكانية الوصول", orbitRentBody: "ليوم أو لمشروع أو لرحلة أو لمناسبة.", orbitListTitle: "شارك ما هو متاح", orbitListBody: "أتِح عنصرًا مناسبًا.", orbitNote: "سوق واحد لفرص الإيجار.",
    navOverview: "نظرة عامة", navHow: "كيف يعمل", navRenters: "للمستأجرين", navOwners: "للمالكين", navBusiness: "للشركات", navTrust: "الثقة", navVision: "الرؤية",
    overviewEyebrow: "ما هي SEVOR؟", overviewTitle: "سوق للوصول المؤقت.", overviewLead: "تربط SEVOR المستأجرين الذين يبحثون عن شيء لاستخدامه لفترة محدودة بالمالكين والجهات التي تتيح عناصر مناسبة للإيجار.",
    overviewCards: [
      { title: "المستأجرون", body: "أفراد أو جهات تبحث عن الوصول إلى عنصر لفترة محددة." },
      { title: "المالكون والجهات المقدمة", body: "أفراد أو شركات تتيح عناصر مناسبة عبر الإعلانات." },
      { title: "فرص الإيجار", body: "مكان لاكتشاف الإيجارات ومراجعتها وطلبها وإتمامها عند توفر الإعلانات." }
    ],
    problemQuote: "لماذا تشتري شيئًا قد تحتاج إليه لفترة قصيرة فقط؟", problemBody: "قد تكون أداة أو كاميرا أو مركبة أو جهازًا أو عنصرًا آخر مفيدًا ليوم أو أسبوع أو مشروع أو مناسبة. قد تكون الملكية منطقية في بعض الحالات؛ وفي حالات أخرى قد يكون من المفيد استكشاف الوصول المؤقت.", problemPoint1: "اكتشف خيارات الإيجار عند توفرها.", problemPoint2: "ساعد العناصر المناسبة غير المستخدمة على أن تصبح مفيدة لشخص آخر.",
    compareEyebrow: "خيار عملي", compareTitle: "يلبّي الإيجار والشراء احتياجات مختلفة.", buyLabel: "شراء", buyTitle: "اختر التملك", buy: ["ادفع سعر الشراء الكامل.", "احتفظ بالعنصر.", "خزّنه وحافظ عليه.", "مفيد عندما يكون التملك هو الأنسب."], rentLabel: "إيجار", rentTitle: "اختر الوصول المؤقت", rent: ["ادفع مقابل الوصول المؤقت المتفق عليه.", "استخدم العنصر خلال فترة الإيجار.", "أعده بعد ذلك.", "مفيد عندما يكون الوصول المؤقت هو الأنسب."],
    audienceEyebrow: "لمن صُممت SEVOR؟", audienceTitle: "مصممة للأفراد والشركات المشاركين في الإيجارات.", audienceLead: "يدعم SEVOR نوعَي حسابات الأفراد والشركات. وتحدد الإعلانات المتاحة، لا الوعد بتوفر كل فئة، ما يمكن لكل شخص العثور عليه.",
    audienceCards: [
      { title: "الأفراد", body: "أشخاص يبحثون عن وصول مؤقت إلى أشياء مفيدة." },
      { title: "المستأجرون", body: "مستخدمون يقارنون الإعلانات ويراجعون التفاصيل ويرسلون طلبات الحجز." },
      { title: "المالكون", body: "أشخاص يريدون إتاحة عناصر مناسبة عندما لا يستخدمونها." },
      { title: "الشركات", body: "يمكن لحسابات الشركات استخدام مسار السوق نفسه لعروض واحتياجات الإيجار المناسبة." }
    ],
    relationshipsEyebrow: "سوق واحد، وعلاقات متعددة", relationshipsTitle: "استأجر من أفراد أو شركات عند توفر إعلانات مناسبة.", relationshipsLead: "لا يقصر نموذج الحساب والحجز الحالي الحجز على اقتران واحد بين أنواع الحسابات. وهذه العلاقات ممكنة عبر مسار الإيجار نفسه.",
    relationships: [
      { title: "فرد ← فرد", body: "إيجار بين حسابين فرديين." },
      { title: "شركة ← فرد", body: "فرد يستأجر من حساب شركة." },
      { title: "فرد ← شركة", body: "شركة تستأجر من حساب فردي." },
      { title: "شركة ← شركة", body: "إيجار بين حسابين لشركتين." }
    ],
    howEyebrow: "كيف يعمل SEVOR", howTitle: "اختر المسار الذي يناسب خطوتك التالية.", howLead: "يعكس هذان المنظوران مسار الإدراج والحجز الحالي من دون تغيير طريقة عمل المنصة.", rentTab: "أريد الاستئجار", listTab: "أريد الإدراج",
    rentSteps: [
      { title: "استكشف", body: "ابحث في الإعلانات المتاحة وصفِّها." },
      { title: "راجع", body: "اقرأ تفاصيل الإعلان والسعر والموقع والتقييمات." },
      { title: "اطلب", body: "اختر التواريخ وأرسل طلب حجز." },
      { title: "أكمل الإيجار", body: "بعد قرار المالك، اتبع خطوات الدفع والاستلام والإرجاع والمراجعة الحالية حيثما تنطبق." }
    ],
    listSteps: [
      { title: "استعد", body: "استخدم حسابًا معتمدًا واختر عنصرًا مناسبًا لإدراجه." },
      { title: "أنشئ", body: "أضف الصور والتفاصيل والموقع والفئة والسعر اليومي." },
      { title: "أدر الطلبات", body: "راجع طلبات الحجز ورد عليها عبر المسار الحالي." },
      { title: "أكمل الإيجارات", body: "نسّق خطوات الإيجار والأدلة والملاحظات حيثما تنطبق." }
    ],
    rentersEyebrow: "للمستأجرين", rentersTitle: "اعثر على الوصول المؤقت المناسب للحظة.", rentersLead: "تصفّح الإعلانات الحالية، وقارن ما هو متاح، وراجع التفاصيل، ثم تابع عبر مسار الحجز عندما يناسبك إعلان.",
    renterCards: [
      { title: "اكتشف", body: "استكشف الإعلانات باستخدام البحث والفلاتر المتاحة.", point1: "قارن تفاصيل الإعلانات.", point2: "اطّلع على إعلانات الأفراد أو الشركات عند توفرها." },
      { title: "احجز", body: "اختر التواريخ واطلب حجزًا عبر المنصة.", point1: "يمكن للمالك قبول الطلب أو رفضه.", point2: "قد تتضمن بعض الحجوزات المقبولة مبلغ تأمين." },
      { title: "ابنِ تجربتك", body: "استخدم أدوات الحجز والرسائل والأدلة والتقييم المتاحة للإيجار.", point1: "اتبع خطوات الاستلام والإرجاع عند طلبها.", point2: "اترك ملاحظات مرتبطة بالحجز بعد الإيجارات المؤهلة." }
    ],
    ownersEyebrow: "للمالكين", ownersTitle: "أتِح عناصر مناسبة عندما لا تستخدمها.", ownersLead: "قد يخلق الإيجار المكتمل فرصة دخل من الإيجار للمالك. وليس ذلك وعدًا بالدخل أو الطلب أو نتيجة محددة.",
    ownerCards: [
      { title: "أنشئ إعلانًا واضحًا", body: "أضف معلومات تساعد المستأجرين على فهم العنصر المناسب.", point1: "صور وتفاصيل العنصر.", point2: "الفئة والمدينة والسعر اليومي." },
      { title: "رد على الطلبات", body: "راجع طلبات الحجز الواردة واستخدم مسار القرار الحالي.", point1: "اقبل الطلب أو ارفضه.", point2: "حدد وديعة عندما يسمح مسار الحجز بذلك." },
      { title: "أنشئ فرصة", body: "قد يحقق أصل مناسب غير مستخدم دخلاً من الإيجار عندما يكتمل الإيجار.", point1: "حافظ على تفضيلات تلقي الدفعات في الحساب.", point2: "استخدم أدوات الأدلة والملاحظات عند الحاجة." }
    ],
    businessEyebrow: "للشركات", businessTitle: "يمكن لحسابات الشركات المشاركة في سوق الإيجار نفسه.", businessLead: "يدعم SEVOR حاليًا نوعَي حسابات الأفراد والشركات. ويمكن للشركة استخدام مسار الإدراج والحجز القائم لاحتياجات أو عروض الإيجار المناسبة؛ ولا تعني هذه الصفحة وجود أدوات منفصلة للمؤسسات.", businessQuote: "يمكن أن تكون الشركة مالكًا أو مستأجرًا أو كليهما، بحسب الإعلانات المتاحة واحتياجاتها.", businessBody: "يمكن إتاحة المعدات أو الأصول المناسبة عبر الإعلانات. ويمكن للشركة التي تحتاج وصولًا مؤقتًا استكشاف السوق نفسه أيضًا. نموذج الحجز مشترك وليس مسارًا منفصلًا للشركات فقط.", businessPoint1: "يتضمن تسجيل الشركة خطوة لإثبات الشركة.", businessPoint2: "يمكن لتصفّح الإعلانات تصفية إعلانات الشركات أو الأفراد.",
    categoriesEyebrow: "ما الذي يمكنك استئجاره؟", categoriesTitle: "استكشف الفئات التي يستخدمها SEVOR اليوم.", categoriesLead: "يمكن للسوق عرض إعلانات ضمن هذه الفئات العامة؛ ويعتمد التوفر الفعلي على الإعلانات الحالية.", categories: ["المركبات", "السكن والإقامات", "الإلكترونيات", "الأثاث", "الملابس", "الأدوات والمعدات", "أخرى"],
    trustEyebrow: "مصمم حول أدوات ثقة عملية", trustTitle: "أدوات تدعم قرارات إيجار مدروسة.", trustLead: "تتضمن SEVOR آليات تساعد المستخدمين على توثيق الإيجارات والتواصل بشأنها وإدارتها. وهي تدعم العملية؛ لكنها ليست ضمانًا لأي نتيجة.",
    trustCards: [
      { title: "التحقق من الهوية والشركة", body: "تجمع المنصة مستندات التحقق، بما فيها بطاقة الهوية ورخصة القيادة وجواز السفر وإثبات الشركة، مع مسارات للمراجعة." },
      { title: "سجلات الحجز", body: "تُسجل طلبات الحجز والقرارات والخطوات المتعلقة بالإيجار ضمن المسار الحالي." },
      { title: "التواصل بشأن الإيجار", body: "تساعد الرسائل المرتبطة بالعنصر المشاركين المؤهلين على التواصل بشأن الإيجار." },
      { title: "مسارات الأدلة", body: "توجد أدوات أدلة للاستلام والإرجاع والوديعة عندما يتطلبها مسار الإيجار." },
      { title: "المراجعات والتقييمات", body: "تساعد الملاحظات المرتبطة بالحجز المستخدمين على فهم التجارب السابقة دون ضمان الجودة." },
      { title: "الدعم والتقارير", body: "تتوفر تذاكر الدعم ومسارات الإبلاغ عن الإعلانات عبر أدوات المنصة الحالية." }
    ],
    paymentsQuote: "تستخدم الحجوزات الإلكترونية المقبولة مسار الدفع الحالي عبر PayPal.", paymentsBody: "يمكن للمالكين الاحتفاظ بتفضيلات تلقي الدفعات عبر Interac أو PayPal أو Wise في إعدادات الحساب الحالية. ومسار الدفعات الحالي يدوي، لذا لا تعد هذه الصفحة بتوقيت أو توفر أو نتيجة للدفعة.", paymentsPoint1: "قد ينطبق مبلغ تأمين على بعض الحجوزات.", paymentsPoint2: "تنطبق أدلة الوديعة ومسارات المراجعة حيثما كان ذلك مناسبًا.",
    visionEyebrow: "الوصول بدل التملك", visionTitle: "بُني برؤية عالمية مرنة للإيجارات.", visionLead: "صُممت SEVOR لجعل اكتشاف الإيجارات والوصول إليها أكثر مرونة للأفراد والشركات. وعندما يكون عنصر مناسب موجودًا ومتاحًا، قد يكون الإيجار المؤقت بديلًا لشراء شيء جديد لبعض الاستخدامات.",
    visionCards: [
      { title: "احصل على ما تحتاج إليه", body: "اعثر على وصول مؤقت عندما يلبي إعلان حاجة." },
      { title: "استخدم أكثر مما هو موجود", body: "يمكن للأصول المناسبة أن تصبح مفيدة عندما يتيحها مالكوها." },
      { title: "نمِّ الخيارات المفيدة", body: "قد تخلق الإعلانات الأكثر صلة فرصًا أكثر لاكتشاف الإيجارات." }
    ],
    whyEyebrow: "لماذا SEVOR؟", whyTitle: "حلقة سوق بسيطة.", whyLead: "لا عدّادات ولا نتائج مضمونة؛ فقط العلاقة العملية بين الإعلانات المفيدة وفرص الإيجار.", flywheel: ["تُدرج عناصر مفيدة أكثر", "خيارات أكثر للمستأجرين", "قد تخلق عمليات الإيجار المكتملة أكثر فرصًا للمالكين"],
    finalEyebrow: "إيجارك القادم", finalTitle: "هل أنت مستعد لتجربة الإيجار بطريقة مختلفة؟", finalLead: "استكشف ما هو متاح الآن، أو اجعل عنصرًا مناسبًا متاحًا عبر إعلان.", languageTitle: "اختر لغة صفحة حول SEVOR", languageLead: "يُحفَظ تفضيلك لهذه الصفحة عند عودتك.", footerNote: "SEVOR سوق: يعتمد التوفر على الإعلانات الحالية.", privacyLink: "مركز الخصوصية", backTop: "العودة إلى الأعلى"
  });

  const hi = completeLocale({
    languageName: "हिन्दी", lang: "hi", dir: "ltr",
    pageTitle: "SEVOR के बारे में | जिसकी ज़रूरत हो, उसे किराये पर लें", metaDescription: "SEVOR को जानें, उपयोगी वस्तुओं तक अस्थायी पहुँच खोजने और उपयुक्त वस्तुओं को किराये के लिए उपलब्ध कराने वाला किराये का बाज़ार।",
    homeAria: "SEVOR मुखपृष्ठ पर लौटें", localNavAria: "SEVOR के बारे में अनुभाग", tabListAria: "SEVOR यात्रा चुनें", languageGroupAria: "About पेज की भाषा चुनें", flywheelAria: "SEVOR बाज़ार चक्र", backTopAria: "इस पेज के शीर्ष पर लौटें", languageSelected: "इस About पेज के लिए {language} चुनी गई है।",
    homeLink: "SEVOR पर वापस जाएँ", kicker: "किराये का बाज़ार", heroTitle: "जिसकी ज़रूरत हो, उसे किराये पर लें। जो आपका है, उससे कमाएँ।", heroLead: "SEVOR लोगों और कंपनियों को उपयोगी वस्तुओं तक अस्थायी पहुँच के विकल्प खोजने और उपयुक्त वस्तुओं को किराये के लिए उपलब्ध कराने में मदद करता है।", exploreCta: "किराये देखें", listCta: "एक वस्तु सूचीबद्ध करें", registerCta: "खाता बनाएँ",
    orbitRentTitle: "अस्थायी पहुँच पाएँ", orbitRentBody: "एक दिन, प्रोजेक्ट, यात्रा या अवसर के लिए।", orbitListTitle: "उपलब्ध कराएँ", orbitListBody: "एक उपयुक्त वस्तु उपलब्ध कराएँ।", orbitNote: "किराये के अवसरों के लिए एक बाज़ार।",
    navOverview: "अवलोकन", navHow: "कैसे काम करता है", navRenters: "किरायेदारों के लिए", navOwners: "मालिकों के लिए", navBusiness: "कंपनियों के लिए", navTrust: "विश्वास", navVision: "दृष्टि",
    overviewEyebrow: "SEVOR क्या है?", overviewTitle: "अस्थायी पहुँच के लिए एक बाज़ार।", overviewLead: "SEVOR सीमित अवधि के लिए किसी वस्तु का उपयोग चाहने वाले किरायेदारों को उन मालिकों और प्रदाताओं से जोड़ता है जिनके पास किराये के लिए उपयुक्त वस्तुएँ उपलब्ध हैं।",
    overviewCards: [
      { title: "किरायेदार", body: "लोग या संगठन जो निश्चित अवधि के लिए किसी वस्तु तक पहुँच चाहते हैं।" },
      { title: "मालिक और प्रदाता", body: "व्यक्ति या कंपनियाँ जो लिस्टिंग के माध्यम से उपयुक्त वस्तुएँ उपलब्ध कराती हैं।" },
      { title: "किराये के अवसर", body: "लिस्टिंग उपलब्ध होने पर किराये खोजने, देखने, अनुरोध करने और पूरा करने का स्थान।" }
    ],
    problemQuote: "ऐसी चीज़ क्यों खरीदें जिसकी ज़रूरत शायद केवल थोड़े समय के लिए हो?", problemBody: "कोई उपकरण, कैमरा, वाहन, डिवाइस या अन्य वस्तु एक दिन, एक सप्ताह, किसी प्रोजेक्ट या अवसर के लिए उपयोगी हो सकती है। कुछ स्थितियों में स्वामित्व उचित हो सकता है; अन्य में अस्थायी पहुँच पर विचार करना उपयोगी हो सकता है।", problemPoint1: "उपलब्ध होने पर किराये के विकल्प खोजें।", problemPoint2: "उपयुक्त, अनुपयोगी वस्तुओं को किसी और के लिए उपयोगी बनने में मदद करें।",
    compareEyebrow: "व्यावहारिक विकल्प", compareTitle: "किराये पर लेना और खरीदना अलग ज़रूरतों को पूरा करते हैं।", buyLabel: "खरीदें", buyTitle: "स्वामित्व चुनें", buy: ["पूरा खरीद मूल्य चुकाएँ।", "वस्तु अपने पास रखें।", "उसे रखें और उसकी देखभाल करें।", "उपयोगी जब स्वामित्व उचित हो।"], rentLabel: "किराया", rentTitle: "अस्थायी पहुँच चुनें", rent: ["सहमति वाली अस्थायी पहुँच के लिए भुगतान करें।", "किराये की अवधि में वस्तु का उपयोग करें।", "बाद में उसे लौटाएँ।", "उपयोगी जब अस्थायी पहुँच उचित हो।"],
    audienceEyebrow: "SEVOR किसके लिए है?", audienceTitle: "किराये में भाग लेने वाले लोगों और कंपनियों के लिए बनाया गया है।", audienceLead: "SEVOR व्यक्तिगत और कंपनी खाता प्रकारों का समर्थन करता है। उपलब्ध लिस्टिंग—न कि हर श्रेणी के बारे में कोई वादा—तय करती हैं कि प्रत्येक व्यक्ति को क्या मिल सकता है।",
    audienceCards: [
      { title: "व्यक्ति", body: "उपयोगी वस्तुओं तक अस्थायी पहुँच खोजने वाले लोग।" },
      { title: "किरायेदार", body: "उपयोगकर्ता जो लिस्टिंग की तुलना करते हैं, विवरण देखते हैं और बुकिंग अनुरोध करते हैं।" },
      { title: "मालिक", body: "लोग जो उपयुक्त वस्तुओं को तब उपलब्ध कराना चाहते हैं जब वे उनका उपयोग नहीं कर रहे हों।" },
      { title: "कंपनियाँ", body: "कंपनी खाते उपयुक्त किराये की पेशकशों और ज़रूरतों के लिए उसी बाज़ार प्रक्रिया का उपयोग कर सकते हैं।" }
    ],
    relationshipsEyebrow: "एक बाज़ार, कई संबंध", relationshipsTitle: "मेल खाती लिस्टिंग उपलब्ध होने पर लोगों या कंपनियों से किराये पर लें।", relationshipsLead: "मौजूदा खाता और बुकिंग मॉडल बुकिंग को केवल एक खाता-प्रकार की जोड़ी तक सीमित नहीं करता। ये संबंध उसी किराये की प्रक्रिया से संभव हैं।",
    relationships: [
      { title: "व्यक्ति → व्यक्ति", body: "व्यक्तिगत खातों के बीच किराया।" },
      { title: "कंपनी → व्यक्ति", body: "कंपनी खाते से किराये पर लेने वाला व्यक्ति।" },
      { title: "व्यक्ति → कंपनी", body: "व्यक्तिगत खाते से किराये पर लेने वाली कंपनी।" },
      { title: "कंपनी → कंपनी", body: "कंपनी खातों के बीच किराया।" }
    ],
    howEyebrow: "SEVOR कैसे काम करता है", howTitle: "ऐसा मार्ग चुनें जो आपके अगले कदम के अनुकूल हो।", howLead: "ये दो दृश्य प्लेटफ़ॉर्म के काम करने के तरीके को बदले बिना वर्तमान लिस्टिंग और बुकिंग प्रक्रिया दिखाते हैं।", rentTab: "मैं किराये पर लेना चाहता/चाहती हूँ", listTab: "मैं सूचीबद्ध करना चाहता/चाहती हूँ",
    rentSteps: [
      { title: "खोजें", body: "उपलब्ध लिस्टिंग खोजें और फ़िल्टर करें।" },
      { title: "देखें", body: "लिस्टिंग विवरण, मूल्य, स्थान और रेटिंग पढ़ें।" },
      { title: "अनुरोध करें", body: "तारीखें चुनें और बुकिंग अनुरोध भेजें।" },
      { title: "किराया पूरा करें", body: "मालिक के निर्णय के बाद, जहाँ लागू हो वर्तमान भुगतान, पिकअप, वापसी और समीक्षा चरणों का पालन करें।" }
    ],
    listSteps: [
      { title: "तैयार करें", body: "स्वीकृत खाते का उपयोग करें और सूचीबद्ध करने के लिए उपयुक्त वस्तु चुनें।" },
      { title: "बनाएँ", body: "फ़ोटो, विवरण, स्थान, श्रेणी और दैनिक मूल्य जोड़ें।" },
      { title: "अनुरोध प्रबंधित करें", body: "बुकिंग अनुरोध देखें और मौजूदा प्रक्रिया से उत्तर दें।" },
      { title: "किराये पूरे करें", body: "जहाँ लागू हो किराये के चरण, साक्ष्य और फीडबैक समन्वित करें।" }
    ],
    rentersEyebrow: "किरायेदारों के लिए", rentersTitle: "इस समय के लिए सही अस्थायी पहुँच खोजें।", rentersLead: "मौजूदा लिस्टिंग ब्राउज़ करें, उपलब्ध विकल्पों की तुलना करें, विवरण देखें और कोई लिस्टिंग उपयुक्त लगे तो बुकिंग प्रक्रिया जारी रखें।",
    renterCards: [
      { title: "खोजें", body: "उपलब्ध खोज और फ़िल्टर से लिस्टिंग देखें।", point1: "लिस्टिंग के विवरण की तुलना करें।", point2: "उपलब्ध होने पर व्यक्तियों या कंपनियों की लिस्टिंग देखें।" },
      { title: "बुक करें", body: "तारीखें चुनें और प्लेटफ़ॉर्म से बुकिंग अनुरोध करें।", point1: "मालिक अनुरोध स्वीकार या अस्वीकार कर सकता है।", point2: "कुछ स्वीकृत बुकिंग में सुरक्षा राशि शामिल हो सकती है।" },
      { title: "अनुभव बनाएँ", body: "किराये के लिए उपलब्ध बुकिंग, संदेश, साक्ष्य और समीक्षा उपकरणों का उपयोग करें।", point1: "जहाँ आवश्यक हो पिकअप और वापसी चरणों का पालन करें।", point2: "पात्र किरायों के बाद बुकिंग से जुड़ा फीडबैक दें।" }
    ],
    ownersEyebrow: "मालिकों के लिए", ownersTitle: "उपयुक्त वस्तुएँ तब उपलब्ध कराएँ जब आप उनका उपयोग न कर रहे हों।", ownersLead: "पूरा हुआ किराया किसी मालिक के लिए किराये से आय का अवसर पैदा कर सकता है। यह आय, माँग या किसी विशेष परिणाम का वादा नहीं है।",
    ownerCards: [
      { title: "स्पष्ट लिस्टिंग बनाएँ", body: "ऐसी जानकारी जोड़ें जो किरायेदारों को उपयुक्त वस्तु समझने में मदद करे।", point1: "फ़ोटो और वस्तु विवरण।", point2: "श्रेणी, शहर और दैनिक मूल्य।" },
      { title: "अनुरोधों का जवाब दें", body: "आने वाले बुकिंग अनुरोधों की समीक्षा करें और मौजूदा निर्णय प्रक्रिया का उपयोग करें।", point1: "अनुरोध स्वीकार या अस्वीकार करें।", point2: "जहाँ बुकिंग प्रक्रिया अनुमति दे, जमा राशि तय करें।" },
      { title: "अवसर बनाएँ", body: "उपयुक्त अनुपयोगी संपत्ति, किराया पूरा होने पर किराये की आय दे सकती है।", point1: "खाते की भुगतान प्राप्ति प्राथमिकताएँ अद्यतन रखें।", point2: "जहाँ प्रासंगिक हो साक्ष्य और फीडबैक उपकरणों का उपयोग करें।" }
    ],
    businessEyebrow: "कंपनियों के लिए", businessTitle: "कंपनी खाते उसी किराये के बाज़ार में भाग ले सकते हैं।", businessLead: "SEVOR फिलहाल व्यक्तिगत और कंपनी खाता प्रकारों को मान्यता देता है। कंपनी उपयुक्त किराये की ज़रूरतों या पेशकशों के लिए मौजूदा लिस्टिंग और बुकिंग प्रक्रिया का उपयोग कर सकती है; यह पृष्ठ अलग एंटरप्राइज़ टूल का संकेत नहीं देता।", businessQuote: "उपलब्ध लिस्टिंग और अपनी ज़रूरतों के आधार पर कोई कंपनी मालिक, किरायेदार या दोनों हो सकती है।", businessBody: "उपयुक्त उपकरण या संपत्तियाँ लिस्टिंग के माध्यम से उपलब्ध कराई जा सकती हैं। अस्थायी पहुँच की ज़रूरत वाली कंपनी उसी बाज़ार को देख सकती है। प्लेटफ़ॉर्म का बुकिंग मॉडल साझा है, अलग केवल-व्यावसायिक प्रक्रिया नहीं।", businessPoint1: "कंपनी पंजीकरण में कंपनी के प्रमाण का एक चरण शामिल है।", businessPoint2: "खोज में कंपनियों या व्यक्तियों की लिस्टिंग फ़िल्टर की जा सकती हैं।",
    categoriesEyebrow: "आप क्या किराये पर ले सकते हैं?", categoriesTitle: "आज SEVOR द्वारा इस्तेमाल की जाने वाली श्रेणियाँ देखें।", categoriesLead: "बाज़ार इन उच्च-स्तरीय श्रेणियों में लिस्टिंग दिखा सकता है; वास्तविक उपलब्धता मौजूदा लिस्टिंग पर निर्भर करती है।", categories: ["वाहन", "आवास और ठहराव", "इलेक्ट्रॉनिक्स", "फ़र्नीचर", "कपड़े", "उपकरण और मशीनरी", "अन्य"],
    trustEyebrow: "व्यावहारिक विश्वास उपकरणों पर निर्मित", trustTitle: "सूचित किराये के निर्णयों का समर्थन करने वाले उपकरण।", trustLead: "SEVOR में ऐसे तंत्र शामिल हैं जो उपयोगकर्ताओं को किरायों का दस्तावेज़ीकरण करने, उनके बारे में संवाद करने और उन्हें प्रबंधित करने में मदद करते हैं। वे प्रक्रिया का समर्थन करते हैं; वे किसी परिणाम की गारंटी नहीं हैं।",
    trustCards: [
      { title: "पहचान और कंपनी सत्यापन", body: "प्लेटफ़ॉर्म पहचान पत्र, ड्राइविंग लाइसेंस, पासपोर्ट और कंपनी प्रमाण सहित सत्यापन दस्तावेज़ एकत्र करता है, जिनके समीक्षा मार्ग हैं।" },
      { title: "बुकिंग रिकॉर्ड", body: "बुकिंग अनुरोध, निर्णय और किराये से जुड़े चरण मौजूदा प्रक्रिया में दर्ज होते हैं।" },
      { title: "किराये का संवाद", body: "वस्तु से जुड़े संदेश पात्र प्रतिभागियों को किराये के बारे में संवाद करने में मदद करते हैं।" },
      { title: "साक्ष्य मार्ग", body: "जहाँ किराये की प्रक्रिया आवश्यक करे, वहाँ पिकअप, वापसी और जमा के लिए साक्ष्य उपकरण मौजूद हैं।" },
      { title: "समीक्षाएँ और रेटिंग", body: "बुकिंग से जुड़ा फीडबैक उपयोगकर्ताओं को पिछले अनुभव समझने में मदद करता है, लेकिन गुणवत्ता की गारंटी नहीं देता।" },
      { title: "सहायता और रिपोर्ट", body: "मौजूदा प्लेटफ़ॉर्म उपकरणों से सहायता टिकट और लिस्टिंग रिपोर्ट के मार्ग उपलब्ध हैं।" }
    ],
    paymentsQuote: "स्वीकृत ऑनलाइन बुकिंग वर्तमान PayPal भुगतान प्रक्रिया का उपयोग करती हैं।", paymentsBody: "मालिक मौजूदा खाता सेटिंग्स में Interac, PayPal या Wise के लिए भुगतान प्राप्त करने की प्राथमिकताएँ बनाए रख सकते हैं। वर्तमान भुगतान-प्राप्ति प्रक्रिया मैन्युअल है, इसलिए यह पृष्ठ समय, उपलब्धता या भुगतान-प्राप्ति परिणाम का कोई वादा नहीं करता।", paymentsPoint1: "कुछ बुकिंग पर सुरक्षा राशि लागू हो सकती है।", paymentsPoint2: "जहाँ प्रासंगिक हो, जमा राशि के साक्ष्य और समीक्षा प्रक्रियाएँ लागू होती हैं।",
    visionEyebrow: "स्वामित्व के बजाय पहुँच", visionTitle: "किरायों के लिए लचीली, वैश्विक दृष्टि के साथ बनाया गया।", visionLead: "SEVOR लोगों और कंपनियों के लिए किराये खोजने और उन तक पहुँच को अधिक लचीला बनाने के लिए डिज़ाइन किया गया है। जब उपयुक्त वस्तु पहले से मौजूद और उपलब्ध हो, तो कुछ उपयोगों के लिए अस्थायी रूप से किराये पर लेना कुछ नया खरीदने का विकल्प हो सकता है।",
    visionCards: [
      { title: "जिसकी ज़रूरत हो उसे पाएँ", body: "जब लिस्टिंग किसी ज़रूरत से मेल खाए, अस्थायी पहुँच पाएँ।" },
      { title: "जो मौजूद है उसका अधिक उपयोग करें", body: "उपयुक्त संपत्तियाँ तब उपयोगी बन सकती हैं जब मालिक उन्हें उपलब्ध कराएँ।" },
      { title: "उपयोगी विकल्प बढ़ाएँ", body: "अधिक प्रासंगिक लिस्टिंग किराये खोजने के अधिक अवसर बना सकती हैं।" }
    ],
    whyEyebrow: "SEVOR क्यों?", whyTitle: "एक सरल बाज़ार चक्र।", whyLead: "कोई गिनती या गारंटीकृत परिणाम नहीं—केवल उपयोगी लिस्टिंग और किराये के अवसरों के बीच व्यावहारिक संबंध।", flywheel: ["और उपयोगी वस्तुएँ सूचीबद्ध होती हैं", "किरायेदारों के लिए अधिक विकल्प", "अधिक पूरे हुए किराये मालिकों के लिए अधिक अवसर पैदा कर सकते हैं"],
    finalEyebrow: "आपका अगला किराया", finalTitle: "क्या आप अलग तरीके से किराये पर लेने के लिए तैयार हैं?", finalLead: "अभी उपलब्ध विकल्प देखें, या लिस्टिंग के माध्यम से उपयुक्त वस्तु उपलब्ध कराएँ।", languageTitle: "About पेज की भाषा चुनें", languageLead: "जब आप लौटेंगे, तो इस About पेज के लिए आपकी पसंद याद रखी जाएगी।", footerNote: "SEVOR एक बाज़ार है: उपलब्धता मौजूदा लिस्टिंग पर निर्भर करती है।", privacyLink: "गोपनीयता केंद्र", backTop: "ऊपर जाएँ"
  });

  const zh = completeLocale({
    languageName: "中文", lang: "zh-CN", dir: "ltr",
    pageTitle: "关于 SEVOR | 租你所需", metaDescription: "了解 SEVOR：一个用于寻找实用物品临时使用机会并发布合适物品出租的租赁市场。",
    homeAria: "返回 SEVOR 主页", localNavAria: "SEVOR 关于页面章节", tabListAria: "选择 SEVOR 路径", languageGroupAria: "选择 About 页面语言", flywheelAria: "SEVOR 市场循环", backTopAria: "返回本页顶部", languageSelected: "已为此 About 页面选择 {language}。",
    homeLink: "返回 SEVOR", kicker: "租赁市场", heroTitle: "租你所需，靠你拥有的物品赚取收益。", heroLead: "SEVOR 帮助个人和公司发现实用物品的临时使用机会，并将合适的物品发布出租。", exploreCta: "浏览租赁", listCta: "发布物品", registerCta: "创建账户",
    orbitRentTitle: "获得临时使用权", orbitRentBody: "用于一天、项目、旅行或某个场合。", orbitListTitle: "分享可用资源", orbitListBody: "提供合适的物品出租。", orbitNote: "一个汇集租赁机会的市场。",
    navOverview: "概览", navHow: "如何运作", navRenters: "面向租客", navOwners: "面向所有者", navBusiness: "面向公司", navTrust: "信任", navVision: "愿景",
    overviewEyebrow: "SEVOR 是什么？", overviewTitle: "面向临时使用的市场。", overviewLead: "SEVOR 将希望在有限时间内使用某件物品的租客，与有合适物品可供出租的所有者和提供方连接起来。",
    overviewCards: [
      { title: "租客", body: "希望在限定时间内使用某件物品的个人或组织。" },
      { title: "所有者和提供方", body: "通过发布信息提供合适物品出租的个人或公司。" },
      { title: "租赁机会", body: "在有发布信息时，可发现、查看、申请和完成租赁的地方。" }
    ],
    problemQuote: "为什么要购买一件你可能只会短期需要的物品？", problemBody: "工具、相机、车辆、设备或其他物品，可能在一天、一周、一个项目或某个场合中发挥作用。在某些情况下，拥有它是合理的；在另一些情况下，值得考虑临时使用。", problemPoint1: "在有供应时探索租赁选项。", problemPoint2: "帮助合适的闲置物品为他人发挥作用。",
    compareEyebrow: "一种务实的选择", compareTitle: "租赁和购买满足不同需求。", buyLabel: "购买", buyTitle: "选择拥有", buy: ["支付完整购买价格。", "保留物品。", "存放并维护它。", "适合拥有更合理的情况。"], rentLabel: "租赁", rentTitle: "选择临时使用", rent: ["为约定的临时使用付费。", "在租赁期间使用物品。", "之后归还。", "适合临时使用更合理的情况。"],
    audienceEyebrow: "SEVOR 面向谁？", audienceTitle: "为参与租赁的个人和公司而设。", audienceLead: "SEVOR 支持个人和公司账户类型。可找到什么由当前可用的发布信息决定，并不承诺每个类别都有供应。",
    audienceCards: [
      { title: "个人", body: "寻找实用物品临时使用机会的人。" },
      { title: "租客", body: "比较发布信息、查看详情并发起预订申请的用户。" },
      { title: "所有者", body: "希望在不使用时将合适物品提供出租的人。" },
      { title: "公司", body: "公司账户可使用同一市场流程处理合适的租赁供给和需求。" }
    ],
    relationshipsEyebrow: "一个市场，多种关系", relationshipsTitle: "当有匹配的发布信息时，可向个人或公司租用。", relationshipsLead: "当前的账户和预订模式并不把预订限制为某一种账户类型组合。这些关系都可通过同一租赁流程实现。",
    relationships: [
      { title: "个人 → 个人", body: "个人账户之间的租赁。" },
      { title: "公司 → 个人", body: "个人从公司账户租用。" },
      { title: "个人 → 公司", body: "公司从个人账户租用。" },
      { title: "公司 → 公司", body: "公司账户之间的租赁。" }
    ],
    howEyebrow: "SEVOR 如何运作", howTitle: "选择适合你下一步的路径。", howLead: "这两种视图反映当前的发布和预订流程，不会改变平台的运作方式。", rentTab: "我想租用", listTab: "我想发布",
    rentSteps: [
      { title: "浏览", body: "搜索并筛选可用发布信息。" },
      { title: "查看", body: "阅读发布详情、价格、地点和评分。" },
      { title: "申请", body: "选择日期并提交预订申请。" },
      { title: "完成租赁", body: "所有者作出决定后，在适用时遵循当前的付款、取用、归还和评价步骤。" }
    ],
    listSteps: [
      { title: "准备", body: "使用已获批准的账户，并选择适合发布的物品。" },
      { title: "创建", body: "添加照片、详情、地点、类别和每日价格。" },
      { title: "管理申请", body: "查看预订申请，并通过当前流程回复。" },
      { title: "完成租赁", body: "在适用时协调租赁步骤、凭证和反馈。" }
    ],
    rentersEyebrow: "面向租客", rentersTitle: "在当下找到合适的临时使用方式。", rentersLead: "浏览当前发布信息，比较可选项，查看详情；找到合适的发布信息后，再继续预订流程。",
    renterCards: [
      { title: "发现", body: "使用可用的搜索和筛选功能浏览发布信息。", point1: "比较发布详情。", point2: "在有供应时查看个人或公司的发布信息。" },
      { title: "预订", body: "选择日期并通过平台申请预订。", point1: "所有者可接受或拒绝申请。", point2: "部分已接受的预订可能包含保证金。" },
      { title: "积累体验", body: "使用租赁可用的预订、消息、凭证和评价工具。", point1: "在需要时遵循取用和归还步骤。", point2: "在符合条件的租赁后留下与预订关联的反馈。" }
    ],
    ownersEyebrow: "面向所有者", ownersTitle: "在不使用合适物品时，将其提供出租。", ownersLead: "已完成的租赁可能为所有者创造租赁收入机会。这并不承诺收入、需求或某一特定结果。",
    ownerCards: [
      { title: "创建清晰的发布信息", body: "添加帮助租客了解合适物品的信息。", point1: "照片和物品详情。", point2: "类别、城市和每日价格。" },
      { title: "回复申请", body: "查看收到的预订申请，并使用当前的决定流程。", point1: "接受或拒绝申请。", point2: "在预订流程允许时设定押金。" },
      { title: "创造机会", body: "合适的闲置资产在租赁完成时可能带来租赁收入。", point1: "保持账户收款偏好为最新状态。", point2: "在相关时使用凭证和反馈工具。" }
    ],
    businessEyebrow: "面向公司", businessTitle: "公司账户可以参与同一个租赁市场。", businessLead: "SEVOR 目前支持个人和公司账户类型。公司可使用现有的发布和预订流程来满足合适的租赁需求或提供相应的租赁物品；本页并不表示存在独立的企业工具。", businessQuote: "公司可以是所有者、租客，或两者兼具，具体取决于可用发布信息和自身需求。", businessBody: "合适的设备或资产可通过发布信息提供出租。需要临时使用的公司也可浏览同一个市场。平台的预订模式是共用的，而非仅面向企业的独立流程。", businessPoint1: "公司注册包含公司证明步骤。", businessPoint2: "浏览页可按公司或个人筛选发布信息。",
    categoriesEyebrow: "可以租什么？", categoriesTitle: "浏览 SEVOR 目前使用的类别。", categoriesLead: "市场可以显示这些高层类别下的发布信息；实际可用性取决于当前发布信息。", categories: ["车辆", "住房和短住", "电子产品", "家具", "服装", "工具和设备", "其他"],
    trustEyebrow: "围绕实用的信任工具构建", trustTitle: "支持知情租赁决策的工具。", trustLead: "SEVOR 包含帮助用户记录、沟通和管理租赁的机制。它们支持流程；并不保证任何结果。",
    trustCards: [
      { title: "身份和公司验证", body: "平台收集验证文件，包括身份证、驾驶执照、护照和公司证明，并设有审核路径。" },
      { title: "预订记录", body: "预订申请、决定和租赁相关步骤会在当前流程中记录。" },
      { title: "租赁沟通", body: "与物品关联的消息功能可帮助符合条件的参与者沟通租赁事宜。" },
      { title: "凭证路径", body: "在租赁流程需要时，提供取用、归还和押金相关的凭证工具。" },
      { title: "评价和评分", body: "与预订关联的反馈可帮助用户了解过往体验，但不保证质量。" },
      { title: "支持和报告", body: "现有平台工具提供支持工单和发布信息举报路径。" }
    ],
    paymentsQuote: "已接受的在线预订使用当前的 PayPal 支付流程。", paymentsBody: "所有者可在当前账户设置中维护 Interac、PayPal 或 Wise 的收款偏好。当前收款流程为人工处理，因此本页不承诺处理时间、可用性或收款结果。", paymentsPoint1: "部分预订可能适用保证金。", paymentsPoint2: "在相关情况下，适用押金凭证和审核流程。",
    visionEyebrow: "使用权优先于所有权", visionTitle: "以灵活的全球租赁愿景打造。", visionLead: "SEVOR 旨在让个人和公司更灵活地发现租赁并获得使用机会。当合适的物品已经存在且可供使用时，对于某些用途，短期租赁可以成为购买新物品的替代方案。",
    visionCards: [
      { title: "获得你所需", body: "当发布信息满足需求时，获得临时使用机会。" },
      { title: "更多利用已有物品", body: "所有者提供合适资产时，它们能发挥更多作用。" },
      { title: "增加有用选择", body: "更多相关发布信息可带来更多发现租赁的机会。" }
    ],
    whyEyebrow: "为什么选择 SEVOR？", whyTitle: "一个简单的市场循环。", whyLead: "不设计数器，也不保证结果，只有实用发布信息与租赁机会之间的实际联系。", flywheel: ["更多实用物品被发布", "租客有更多选择", "更多已完成租赁可为所有者创造更多机会"],
    finalEyebrow: "你的下一次租赁", finalTitle: "准备好以不同方式租赁了吗？", finalLead: "浏览现在可用的内容，或通过发布信息提供合适物品出租。", languageTitle: "选择 About 页面语言", languageLead: "下次返回此 About 页面时，将保留你的偏好。", footerNote: "SEVOR 是一个市场：可用性取决于当前发布信息。", privacyLink: "隐私中心", backTop: "返回顶部"
  });

  const ru = completeLocale({
    languageName: "Русский", lang: "ru", dir: "ltr",
    pageTitle: "О SEVOR | Арендуйте то, что нужно", metaDescription: "Узнайте о SEVOR — площадке аренды для поиска временного доступа к полезным вещам и размещения подходящих предметов.",
    homeAria: "Вернуться на главную страницу SEVOR", localNavAria: "Разделы страницы о SEVOR", tabListAria: "Выбрать путь SEVOR", languageGroupAria: "Выбрать язык страницы о SEVOR", flywheelAria: "Цикл площадки SEVOR", backTopAria: "Вернуться в начало этой страницы", languageSelected: "Для этой страницы выбран язык: {language}.",
    homeLink: "Вернуться к SEVOR", kicker: "Площадка для аренды", heroTitle: "Арендуйте то, что нужно. Зарабатывайте на том, что принадлежит вам.", heroLead: "SEVOR помогает людям и компаниям находить временный доступ к полезным вещам и делать подходящие предметы доступными для аренды.", exploreCta: "Посмотреть аренду", listCta: "Разместить предмет", registerCta: "Создать аккаунт",
    orbitRentTitle: "Найдите временный доступ", orbitRentBody: "На день, для проекта, поездки или события.", orbitListTitle: "Поделитесь доступностью", orbitListBody: "Сделайте подходящий предмет доступным.", orbitNote: "Одна площадка для возможностей аренды.",
    navOverview: "Обзор", navHow: "Как это работает", navRenters: "Для арендаторов", navOwners: "Для владельцев", navBusiness: "Для компаний", navTrust: "Доверие", navVision: "Видение",
    overviewEyebrow: "Что такое SEVOR?", overviewTitle: "Площадка для временного доступа.", overviewLead: "SEVOR связывает арендаторов, которым нужен предмет на ограниченный срок, с владельцами и поставщиками, у которых есть подходящие предметы для аренды.",
    overviewCards: [
      { title: "Арендаторы", body: "Люди или организации, которым нужен доступ к предмету на определённый срок." },
      { title: "Владельцы и поставщики", body: "Частные лица или компании, размещающие подходящие предметы для аренды." },
      { title: "Возможности аренды", body: "Место для поиска, просмотра, запроса и завершения аренды при наличии объявлений." }
    ],
    problemQuote: "Зачем покупать то, что может понадобиться лишь на короткое время?", problemBody: "Инструмент, камера, автомобиль, устройство или другой предмет могут быть нужны на день, неделю, для проекта или события. Владение имеет смысл в одних случаях; в других стоит рассмотреть временный доступ.", problemPoint1: "Находите варианты аренды, когда они доступны.", problemPoint2: "Помогайте подходящим неиспользуемым вещам становиться полезными для других.",
    compareEyebrow: "Практичный выбор", compareTitle: "Аренда и покупка решают разные задачи.", buyLabel: "КУПИТЬ", buyTitle: "Выбрать владение", buy: ["Заплатить полную цену покупки.", "Оставить предмет себе.", "Хранить и обслуживать его.", "Подходит, когда владение оправдано."], rentLabel: "АРЕНДОВАТЬ", rentTitle: "Выбрать временный доступ", rent: ["Оплатить согласованный временный доступ.", "Пользоваться предметом в период аренды.", "Вернуть его после этого.", "Подходит, когда временный доступ разумнее."],
    audienceEyebrow: "Для кого SEVOR?", audienceTitle: "Для людей и компаний, участвующих в аренде.", audienceLead: "SEVOR поддерживает индивидуальные и корпоративные аккаунты. То, что может найти каждый пользователь, определяется доступными объявлениями, а не обещанием наличия каждой категории.",
    audienceCards: [
      { title: "Частные лица", body: "Люди, ищущие временный доступ к полезным вещам." },
      { title: "Арендаторы", body: "Пользователи, которые сравнивают объявления, изучают детали и отправляют запросы на бронирование." },
      { title: "Владельцы", body: "Люди, которые хотят предложить подходящие предметы, когда сами ими не пользуются." },
      { title: "Компании", body: "Корпоративные аккаунты могут использовать тот же путь площадки для подходящих предложений и потребностей аренды." }
    ],
    relationshipsEyebrow: "Одна площадка — несколько видов отношений", relationshipsTitle: "Арендуйте у людей или компаний, когда есть подходящие объявления.", relationshipsLead: "Текущая модель аккаунтов и бронирований не ограничивает бронирование одной комбинацией типов аккаунтов. Эти отношения возможны в рамках одного процесса аренды.",
    relationships: [
      { title: "Частное лицо → Частное лицо", body: "Аренда между индивидуальными аккаунтами." },
      { title: "Компания → Частное лицо", body: "Частное лицо арендует у корпоративного аккаунта." },
      { title: "Частное лицо → Компания", body: "Компания арендует у индивидуального аккаунта." },
      { title: "Компания → Компания", body: "Аренда между корпоративными аккаунтами." }
    ],
    howEyebrow: "Как работает SEVOR", howTitle: "Выберите путь, соответствующий вашему следующему шагу.", howLead: "Эти два представления отражают текущий процесс размещения и бронирования, не меняя работу платформы.", rentTab: "Я хочу арендовать", listTab: "Я хочу разместить",
    rentSteps: [
      { title: "Найдите", body: "Ищите и фильтруйте доступные объявления." },
      { title: "Изучите", body: "Читайте детали объявления, цену, место и оценки." },
      { title: "Запросите", body: "Выберите даты и отправьте запрос на бронирование." },
      { title: "Завершите аренду", body: "После решения владельца выполните текущие шаги оплаты, получения, возврата и отзыва, если они применимы." }
    ],
    listSteps: [
      { title: "Подготовьтесь", body: "Используйте одобренный аккаунт и выберите подходящий предмет для размещения." },
      { title: "Создайте", body: "Добавьте фото, детали, местоположение, категорию и дневную цену." },
      { title: "Управляйте запросами", body: "Просматривайте запросы на бронирование и отвечайте в текущем процессе." },
      { title: "Завершайте аренду", body: "Координируйте шаги аренды, доказательства и отзывы, где это применимо." }
    ],
    rentersEyebrow: "Для арендаторов", rentersTitle: "Найдите подходящий временный доступ на нужный момент.", rentersLead: "Просматривайте текущие объявления, сравнивайте доступное, изучайте детали и переходите к бронированию, когда объявление вам подходит.",
    renterCards: [
      { title: "Откройте", body: "Изучайте объявления через доступные поиск и фильтры.", point1: "Сравнивайте детали объявлений.", point2: "Смотрите объявления частных лиц или компаний, когда они доступны." },
      { title: "Забронируйте", body: "Выберите даты и запросите бронирование через платформу.", point1: "Владелец может принять или отклонить запрос.", point2: "К некоторым принятым бронированиям может применяться сумма обеспечения." },
      { title: "Набирайте опыт", body: "Используйте доступные для аренды инструменты бронирования, сообщений, доказательств и отзывов.", point1: "Следуйте шагам получения и возврата, когда это необходимо.", point2: "Оставляйте отзыв, связанный с бронированием, после подходящей аренды." }
    ],
    ownersEyebrow: "Для владельцев", ownersTitle: "Делайте подходящие предметы доступными, когда не используете их.", ownersLead: "Завершённая аренда может создать для владельца возможность арендного дохода. Это не обещание дохода, спроса или конкретного результата.",
    ownerCards: [
      { title: "Создайте понятное объявление", body: "Добавьте информацию, помогающую арендаторам понять подходящий предмет.", point1: "Фото и детали предмета.", point2: "Категория, город и дневная цена." },
      { title: "Отвечайте на запросы", body: "Просматривайте входящие запросы на бронирование и используйте текущий процесс решения.", point1: "Примите или отклоните запрос.", point2: "Установите залог, если это позволяет процесс бронирования." },
      { title: "Создайте возможность", body: "Подходящий неиспользуемый актив может приносить арендный доход после завершения аренды.", point1: "Поддерживайте актуальность предпочтений выплат в аккаунте.", point2: "Используйте доказательства и отзывы, когда это уместно." }
    ],
    businessEyebrow: "Для компаний", businessTitle: "Корпоративные аккаунты могут участвовать в той же площадке аренды.", businessLead: "SEVOR в настоящее время распознаёт индивидуальные и корпоративные типы аккаунтов. Компания может использовать существующий процесс размещения и бронирования для подходящих потребностей или предложений аренды; эта страница не подразумевает отдельные корпоративные инструменты.", businessQuote: "Компания может быть владельцем, арендатором или и тем и другим — в зависимости от доступных объявлений и своих потребностей.", businessBody: "Подходящее оборудование или активы можно размещать в объявлениях. Компании, которой нужен временный доступ, также доступна та же площадка. Модель бронирования общая, а не отдельная только для бизнеса.", businessPoint1: "Регистрация компании включает этап подтверждения компании.", businessPoint2: "В каталоге можно фильтровать объявления компаний или частных лиц.",
    categoriesEyebrow: "Что можно арендовать?", categoriesTitle: "Изучите категории, которые SEVOR использует сегодня.", categoriesLead: "Площадка может показывать объявления в этих основных категориях; фактическая доступность зависит от текущих объявлений.", categories: ["Транспорт", "Жильё и проживание", "Электроника", "Мебель", "Одежда", "Инструменты и оборудование", "Другое"],
    trustEyebrow: "Создано вокруг практических инструментов доверия", trustTitle: "Инструменты, поддерживающие обоснованные решения об аренде.", trustLead: "SEVOR включает механизмы, помогающие пользователям документировать аренду, общаться о ней и управлять ею. Они поддерживают процесс, но не гарантируют какой-либо результат.",
    trustCards: [
      { title: "Проверка личности и компании", body: "Платформа собирает документы для проверки, включая удостоверение личности, водительское удостоверение, паспорт и подтверждение компании, с путями проверки." },
      { title: "Записи бронирований", body: "Запросы, решения и шаги, связанные с арендой, фиксируются в текущем процессе." },
      { title: "Общение об аренде", body: "Сообщения, связанные с предметом, помогают допущенным участникам общаться об аренде." },
      { title: "Пути доказательств", body: "Инструменты доказательств для получения, возврата и залога существуют, когда этого требует процесс аренды." },
      { title: "Отзывы и оценки", body: "Отзывы, связанные с бронированием, помогают узнать о прошлом опыте без гарантии качества." },
      { title: "Поддержка и жалобы", body: "В существующих инструментах доступны тикеты поддержки и пути сообщения о объявлениях." }
    ],
    paymentsQuote: "Для принятых онлайн-бронирований используется текущий платёжный процесс PayPal.", paymentsBody: "Владельцы могут поддерживать предпочтения выплат через Interac, PayPal или Wise в текущих настройках аккаунта. Текущий процесс выплат выполняется вручную, поэтому эта страница не обещает сроки, доступность или результат выплаты.", paymentsPoint1: "К некоторым бронированиям может применяться сумма обеспечения.", paymentsPoint2: "Доказательства по залогу и пути их проверки применяются там, где это уместно.",
    visionEyebrow: "Доступ вместо владения", visionTitle: "Создано с гибким глобальным видением аренды.", visionLead: "SEVOR создана, чтобы сделать поиск аренды и доступ к ней более гибкими для людей и компаний. Когда подходящий предмет уже существует и доступен, временная аренда может быть альтернативой покупке нового предмета для некоторых задач.",
    visionCards: [
      { title: "Получайте нужное", body: "Находите временный доступ, когда объявление отвечает потребности." },
      { title: "Используйте больше того, что уже есть", body: "Подходящие активы могут стать полезными, когда владельцы делают их доступными." },
      { title: "Расширяйте полезный выбор", body: "Более подходящие объявления могут создавать больше возможностей найти аренду." }
    ],
    whyEyebrow: "Почему SEVOR?", whyTitle: "Простой цикл площадки.", whyLead: "Без счётчиков и гарантированных результатов — только практическая связь между полезными объявлениями и возможностями аренды.", flywheel: ["Размещается больше полезных предметов", "Больше выбора для арендаторов", "Больше завершённых аренд может создать больше возможностей для владельцев"],
    finalEyebrow: "Ваша следующая аренда", finalTitle: "Готовы арендовать по-другому?", finalLead: "Посмотрите, что доступно сейчас, или сделайте подходящий предмет доступным через объявление.", languageTitle: "Выберите язык страницы о SEVOR", languageLead: "Ваш выбор сохраняется для этой страницы при следующем посещении.", footerNote: "SEVOR — это площадка: доступность зависит от текущих объявлений.", privacyLink: "Центр конфиденциальности", backTop: "Наверх"
  });

  const de = completeLocale({
    languageName: "Deutsch", lang: "de", dir: "ltr",
    pageTitle: "Über SEVOR | Mieten Sie, was Sie brauchen", metaDescription: "Entdecken Sie SEVOR, einen Mietmarktplatz für zeitlich begrenzten Zugang zu nützlichen Dingen und passende Mietangebote.",
    homeAria: "Zur SEVOR-Startseite zurückkehren", localNavAria: "Abschnitte über SEVOR", tabListAria: "SEVOR-Weg auswählen", languageGroupAria: "Sprache der Über-Seite auswählen", flywheelAria: "SEVOR-Marktplatzkreislauf", backTopAria: "Zum Anfang dieser Seite zurückkehren", languageSelected: "{language} ist für diese Über-Seite ausgewählt.",
    homeLink: "Zurück zu SEVOR", kicker: "Ein Marktplatz für Vermietungen", heroTitle: "Mieten Sie, was Sie brauchen. Verdienen Sie mit dem, was Sie besitzen.", heroLead: "SEVOR hilft Menschen und Unternehmen, zeitlich begrenzten Zugang zu nützlichen Dingen zu entdecken und geeignete Artikel zur Miete anzubieten.", exploreCta: "Mietangebote entdecken", listCta: "Artikel inserieren", registerCta: "Konto erstellen",
    orbitRentTitle: "Zugang finden", orbitRentBody: "Für einen Tag, ein Projekt, eine Reise oder einen Anlass.", orbitListTitle: "Verfügbarkeit teilen", orbitListBody: "Einen passenden Artikel verfügbar machen.", orbitNote: "Ein Marktplatz für Mietmöglichkeiten.",
    navOverview: "Überblick", navHow: "So funktioniert es", navRenters: "Für Mietende", navOwners: "Für Eigentümer", navBusiness: "Für Unternehmen", navTrust: "Vertrauen", navVision: "Vision",
    overviewEyebrow: "Was ist SEVOR?", overviewTitle: "Ein Marktplatz für zeitlich begrenzten Zugang.", overviewLead: "SEVOR bringt Mietinteressierte, die etwas für einen begrenzten Zeitraum nutzen möchten, mit Eigentümern und Anbietern zusammen, die geeignete Artikel zur Miete anbieten.",
    overviewCards: [
      { title: "Mietende", body: "Menschen oder Organisationen, die für einen bestimmten Zeitraum Zugang zu einem Artikel suchen." },
      { title: "Eigentümer und Anbieter", body: "Privatpersonen oder Unternehmen, die passende Artikel über Inserate verfügbar machen." },
      { title: "Mietmöglichkeiten", body: "Ein Ort, um Vermietungen zu entdecken, zu prüfen, anzufragen und abzuschließen, wenn Inserate verfügbar sind." }
    ],
    problemQuote: "Warum etwas kaufen, das Sie vielleicht nur kurz brauchen?", problemBody: "Ein Werkzeug, eine Kamera, ein Fahrzeug, ein Gerät oder ein anderer Artikel kann für einen Tag, eine Woche, ein Projekt oder einen Anlass nützlich sein. Eigentum ist in manchen Situationen sinnvoll; in anderen kann sich zeitlich begrenzter Zugang lohnen.", problemPoint1: "Entdecken Sie Mietoptionen, wenn sie verfügbar sind.", problemPoint2: "Helfen Sie passenden ungenutzten Artikeln, für jemand anderen nützlich zu werden.",
    compareEyebrow: "Eine praktische Wahl", compareTitle: "Mieten und Kaufen erfüllen unterschiedliche Bedürfnisse.", buyLabel: "KAUFEN", buyTitle: "Eigentum wählen", buy: ["Den vollen Kaufpreis zahlen.", "Den Artikel behalten.", "Ihn lagern und warten.", "Sinnvoll, wenn Eigentum sinnvoll ist."], rentLabel: "MIETEN", rentTitle: "Zeitlich begrenzten Zugang wählen", rent: ["Für den vereinbarten Zugang zahlen.", "Den Artikel im Mietzeitraum nutzen.", "Ihn anschließend zurückgeben.", "Sinnvoll, wenn zeitlich begrenzter Zugang mehr Sinn ergibt."],
    audienceEyebrow: "Für wen ist SEVOR?", audienceTitle: "Für Menschen und Unternehmen, die an Vermietungen teilnehmen.", audienceLead: "SEVOR unterstützt individuelle und Unternehmenskonten. Verfügbare Inserate — nicht ein Versprechen für jede Kategorie — bestimmen, was jede Person finden kann.",
    audienceCards: [
      { title: "Privatpersonen", body: "Menschen, die zeitlich begrenzten Zugang zu nützlichen Dingen suchen." },
      { title: "Mietende", body: "Nutzer, die Inserate vergleichen, Details prüfen und Buchungsanfragen stellen." },
      { title: "Eigentümer", body: "Menschen, die passende Artikel anbieten möchten, wenn sie sie nicht nutzen." },
      { title: "Unternehmen", body: "Unternehmenskonten können denselben Marktplatzablauf für passende Mietangebote und -bedarfe nutzen." }
    ],
    relationshipsEyebrow: "Ein Marktplatz, mehrere Beziehungen", relationshipsTitle: "Mieten Sie von Privatpersonen oder Unternehmen, wenn passende Inserate verfügbar sind.", relationshipsLead: "Das aktuelle Konto- und Buchungsmodell beschränkt eine Buchung nicht auf eine bestimmte Kombination von Kontotypen. Diese Beziehungen verwenden denselben Mietablauf.",
    relationships: [
      { title: "Privatperson → Privatperson", body: "Eine Vermietung zwischen individuellen Konten." },
      { title: "Unternehmen → Privatperson", body: "Eine Privatperson mietet von einem Unternehmenskonto." },
      { title: "Privatperson → Unternehmen", body: "Ein Unternehmen mietet von einem individuellen Konto." },
      { title: "Unternehmen → Unternehmen", body: "Eine Vermietung zwischen Unternehmenskonten." }
    ],
    howEyebrow: "So funktioniert SEVOR", howTitle: "Wählen Sie den Weg, der zu Ihrem nächsten Schritt passt.", howLead: "Diese beiden Ansichten spiegeln den aktuellen Inserats- und Buchungsablauf wider, ohne die Funktionsweise der Plattform zu verändern.", rentTab: "Ich möchte mieten", listTab: "Ich möchte inserieren",
    rentSteps: [
      { title: "Entdecken", body: "Verfügbare Inserate suchen und filtern." },
      { title: "Prüfen", body: "Details, Preise, Standort und Bewertungen lesen." },
      { title: "Anfragen", body: "Daten wählen und eine Buchungsanfrage senden." },
      { title: "Miete abschließen", body: "Nach der Entscheidung des Eigentümers die aktuellen Schritte für Zahlung, Abholung, Rückgabe und Bewertung ausführen, soweit sie gelten." }
    ],
    listSteps: [
      { title: "Vorbereiten", body: "Ein genehmigtes Konto verwenden und einen passenden Artikel wählen." },
      { title: "Erstellen", body: "Fotos, Details, Ort, Kategorie und Tagespreis hinzufügen." },
      { title: "Anfragen verwalten", body: "Buchungsanfragen prüfen und im aktuellen Ablauf antworten." },
      { title: "Vermietungen abschließen", body: "Mietschritte, Nachweise und Feedback koordinieren, soweit sie gelten." }
    ],
    rentersEyebrow: "Für Mietende", rentersTitle: "Finden Sie den passenden zeitlich begrenzten Zugang für den Moment.", rentersLead: "Durchsuchen Sie aktuelle Inserate, vergleichen Sie Verfügbares, prüfen Sie Details und setzen Sie den Buchungsablauf fort, wenn ein Inserat passt.",
    renterCards: [
      { title: "Entdecken", body: "Inserate mit der verfügbaren Suche und den Filtern erkunden.", point1: "Inseratsdetails vergleichen.", point2: "Inserate von Unternehmen oder Privatpersonen sehen, wenn verfügbar." },
      { title: "Buchen", body: "Daten wählen und eine Buchung über die Plattform anfragen.", point1: "Ein Eigentümer kann eine Anfrage annehmen oder ablehnen.", point2: "Für einige angenommene Buchungen kann ein Sicherheitsbetrag gelten." },
      { title: "Erfahrung aufbauen", body: "Die verfügbaren Buchungs-, Nachrichten-, Nachweis- und Bewertungswerkzeuge nutzen.", point1: "Abhol- und Rückgabeschritte befolgen, wenn erforderlich.", point2: "Nach berechtigten Vermietungen buchungsbezogenes Feedback hinterlassen." }
    ],
    ownersEyebrow: "Für Eigentümer", ownersTitle: "Stellen Sie geeignete Artikel zur Verfügung, wenn Sie sie nicht nutzen.", ownersLead: "Eine abgeschlossene Vermietung kann einem Eigentümer eine Gelegenheit für Mieteinnahmen eröffnen. Sie ist kein Versprechen für Einnahmen, Nachfrage oder ein bestimmtes Ergebnis.",
    ownerCards: [
      { title: "Klares Inserat erstellen", body: "Informationen hinzufügen, die Mietenden helfen, einen passenden Artikel zu verstehen.", point1: "Fotos und Artikeldetails.", point2: "Kategorie, Stadt und Tagespreis." },
      { title: "Auf Anfragen reagieren", body: "Eingehende Buchungsanfragen prüfen und den aktuellen Entscheidungsablauf nutzen.", point1: "Anfrage annehmen oder ablehnen.", point2: "Kaution festlegen, sofern der Buchungsablauf dies zulässt." },
      { title: "Eine Möglichkeit schaffen", body: "Ein passender ungenutzter Vermögenswert kann nach einer abgeschlossenen Vermietung Mieteinnahmen erzielen.", point1: "Auszahlungspräferenzen im Konto aktuell halten.", point2: "Nachweis- und Feedbackwerkzeuge nutzen, wenn relevant." }
    ],
    businessEyebrow: "Für Unternehmen", businessTitle: "Unternehmenskonten können am selben Mietmarktplatz teilnehmen.", businessLead: "SEVOR erkennt derzeit individuelle und Unternehmenskonten. Ein Unternehmen kann den bestehenden Inserats- und Buchungsablauf für passende Mietbedarfe oder -angebote nutzen; diese Seite impliziert keine separaten Unternehmenstools.", businessQuote: "Ein Unternehmen kann Eigentümer, Mieter oder beides sein — je nach verfügbaren Inseraten und seinem Bedarf.", businessBody: "Passende Ausrüstung oder Vermögenswerte können über Inserate verfügbar gemacht werden. Ein Unternehmen mit temporärem Bedarf kann denselben Marktplatz erkunden. Das Buchungsmodell ist gemeinsam und kein separater Ablauf nur für Unternehmen.", businessPoint1: "Die Unternehmensregistrierung enthält einen Schritt zum Unternehmensnachweis.", businessPoint2: "Entdecken kann Inserate von Unternehmen oder Privatpersonen filtern.",
    categoriesEyebrow: "Was können Sie mieten?", categoriesTitle: "Entdecken Sie die Kategorien, die SEVOR derzeit verwendet.", categoriesLead: "Der Marktplatz kann Inserate in diesen übergeordneten Kategorien anzeigen; die tatsächliche Verfügbarkeit hängt von aktuellen Inseraten ab.", categories: ["Fahrzeuge", "Unterkünfte und Aufenthalte", "Elektronik", "Möbel", "Kleidung", "Werkzeuge und Ausrüstung", "Sonstiges"],
    trustEyebrow: "Mit praktischen Vertrauenswerkzeugen entwickelt", trustTitle: "Werkzeuge für fundierte Mietentscheidungen.", trustLead: "SEVOR enthält Mechanismen, die Nutzer dabei unterstützen, Vermietungen zu dokumentieren, darüber zu kommunizieren und sie zu verwalten. Sie unterstützen den Ablauf; sie garantieren kein Ergebnis.",
    trustCards: [
      { title: "Identitäts- und Unternehmensprüfung", body: "Die Plattform sammelt Prüfungsdokumente wie Ausweis, Führerschein, Reisepass und Unternehmensnachweis mit Prüfwegen." },
      { title: "Buchungsaufzeichnungen", body: "Buchungsanfragen, Entscheidungen und mietbezogene Schritte werden im aktuellen Ablauf erfasst." },
      { title: "Kommunikation zur Miete", body: "Artikelbezogene Nachrichten helfen berechtigten Teilnehmenden, über eine Vermietung zu kommunizieren." },
      { title: "Nachweiswege", body: "Nachweiswerkzeuge für Abholung, Rückgabe und Kaution existieren, wenn der Mietablauf sie erfordert." },
      { title: "Bewertungen", body: "Buchungsbezogenes Feedback hilft Nutzern, frühere Erfahrungen zu verstehen, ohne Qualität zu garantieren." },
      { title: "Support und Meldungen", body: "Supporttickets und Wege zum Melden von Inseraten sind in den bestehenden Plattformwerkzeugen verfügbar." }
    ],
    paymentsQuote: "Akzeptierte Online-Buchungen verwenden den aktuellen PayPal-Zahlungsablauf.", paymentsBody: "Eigentümer können in den aktuellen Kontoeinstellungen Auszahlungspräferenzen für Interac, PayPal oder Wise hinterlegen. Der aktuelle Auszahlungsprozess ist manuell; diese Seite verspricht daher weder Zeitpunkt, Verfügbarkeit noch Ergebnis einer Auszahlung.", paymentsPoint1: "Für einige Buchungen kann ein Sicherheitsbetrag gelten.", paymentsPoint2: "Nachweise zur Kaution und Prüfwege gelten, sofern relevant.",
    visionEyebrow: "Zugang statt Eigentum", visionTitle: "Mit einer flexiblen, globalen Vision für Vermietungen entwickelt.", visionLead: "SEVOR soll es Menschen und Unternehmen ermöglichen, Vermietungen und Zugang flexibler zu entdecken. Wenn ein geeigneter Artikel bereits existiert und verfügbar gemacht wird, kann zeitlich begrenztes Mieten für einige Nutzungen eine Alternative zum Neukauf sein.",
    visionCards: [
      { title: "Zugang zu dem, was Sie brauchen", body: "Zeitlich begrenzten Zugang finden, wenn ein Inserat einem Bedarf entspricht." },
      { title: "Mehr von Bestehendem nutzen", body: "Passende Vermögenswerte können nützlich werden, wenn Eigentümer sie verfügbar machen." },
      { title: "Nützliche Auswahl erweitern", body: "Mehr relevante Inserate können mehr Möglichkeiten schaffen, Vermietungen zu entdecken." }
    ],
    whyEyebrow: "Warum SEVOR?", whyTitle: "Ein einfacher Marktplatzkreislauf.", whyLead: "Keine Zähler und keine garantierten Ergebnisse — nur die praktische Verbindung zwischen nützlichen Inseraten und Mietmöglichkeiten.", flywheel: ["Mehr nützliche Artikel werden inseriert", "Mehr Auswahl für Mietende", "Mehr abgeschlossene Vermietungen können mehr Möglichkeiten für Eigentümer schaffen"],
    finalEyebrow: "Ihre nächste Miete", finalTitle: "Bereit, anders zu mieten?", finalLead: "Entdecken Sie, was jetzt verfügbar ist, oder stellen Sie einen passenden Artikel über ein Inserat zur Verfügung.", languageTitle: "Sprache der Über-Seite auswählen", languageLead: "Ihre Auswahl bleibt für diese Über-Seite gespeichert, wenn Sie zurückkehren.", footerNote: "SEVOR ist ein Marktplatz: Die Verfügbarkeit hängt von aktuellen Inseraten ab.", privacyLink: "Datenschutz-Center", backTop: "Nach oben"
  });

  const it = completeLocale({
    languageName: "Italiano", lang: "it", dir: "ltr",
    pageTitle: "Informazioni su SEVOR | Noleggia ciò di cui hai bisogno", metaDescription: "Scopri SEVOR, un marketplace di noleggio per trovare accesso temporaneo a beni utili e rendere disponibili articoli adatti.",
    homeAria: "Torna alla home page di SEVOR", localNavAria: "Sezioni Informazioni su SEVOR", tabListAria: "Scegli un percorso SEVOR", languageGroupAria: "Scegli la lingua della pagina Informazioni", flywheelAria: "Ciclo del marketplace SEVOR", backTopAria: "Torna all’inizio della pagina", languageSelected: "{language} selezionato per questa pagina Informazioni.",
    homeLink: "Torna a SEVOR", kicker: "Un marketplace di noleggio", heroTitle: "Noleggia ciò di cui hai bisogno. Guadagna con ciò che possiedi.", heroLead: "SEVOR aiuta persone e aziende a scoprire un accesso temporaneo a beni utili e a rendere disponibili per il noleggio articoli adatti.", exploreCta: "Esplora i noleggi", listCta: "Pubblica un articolo", registerCta: "Crea un account",
    orbitRentTitle: "Trova accesso", orbitRentBody: "Per un giorno, un progetto, un viaggio o un’occasione.", orbitListTitle: "Condividi la disponibilità", orbitListBody: "Rendi disponibile un articolo adatto.", orbitNote: "Un solo marketplace per opportunità di noleggio.",
    navOverview: "Panoramica", navHow: "Come funziona", navRenters: "Per chi noleggia", navOwners: "Per i proprietari", navBusiness: "Per le aziende", navTrust: "Fiducia", navVision: "Visione",
    overviewEyebrow: "Che cos’è SEVOR?", overviewTitle: "Un marketplace per l’accesso temporaneo.", overviewLead: "SEVOR mette in contatto chi cerca qualcosa da usare per un periodo limitato con proprietari e fornitori che hanno articoli adatti disponibili per il noleggio.",
    overviewCards: [
      { title: "Chi noleggia", body: "Persone o organizzazioni che cercano accesso a un articolo per un periodo definito." },
      { title: "Proprietari e fornitori", body: "Privati o aziende che rendono disponibili articoli adatti tramite annunci." },
      { title: "Opportunità di noleggio", body: "Uno spazio per scoprire, esaminare, richiedere e completare noleggi quando sono disponibili annunci." }
    ],
    problemQuote: "Perché acquistare qualcosa di cui potresti aver bisogno solo per poco tempo?", problemBody: "Un attrezzo, una fotocamera, un veicolo, un dispositivo o un altro articolo può essere utile per un giorno, una settimana, un progetto o un’occasione. La proprietà può avere senso in alcune situazioni; in altre vale la pena valutare l’accesso temporaneo.", problemPoint1: "Scopri le opzioni di noleggio quando sono disponibili.", problemPoint2: "Aiuta articoli adatti e inutilizzati a diventare utili per qualcun altro.",
    compareEyebrow: "Una scelta pratica", compareTitle: "Noleggiare e acquistare rispondono a esigenze diverse.", buyLabel: "ACQUISTARE", buyTitle: "Scegliere la proprietà", buy: ["Pagare l’intero prezzo di acquisto.", "Conservare l’articolo.", "Riporlo e curarne la manutenzione.", "Utile quando la proprietà è la scelta sensata."], rentLabel: "NOLEGGIARE", rentTitle: "Scegliere l’accesso temporaneo", rent: ["Pagare per l’accesso temporaneo concordato.", "Usare l’articolo nel periodo di noleggio.", "Restituirlo dopo.", "Utile quando l’accesso temporaneo è più sensato."],
    audienceEyebrow: "A chi si rivolge SEVOR?", audienceTitle: "Pensato per persone e aziende che partecipano ai noleggi.", audienceLead: "SEVOR supporta tipi di account individuale e aziendale. Sono gli annunci disponibili, non una promessa su ogni categoria, a determinare ciò che ciascuno può trovare.",
    audienceCards: [
      { title: "Privati", body: "Persone che cercano accesso temporaneo a beni utili." },
      { title: "Chi noleggia", body: "Utenti che confrontano annunci, controllano i dettagli e inviano richieste di prenotazione." },
      { title: "Proprietari", body: "Persone che vogliono rendere disponibili articoli adatti quando non li stanno usando." },
      { title: "Aziende", body: "Gli account aziendali possono usare lo stesso flusso del marketplace per offerte e necessità di noleggio adatte." }
    ],
    relationshipsEyebrow: "Un marketplace, più relazioni", relationshipsTitle: "Noleggia da persone o aziende quando sono disponibili annunci corrispondenti.", relationshipsLead: "L’attuale modello di account e prenotazione non limita una prenotazione a un abbinamento di tipi di account. Queste relazioni usano lo stesso flusso di noleggio.",
    relationships: [
      { title: "Privato → Privato", body: "Un noleggio tra account individuali." },
      { title: "Azienda → Privato", body: "Un privato noleggia da un account aziendale." },
      { title: "Privato → Azienda", body: "Un’azienda noleggia da un account individuale." },
      { title: "Azienda → Azienda", body: "Un noleggio tra account aziendali." }
    ],
    howEyebrow: "Come funziona SEVOR", howTitle: "Scegli il percorso adatto al tuo prossimo passo.", howLead: "Queste due viste riflettono l’attuale flusso di annunci e prenotazioni senza modificare il funzionamento della piattaforma.", rentTab: "Voglio noleggiare", listTab: "Voglio pubblicare",
    rentSteps: [
      { title: "Esplora", body: "Cerca e filtra gli annunci disponibili." },
      { title: "Esamina", body: "Leggi dettagli, prezzi, località e valutazioni." },
      { title: "Richiedi", body: "Scegli le date e invia una richiesta di prenotazione." },
      { title: "Completa il noleggio", body: "Dopo la decisione del proprietario, segui gli attuali passaggi di pagamento, ritiro, restituzione e recensione quando applicabili." }
    ],
    listSteps: [
      { title: "Preparati", body: "Usa un account approvato e scegli un articolo adatto da pubblicare." },
      { title: "Crea", body: "Aggiungi foto, dettagli, località, categoria e prezzo giornaliero." },
      { title: "Gestisci le richieste", body: "Esamina le richieste di prenotazione e rispondi nel flusso attuale." },
      { title: "Completa i noleggi", body: "Coordina passaggi di noleggio, prove e feedback quando applicabili." }
    ],
    rentersEyebrow: "Per chi noleggia", rentersTitle: "Trova l’accesso temporaneo giusto per il momento.", rentersLead: "Esplora gli annunci attuali, confronta ciò che è disponibile, controlla i dettagli e prosegui nel flusso di prenotazione quando un annuncio è adatto.",
    renterCards: [
      { title: "Scopri", body: "Esplora gli annunci con la ricerca e i filtri disponibili.", point1: "Confronta i dettagli degli annunci.", point2: "Vedi annunci di privati o aziende quando disponibili." },
      { title: "Prenota", body: "Seleziona le date e richiedi una prenotazione tramite la piattaforma.", point1: "Un proprietario può accettare o rifiutare una richiesta.", point2: "Alcune prenotazioni accettate possono includere un importo di garanzia." },
      { title: "Crea esperienza", body: "Usa gli strumenti disponibili per prenotazioni, messaggistica, prove e recensioni.", point1: "Segui i passaggi di ritiro e restituzione quando richiesti.", point2: "Lascia feedback collegato alla prenotazione dopo noleggi idonei." }
    ],
    ownersEyebrow: "Per i proprietari", ownersTitle: "Rendi disponibili articoli adatti quando non li stai usando.", ownersLead: "Un noleggio completato può creare un’opportunità di reddito da noleggio per un proprietario. Non è una promessa di reddito, domanda o risultato specifico.",
    ownerCards: [
      { title: "Crea un annuncio chiaro", body: "Aggiungi informazioni che aiutino chi noleggia a capire un articolo adatto.", point1: "Foto e dettagli dell’articolo.", point2: "Categoria, città e prezzo giornaliero." },
      { title: "Rispondi alle richieste", body: "Esamina le richieste di prenotazione ricevute e usa il flusso decisionale attuale.", point1: "Accetta o rifiuta una richiesta.", point2: "Imposta un deposito quando il flusso di prenotazione lo consente." },
      { title: "Crea un’opportunità", body: "Un bene adatto e inutilizzato può generare reddito da noleggio quando un noleggio è completato.", point1: "Mantieni aggiornate le preferenze di accredito dell’account.", point2: "Usa strumenti di prova e feedback quando pertinenti." }
    ],
    businessEyebrow: "Per le aziende", businessTitle: "Gli account aziendali possono partecipare allo stesso marketplace di noleggio.", businessLead: "SEVOR riconosce attualmente i tipi di account individuale e aziendale. Un’azienda può usare l’attuale flusso di annunci e prenotazioni per esigenze o offerte di noleggio adatte; questa pagina non implica strumenti aziendali separati.", businessQuote: "Un’azienda può essere proprietaria, locataria o entrambe le cose, a seconda degli annunci disponibili e delle sue esigenze.", businessBody: "Attrezzature o beni adatti possono essere resi disponibili tramite annunci. Un’azienda che necessita di accesso temporaneo può esplorare lo stesso marketplace. Il modello di prenotazione è condiviso e non è un flusso separato solo per le aziende.", businessPoint1: "La registrazione aziendale include una fase di documentazione aziendale.", businessPoint2: "Esplora può filtrare gli annunci di aziende o privati.",
    categoriesEyebrow: "Cosa puoi noleggiare?", categoriesTitle: "Esplora le categorie usate oggi da SEVOR.", categoriesLead: "Il marketplace può mostrare annunci in queste categorie generali; la disponibilità effettiva dipende dagli annunci attuali.", categories: ["Veicoli", "Alloggi e soggiorni", "Elettronica", "Arredamento", "Abbigliamento", "Strumenti e attrezzature", "Altro"],
    trustEyebrow: "Costruito con pratici strumenti di fiducia", trustTitle: "Strumenti che supportano decisioni di noleggio informate.", trustLead: "SEVOR include meccanismi che aiutano gli utenti a documentare, comunicare in merito a e gestire i noleggi. Supportano il processo; non garantiscono alcun risultato.",
    trustCards: [
      { title: "Verifica di identità e azienda", body: "La piattaforma raccoglie documenti di verifica, tra cui carta d’identità, patente, passaporto e documentazione aziendale, con percorsi di revisione." },
      { title: "Registri di prenotazione", body: "Richieste, decisioni e passaggi relativi al noleggio vengono registrati nel flusso attuale." },
      { title: "Comunicazione sul noleggio", body: "La messaggistica collegata all’articolo aiuta i partecipanti idonei a comunicare in merito a un noleggio." },
      { title: "Percorsi di prova", body: "Esistono strumenti di prova per ritiro, restituzione e deposito quando il flusso di noleggio li richiede." },
      { title: "Recensioni e valutazioni", body: "Il feedback collegato alla prenotazione aiuta a comprendere esperienze precedenti senza garantire la qualità." },
      { title: "Supporto e segnalazioni", body: "Ticket di assistenza e percorsi per segnalare annunci sono disponibili tramite gli strumenti esistenti." }
    ],
    paymentsQuote: "Le prenotazioni online accettate utilizzano l’attuale flusso di pagamento PayPal.", paymentsBody: "I proprietari possono mantenere le preferenze di accredito per Interac, PayPal o Wise nelle attuali impostazioni dell’account. L’attuale flusso di accredito è manuale, quindi questa pagina non promette tempistiche, disponibilità o esito di un accredito.", paymentsPoint1: "Un importo di garanzia può applicarsi ad alcune prenotazioni.", paymentsPoint2: "Le prove relative al deposito e i percorsi di revisione si applicano ove pertinente.",
    visionEyebrow: "Accesso prima della proprietà", visionTitle: "Costruito con una visione flessibile e globale del noleggio.", visionLead: "SEVOR è progettato per rendere più flessibili, per persone e aziende, la scoperta dei noleggi e l’accesso. Quando un articolo adatto esiste già ed è reso disponibile, il noleggio temporaneo può essere un’alternativa all’acquisto di qualcosa di nuovo per alcuni usi.",
    visionCards: [
      { title: "Accedi a ciò che ti serve", body: "Trova accesso temporaneo quando un annuncio risponde a un’esigenza." },
      { title: "Usa di più ciò che esiste", body: "Beni adatti possono diventare utili quando i proprietari li rendono disponibili." },
      { title: "Amplia la scelta utile", body: "Annunci più pertinenti possono creare più opportunità di scoprire noleggi." }
    ],
    whyEyebrow: "Perché SEVOR?", whyTitle: "Un semplice ciclo di marketplace.", whyLead: "Nessun contatore né risultati garantiti — solo il rapporto pratico tra annunci utili e opportunità di noleggio.", flywheel: ["Vengono pubblicati più articoli utili", "Più scelta per chi noleggia", "Più noleggi completati possono creare più opportunità per i proprietari"],
    finalEyebrow: "Il tuo prossimo noleggio", finalTitle: "Pronto a noleggiare in modo diverso?", finalLead: "Esplora ciò che è disponibile ora oppure rendi disponibile un articolo adatto tramite un annuncio.", languageTitle: "Scegli la lingua della pagina Informazioni", languageLead: "La tua preferenza resta salvata per questa pagina quando torni.", footerNote: "SEVOR è un marketplace: la disponibilità dipende dagli annunci attuali.", privacyLink: "Centro privacy", backTop: "Torna su"
  });

  const translations = { en, fr, ar, hi, zh, es, pt, ru, de, it };

  const getPath = (source, path) => path.split(".").reduce((value, part) => (
    value === undefined || value === null ? undefined : value[part]
  ), source);
  const textKeys = [...root.querySelectorAll("[data-i18n]")].map((node) => node.dataset.i18n);
  const ariaKeys = [...root.querySelectorAll("[data-i18n-aria]")].map((node) => node.dataset.i18nAria);
  const requiredKeys = [...new Set([...textKeys, ...ariaKeys])];
  const missingKeys = (locale) => requiredKeys.filter((key) => typeof getPath(locale, key) !== "string");

  const setLanguage = (code, options = {}) => {
    const persist = options.persist !== false;
    const announce = options.announce !== false;
    const locale = translations[code] || translations.en;
    const actualCode = translations[code] ? code : "en";
    const shouldReduce = reducedMotion.matches;
    if (!shouldReduce) root.classList.add("is-translating");

    window.setTimeout(() => {
      root.dataset.language = actualCode;
      root.dir = locale.dir;
      document.documentElement.lang = locale.lang;
      document.documentElement.dir = locale.dir;
      document.title = locale.pageTitle;
      const description = document.querySelector('meta[name="description"]');
      if (description) description.content = locale.metaDescription;

      root.querySelectorAll("[data-i18n]").forEach((node) => {
        const value = getPath(locale, node.dataset.i18n);
        if (typeof value === "string") node.textContent = value;
      });
      root.querySelectorAll("[data-i18n-aria]").forEach((node) => {
        const value = getPath(locale, node.dataset.i18nAria);
        if (typeof value === "string") node.setAttribute("aria-label", value);
      });
      root.querySelectorAll(".about-language").forEach((button) => {
        button.setAttribute("aria-pressed", String(button.dataset.language === actualCode));
      });
      const status = root.querySelector("#about-language-status");
      if (status && announce) {
        status.textContent = locale.languageSelected.replace("{language}", locale.languageName);
      }
      if (persist) {
        try { window.localStorage.setItem(storageKey, actualCode); } catch (_) { /* Storage is optional. */ }
      }
      if (!shouldReduce) window.requestAnimationFrame(() => root.classList.remove("is-translating"));
    }, shouldReduce ? 0 : 75);
  };

  const activateTab = (name, focus = false) => {
    root.querySelectorAll("[data-about-tab]").forEach((tab) => {
      const selected = tab.dataset.aboutTab === name;
      tab.setAttribute("aria-selected", String(selected));
      tab.tabIndex = selected ? 0 : -1;
      if (selected && focus) tab.focus();
    });
    root.querySelectorAll("[data-about-panel]").forEach((panel) => {
      panel.hidden = panel.dataset.aboutPanel !== name;
    });
  };

  root.querySelectorAll("[data-about-tab]").forEach((tab) => {
    tab.addEventListener("click", () => activateTab(tab.dataset.aboutTab));
    tab.addEventListener("keydown", (event) => {
      const tabs = [...root.querySelectorAll("[data-about-tab]")];
      const index = tabs.indexOf(tab);
      let next = null;
      if (event.key === "ArrowRight" || event.key === "ArrowDown") next = (index + 1) % tabs.length;
      if (event.key === "ArrowLeft" || event.key === "ArrowUp") next = (index - 1 + tabs.length) % tabs.length;
      if (event.key === "Home") next = 0;
      if (event.key === "End") next = tabs.length - 1;
      if (next !== null) {
        event.preventDefault();
        activateTab(tabs[next].dataset.aboutTab, true);
      }
    });
  });

  root.querySelectorAll(".about-language").forEach((button) => {
    button.addEventListener("click", () => setLanguage(button.dataset.language));
  });

  const smoothBehavior = () => (reducedMotion.matches ? "auto" : "smooth");
  root.querySelectorAll('a[href^="#about-"]').forEach((link) => {
    link.addEventListener("click", (event) => {
      const target = document.querySelector(link.getAttribute("href"));
      if (!target) return;
      event.preventDefault();
      target.scrollIntoView({ behavior: smoothBehavior(), block: "start" });
      window.history.replaceState(null, "", link.getAttribute("href"));
    });
  });

  const backTop = root.querySelector("#about-back-top");
  if (backTop) {
    backTop.addEventListener("click", () => window.scrollTo({ top: 0, behavior: smoothBehavior() }));
  }

  let scrollQueued = false;
  const updateScrollUI = () => {
    scrollQueued = false;
    const fullHeight = document.documentElement.scrollHeight - window.innerHeight;
    const progress = fullHeight > 0 ? (window.scrollY / fullHeight) * 100 : 0;
    const progressBar = root.querySelector("#about-progress-bar");
    if (progressBar) progressBar.style.width = String(Math.max(0, Math.min(progress, 100))) + "%";
    if (backTop) {
      const visible = window.scrollY > Math.max(420, window.innerHeight * .7);
      backTop.classList.toggle("is-visible", visible);
      backTop.tabIndex = visible ? 0 : -1;
      backTop.setAttribute("aria-hidden", String(!visible));
    }
  };
  window.addEventListener("scroll", () => {
    if (!scrollQueued) {
      scrollQueued = true;
      window.requestAnimationFrame(updateScrollUI);
    }
  }, { passive: true });
  updateScrollUI();

  // Only opt into hidden-before-reveal styling after the rest of the page
  // has initialized, so a blocked or failing script cannot hide its content.
  root.classList.add("about-js-ready");
  const revealNodes = root.querySelectorAll("[data-about-reveal]");
  if (reducedMotion.matches || !("IntersectionObserver" in window)) {
    revealNodes.forEach((node) => node.classList.add("is-visible"));
  } else {
    const revealObserver = new IntersectionObserver((entries, observer) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: .08, rootMargin: "0px 0px -28px" });
    revealNodes.forEach((node) => revealObserver.observe(node));
  }

  const navLinks = [...root.querySelectorAll("[data-section-link]")];
  if ("IntersectionObserver" in window && navLinks.length) {
    const activeObserver = new IntersectionObserver((entries) => {
      const current = entries
        .filter((entry) => entry.isIntersecting)
        .sort((first, second) => second.intersectionRatio - first.intersectionRatio)[0];
      if (!current) return;
      navLinks.forEach((link) => link.classList.toggle("is-active", link.dataset.sectionLink === current.target.id));
    }, { rootMargin: "-18% 0px -68%", threshold: [0, .1, .3] });
    navLinks.forEach((link) => {
      const section = document.getElementById(link.dataset.sectionLink);
      if (section) activeObserver.observe(section);
    });
  }

  let preferred = "en";
  try {
    const stored = window.localStorage.getItem(storageKey);
    if (stored && translations[stored]) preferred = stored;
  } catch (_) { /* Storage is optional. */ }
  setLanguage(preferred, { persist: false, announce: false });

  // Test hook: no user data, only translation and interaction coverage.
  window.__sevorAboutCenter = {
    languages: () => Object.keys(translations),
    missing: () => Object.fromEntries(Object.entries(translations).map(([code, locale]) => [code, missingKeys(locale)])),
    setLanguage,
    activateTab,
    keys: () => ({ text: textKeys, aria: ariaKeys })
  };
})();
