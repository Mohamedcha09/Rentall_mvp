"""Central, data-driven listing taxonomy helpers.

The marketplace historically stores the first two hierarchy levels as the
human-readable ``Item.category`` and ``Item.subcategory`` values.  This module
keeps that compatibility and adds an optional third level for any category
whose subcategories define services.  It deliberately contains data and
presentation helpers only: routes still validate database ids server-side.

Keeping the catalog here prevents the create, edit, Explore and admin
templates from each carrying a divergent copy of the Digital Accounts list.
Future three-level categories can be added by extending ``CATEGORY_TREE``;
no route needs a category-specific branch.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


DIGITAL_ACCOUNTS_CATEGORY = "Digital Accounts"
OTHER_VALUE = "Other"


# Values are canonical database values.  Brand and service names are left in
# their established spelling; only user-interface labels are localized below.
DIGITAL_ACCOUNTS_SERVICES: dict[str, tuple[str, ...]] = {
    "Movies & Streaming": (
        "Netflix", "Amazon Prime Video", "Disney+", "Apple TV+", "Max", "Hulu",
        "Paramount+", "Peacock", "STARZ", "SHOWTIME", "AMC+", "Discovery+", "Crave",
        "Canal+", "OCS", "Molotov", "BritBox", "Acorn TV", "MUBI", "Criterion Channel",
        "Rakuten TV", "Plex Pass", "YouTube Premium", "Crunchyroll", "HIDIVE", "Shahid",
        "OSN+", "TOD", "STARZPLAY", "Viaplay", "NOW", "Sky Go", "Sky services",
        "ITVX Premium", "BBC-related paid services", "Stan", "Binge", "Kayo-related bundles",
        "Paramount regional services", OTHER_VALUE,
    ),
    "Sports": (
        "beIN Sports", "DAZN", "ESPN+", "Fubo", "YouTube TV sports packages",
        "Sling sports packages", "Canal+ Sport", "RMC Sport", "Eurosport", "TNT Sports",
        "Sky Sports", "NOW Sports", "TSN+", "Sportsnet+", "TVA Sports-related services",
        "MLS Season Pass", "NBA League Pass", "NFL Game Pass", "MLB.TV", "NHL services",
        "UFC Fight Pass", "WWE-related streaming", "F1 TV", "MotoGP VideoPass", "Tennis TV",
        "ATP/WTA-related streaming services", "FloSports", "Peacock Sports", "Paramount+ Sports",
        "TOD Sports", OTHER_VALUE,
    ),
    "Gaming": (
        "PlayStation Network", "PlayStation Plus Essential", "PlayStation Plus Extra",
        "PlayStation Plus Premium", "Xbox", "Xbox Game Pass Core", "Xbox Game Pass Standard",
        "PC Game Pass", "Xbox Game Pass Ultimate", "Nintendo Switch Online",
        "Nintendo Switch Online + Expansion Pack", "Steam", "Epic Games", "EA Play", "EA Play Pro",
        "Ubisoft+", "Battle.net", "Riot Games", "Rockstar Games", "Minecraft", "Roblox", "Fortnite",
        "GeForce NOW", "Amazon Luna", "Boosteroid", "Shadow PC", "Apple Arcade", "Google Play Pass",
        "Meta Quest services", OTHER_VALUE,
    ),
    "Music & Audio": (
        "Spotify Premium", "Apple Music", "Amazon Music Unlimited", "YouTube Music Premium", "Deezer",
        "Tidal", "SoundCloud Go+", "Anghami", "Qobuz", "Pandora", "iHeartRadio services", "SiriusXM",
        "Audible", "Storytel", "Pocket Casts Plus", OTHER_VALUE,
    ),
    "AI Tools": (
        "ChatGPT", "Claude", "Gemini", "Perplexity", "Microsoft Copilot", "GitHub Copilot", "Midjourney",
        "Leonardo AI", "Runway", "Pika", "Kling AI", "Luma", "ElevenLabs", "Suno", "Udio", "Synthesia",
        "HeyGen", "Character.AI", "Poe", "Cursor", "Replit", "Notion AI", "Canva AI", "Adobe Firefly",
        "Grammarly AI", "Jasper", "Copy.ai", "Writesonic", "DeepL Pro", OTHER_VALUE,
    ),
    "Software & Productivity": (
        "Microsoft 365", "Google Workspace", "Adobe Creative Cloud", "Canva Pro", "Notion", "Slack", "Zoom",
        "Dropbox", "OneDrive", "iCloud+", "Google One", "Evernote", "Grammarly", "Todoist", "ClickUp",
        "Monday.com", "Asana", "Trello", "Airtable", "Calendly", "DocuSign", "Dropbox Sign", "Office apps",
        "PDF editors", "Antivirus software", "Security software", OTHER_VALUE,
    ),
    "Design / Photo / Video": (
        "Adobe Photoshop", "Adobe Illustrator", "Adobe Lightroom", "Adobe Premiere Pro", "Adobe After Effects",
        "Adobe Acrobat Pro", "Canva Pro", "Figma Professional", "CapCut Pro", "Filmora", "Envato Elements",
        "Motion Array", "Storyblocks", "Freepik Premium", "Shutterstock subscriptions", "Adobe Stock",
        "Epidemic Sound", "Artlist", "VSCO", "Picsart", "Placeit", "Creative Market memberships", OTHER_VALUE,
    ),
    "Cloud & Storage": (
        "Google One", "iCloud+", "Microsoft OneDrive", "Dropbox", "Box", "MEGA", "pCloud", "Proton Drive",
        "Sync.com", "IDrive", "Backblaze", OTHER_VALUE,
    ),
    "Education": (
        "Coursera Plus", "Udemy subscriptions", "Skillshare", "MasterClass", "LinkedIn Learning", "Pluralsight",
        "Codecademy", "DataCamp", "Brilliant", "Duolingo Super", "Duolingo Max", "Babbel", "Busuu",
        "Rosetta Stone", "Quizlet Plus", "Chegg", "Study.com", "Khan-related paid offerings if applicable", OTHER_VALUE,
    ),
    "News & Reading": (
        "Kindle Unlimited", "Audible", "Everand", "Kobo Plus", "Blinkist", "Medium", "The New York Times",
        "Wall Street Journal", "Financial Times", "Bloomberg", "The Economist", "Washington Post", "Le Monde",
        "Le Figaro", "The Athletic", "Readly", "PressReader", OTHER_VALUE,
    ),
    "Social & Creator": (
        "X Premium", "Snapchat+", "Telegram Premium", "Discord Nitro", "LinkedIn Premium", "Twitch subscriptions",
        "Twitch Turbo", "Patreon memberships", "YouTube Premium", "YouTube channel memberships", "vidIQ",
        "TubeBuddy", "StreamYard", "Restream", "Later", "Buffer", "Hootsuite", OTHER_VALUE,
    ),
    "Business & Marketing": (
        "Shopify", "Wix", "Squarespace", "Webflow", "Framer", "WordPress paid services", "HubSpot", "Salesforce",
        "Zendesk", "Intercom", "Mailchimp", "Brevo", "Semrush", "Ahrefs", "Moz", "Ubersuggest", "Similarweb",
        "QuickBooks", "Xero", "FreshBooks", OTHER_VALUE,
    ),
    "Hosting & Developer": (
        "GitHub", "GitLab", "JetBrains", "Replit", "Vercel", "Render", "Netlify", "DigitalOcean", "AWS",
        "Microsoft Azure", "Google Cloud", "Cloudflare", "Hostinger", "GoDaddy", "Namecheap", "Heroku", "Railway",
        "Supabase", "Firebase paid plans", OTHER_VALUE,
    ),
    "VPN & Security": (
        "NordVPN", "ExpressVPN", "Surfshark", "Proton VPN", "CyberGhost", "Private Internet Access", "Mullvad",
        "Norton", "McAfee", "Bitdefender", "Malwarebytes", "Kaspersky where legally available", "1Password",
        "Dashlane", "Proton Pass", OTHER_VALUE,
    ),
    "Regional TV & Entertainment": (
        "Canal+", "beIN", "Shahid", "OSN+", "TOD", "Crave", "Molotov", "NOW", "Sky", "Viaplay", "Stan",
        "Binge", "Kayo", "Hotstar", "JioHotstar", "ZEE5", "SonyLIV", "Viki Pass", "iQIYI", "WeTV", OTHER_VALUE,
    ),
    # Amazon Prime itself is intentionally separate from Prime Video, Music,
    # Luna, Audible, and Kindle Unlimited, which belong to their own types.
    "General": ("Amazon Prime", OTHER_VALUE),
    OTHER_VALUE: (OTHER_VALUE,),
}


# A general tree, intentionally not a series of ``if category == ...`` checks
# in route handlers.  Additional three-level categories can be registered in
# the same structure later.
CATEGORY_TREE: dict[str, dict[str, tuple[str, ...]]] = {
    DIGITAL_ACCOUNTS_CATEGORY: DIGITAL_ACCOUNTS_SERVICES,
}


@dataclass(frozen=True)
class TaxonomyDisplayChoice:
    """A configured browse choice which has no legacy lookup row yet.

    It is deliberately presentation-only: create and edit keep validating
    submitted database ids.  This lets Explore show a configured category
    before it has an approved listing, without doing a write during a GET.
    """

    name: str


def _choice_name(row: Any) -> str:
    return str(getattr(row, "name", "") or "").strip()


def explore_category_choices(database_categories: Iterable[Any]) -> list[Any]:
    """Keep persisted choices and append any configured browse branches.

    The configured names come from the same tree that supplies level three;
    nothing is hard-coded in an Explore template.  Existing rows retain their
    order and identity, while an unseeded configured category remains visible
    and selectable for browse-only filtering.
    """

    rows = list(database_categories)
    known = {_choice_name(row).casefold() for row in rows if _choice_name(row)}
    for name in CATEGORY_TREE:
        if name.casefold() not in known:
            rows.append(TaxonomyDisplayChoice(name=name))
    return rows


def explore_subcategory_choices(category_name: str | None, database_subcategories: Iterable[Any]) -> list[Any]:
    """Expose configured level-two browse choices without inventing DB ids."""

    rows = list(database_subcategories)
    known = {_choice_name(row).casefold() for row in rows if _choice_name(row)}
    for name in CATEGORY_TREE.get(str(category_name or ""), {}):
        if name.casefold() not in known:
            rows.append(TaxonomyDisplayChoice(name=name))
    return rows

# Presentation names are data too.  Routes only ask whether a branch has a
# third level; they never special-case Digital Accounts.  A future configured
# category gets neutral Type/Service labels unless it supplies a clearer pair.
CATEGORY_LEVEL_PRESENTATION: dict[str, dict[str, str]] = {
    DIGITAL_ACCOUNTS_CATEGORY: {
        "level2": "digital_type",
        "level3": "service_platform",
    },
}


_COPY: dict[str, dict[str, str]] = {
    "en": {
        "category": "Category",
        "subcategory": "Subcategory",
        "type": "Type",
        "digital_type": "Digital Type",
        "service": "Service",
        "service_platform": "Service / Platform",
        "custom_service": "Custom Service Name",
        "select_category": "Select category",
        "select_category_first": "Select a category first",
        "select_subcategory": "Select subcategory",
        "select_type": "Select type",
        "select_digital_type": "Select digital type",
        "select_service": "Select service / platform",
        "select_type_first": "Select a digital type first",
        "select_level2_first": "Select a type first",
        "no_subcategories": "No subcategories available",
        "subcategory_help": "Available after you choose a category.",
        "service_help": "Choose the service or platform for this type.",
        "custom_service_help": "Required only when you choose Other.",
        "pending_review": "Pending Review",
        "no_selection": "No selection",
        "pending_items_review": "Pending Items Review",
        "pending_items_lead": "Review newly submitted listings before they become visible on SEVOR.",
        "pending_count": "Pending",
        "no_pending_items": "There are no pending listings to review.",
        "owner": "Owner",
        "unknown": "Unknown",
        "email": "Email",
        "user_id": "User ID",
        "account_type": "Account type",
        "location": "Location",
        "price": "Price",
        "per_day": "/ day",
        "listing_category_hierarchy": "Listing category hierarchy",
        "image": "image",
        "created": "Created",
        "description": "Description",
        "images": "Images",
        "no_images": "No images added.",
        "approve": "Approve",
        "delete": "Delete",
        "feedback": "Feedback",
        "send_feedback": "Send feedback",
        "cancel": "Cancel",
        "delete_confirm": "Are you sure you want to delete this listing?",
    },
    "fr": {
        "category": "Catégorie",
        "subcategory": "Sous-catégorie",
        "type": "Type",
        "digital_type": "Type numérique",
        "service": "Service",
        "service_platform": "Service / plateforme",
        "custom_service": "Nom du service personnalisé",
        "select_category": "Sélectionnez une catégorie",
        "select_category_first": "Sélectionnez d’abord une catégorie",
        "select_subcategory": "Sélectionnez une sous-catégorie",
        "select_type": "Sélectionnez un type",
        "select_digital_type": "Sélectionnez un type numérique",
        "select_service": "Sélectionnez un service / une plateforme",
        "select_type_first": "Sélectionnez d’abord un type numérique",
        "select_level2_first": "Sélectionnez d’abord un type",
        "no_subcategories": "Aucune sous-catégorie disponible",
        "subcategory_help": "Disponible après avoir choisi une catégorie.",
        "service_help": "Choisissez le service ou la plateforme pour ce type.",
        "custom_service_help": "Requis uniquement après avoir choisi Autre.",
        "pending_review": "En attente de révision",
        "no_selection": "Aucune sélection",
        "pending_items_review": "Révision des annonces en attente",
        "pending_items_lead": "Examinez les nouvelles annonces avant qu’elles deviennent visibles sur SEVOR.",
        "pending_count": "En attente",
        "no_pending_items": "Aucune annonce en attente de révision.",
        "owner": "Propriétaire",
        "unknown": "Inconnu",
        "email": "E-mail",
        "user_id": "ID utilisateur",
        "account_type": "Type de compte",
        "location": "Lieu",
        "price": "Prix",
        "per_day": "/ jour",
        "listing_category_hierarchy": "Hiérarchie des catégories de l’annonce",
        "image": "image",
        "created": "Créée le",
        "description": "Description",
        "images": "Images",
        "no_images": "Aucune image ajoutée.",
        "approve": "Approuver",
        "delete": "Supprimer",
        "feedback": "Retour",
        "send_feedback": "Envoyer le retour",
        "cancel": "Annuler",
        "delete_confirm": "Voulez-vous vraiment supprimer cette annonce ?",
    },
    "ar": {
        "category": "الفئة",
        "subcategory": "الفئة الفرعية",
        "type": "النوع",
        "digital_type": "النوع الرقمي",
        "service": "الخدمة",
        "service_platform": "الخدمة / المنصة",
        "custom_service": "اسم خدمة مخصصة",
        "select_category": "اختر الفئة",
        "select_category_first": "اختر فئة أولًا",
        "select_subcategory": "اختر الفئة الفرعية",
        "select_type": "اختر النوع",
        "select_digital_type": "اختر النوع الرقمي",
        "select_service": "اختر الخدمة / المنصة",
        "select_type_first": "اختر النوع الرقمي أولًا",
        "select_level2_first": "اختر النوع أولًا",
        "no_subcategories": "لا توجد فئات فرعية متاحة",
        "subcategory_help": "يتاح بعد اختيار الفئة.",
        "service_help": "اختر الخدمة أو المنصة لهذا النوع.",
        "custom_service_help": "مطلوب فقط عند اختيار «أخرى».",
        "pending_review": "قيد المراجعة",
        "no_selection": "لا يوجد اختيار",
        "pending_items_review": "مراجعة الإعلانات المعلّقة",
        "pending_items_lead": "راجع الإعلانات المرسلة حديثًا قبل أن تصبح ظاهرة على SEVOR.",
        "pending_count": "معلّق",
        "no_pending_items": "لا توجد إعلانات معلّقة للمراجعة.",
        "owner": "المالك",
        "unknown": "غير معروف",
        "email": "البريد الإلكتروني",
        "user_id": "معرّف المستخدم",
        "account_type": "نوع الحساب",
        "location": "الموقع",
        "price": "السعر",
        "per_day": "/ يوم",
        "listing_category_hierarchy": "تسلسل فئة الإعلان",
        "image": "صورة",
        "created": "تاريخ الإنشاء",
        "description": "الوصف",
        "images": "الصور",
        "no_images": "لم تتم إضافة صور.",
        "approve": "قبول",
        "delete": "حذف",
        "feedback": "ملاحظة",
        "send_feedback": "إرسال الملاحظة",
        "cancel": "إلغاء",
        "delete_confirm": "هل أنت متأكد من حذف هذا الإعلان؟",
    },
}


_VALUE_LABELS: dict[str, dict[str, str]] = {
    DIGITAL_ACCOUNTS_CATEGORY: {
        "en": "Digital Accounts",
        "fr": "Comptes numériques",
        "ar": "الحسابات الرقمية",
    },
    OTHER_VALUE: {
        "en": "Other",
        "fr": "Autre",
        "ar": "أخرى",
    },
}


def normalize_language(value: str | None) -> str:
    language = str(value or "en").lower().split("-", 1)[0]
    return language if language in _COPY else "en"


def ui_copy(key: str, language: str | None = None) -> str:
    language = normalize_language(language)
    return _COPY[language].get(key, _COPY["en"].get(key, key))


def taxonomy_label(value: Any, language: str | None = None) -> str:
    """Return a translated display label without changing canonical DB data."""
    raw = str(value or "").strip()
    if not raw:
        return ""
    language = normalize_language(language)
    return _VALUE_LABELS.get(raw, {}).get(language, raw)


def category_level_labels(category_name: str | None, language: str | None = None) -> dict[str, str]:
    """UI labels for generic versus configured three-level categories."""
    category_name = str(category_name or "")
    configured = CATEGORY_TREE.get(category_name, {})
    presentation = CATEGORY_LEVEL_PRESENTATION.get(category_name, {})
    return {
        "level2": ui_copy(presentation.get("level2", "type") if configured else "subcategory", language),
        "level3": ui_copy(presentation.get("level3", "service"), language),
        "custom_level3": ui_copy("custom_service", language),
    }


def category_level2_placeholder(category_name: str | None, language: str | None = None) -> str:
    """Return a data-driven second-level prompt for every category shape."""
    category_name = str(category_name or "")
    if category_name not in CATEGORY_TREE:
        return ui_copy("select_subcategory", language)
    presentation = CATEGORY_LEVEL_PRESENTATION.get(category_name, {})
    key = "select_digital_type" if presentation.get("level2") == "digital_type" else "select_type"
    return ui_copy(key, language)


def category_level3_placeholder(category_name: str | None, language: str | None = None) -> str:
    """Return the progressive-disclosure hint without assuming Digital Accounts."""
    presentation = CATEGORY_LEVEL_PRESENTATION.get(str(category_name or ""), {})
    key = "select_type_first" if presentation.get("level2") == "digital_type" else "select_level2_first"
    return ui_copy(key, language)


def catalog_tree_payload(categories: Iterable[Any], subcategories: Iterable[Any], language: str | None = None) -> dict[str, Any]:
    """Build the small, server-produced form payload used by create/edit JS.

    The payload is based on database ids rather than names supplied by a
    browser.  It supports any future category with level-three rows.
    """
    language = normalize_language(language)
    category_rows = list(categories)
    category_names = {
        int(getattr(category, "id", 0) or 0): str(getattr(category, "name", "") or "")
        for category in category_rows
    }
    subs_by_category: dict[int, list[dict[str, Any]]] = {}
    for sub in subcategories:
        category_id = int(getattr(sub, "category_id", 0) or 0)
        if not category_id:
            continue
        sub_id = int(getattr(sub, "id", 0) or 0)
        category_name = category_names.get(category_id, "")
        # The config is keyed by the canonical Category/Subcategory names.  We
        # attach the level-three options only when that pair has them, so all
        # ordinary database categories remain strictly two-level.
        configured_third_levels = CATEGORY_TREE.get(category_name, {}).get(
            str(getattr(sub, "name", "") or ""),
            (),
        )
        subs_by_category.setdefault(category_id, []).append(
            {
                "id": sub_id,
                "name": str(getattr(sub, "name", "") or ""),
                "label": taxonomy_label(getattr(sub, "name", ""), language),
                "third_levels": [
                    {"name": value, "label": taxonomy_label(value, language)}
                    for value in configured_third_levels
                ],
            }
        )

    payload_categories: list[dict[str, Any]] = []
    for category in category_rows:
        category_id = int(getattr(category, "id", 0) or 0)
        name = str(getattr(category, "name", "") or "")
        payload_categories.append(
            {
                "id": category_id,
                "name": name,
                "label": taxonomy_label(name, language),
                "level_labels": category_level_labels(name, language),
                "level2_placeholder": category_level2_placeholder(name, language),
                "level3_placeholder": category_level3_placeholder(name, language),
                "subcategories": subs_by_category.get(category_id, []),
            }
        )
    # ``labels`` avoids the special ``dict.copy`` attribute in Jinja templates.
    return {"categories": payload_categories, "labels": _COPY[language]}


def third_level_display(item: Any) -> str:
    """Use the custom value only for an explicit Other service."""
    third = str(getattr(item, "third_level", "") or "").strip()
    custom = str(getattr(item, "custom_third_level", "") or "").strip()
    return custom if third == OTHER_VALUE and custom else third


def hierarchy_values(item: Any) -> list[str]:
    """Non-empty hierarchy values, safe for legacy two-level rows."""
    values = [
        str(getattr(item, "category", "") or "").strip(),
        str(getattr(item, "subcategory", "") or "").strip(),
        third_level_display(item),
    ]
    return [value for value in values if value]


def listing_hierarchy(item: Any, language: str | None = None) -> list[dict[str, str]]:
    """Return safe, translated hierarchy chips for legacy and new listings."""
    category = str(getattr(item, "category", "") or "").strip()
    subcategory = str(getattr(item, "subcategory", "") or "").strip()
    third = third_level_display(item)
    labels = category_level_labels(category, language)
    rows: list[dict[str, str]] = []
    if category:
        rows.append({"kind": ui_copy("category", language), "value": taxonomy_label(category, language)})
    if subcategory:
        rows.append({"kind": labels["level2"], "value": taxonomy_label(subcategory, language)})
    if third:
        rows.append({"kind": labels["level3"], "value": taxonomy_label(third, language)})
    return rows


class TaxonomyValidationError(ValueError):
    """Raised for a forged, stale, or incomplete listing taxonomy payload."""


def resolve_listing_hierarchy(
    db: Any,
    *,
    category_name: str | None,
    subcategory_id: int | str | None,
    third_level: str | None = None,
    custom_third_level: str | None = None,
) -> dict[str, str | None]:
    """Resolve and validate the selected category hierarchy on the server.

    A browser can submit arbitrary ids/names, so each child is checked against
    its actual parent.  A generic level-three field is allowed only for a
    configured branch, and a free text value is accepted only after the
    explicit ``Other`` choice.  The returned canonical values are ready to be
    persisted on ``Item``.
    """
    # Imported lazily so Alembic can import the central data module without
    # loading application models while rendering an offline migration.
    from .models import Category, Subcategory

    category_name = str(category_name or "").strip()
    if not category_name:
        raise TaxonomyValidationError("Choose a valid category.")
    category = db.query(Category).filter(Category.name == category_name).first()
    if category is None:
        raise TaxonomyValidationError("The selected category is not available.")

    try:
        subcategory_id_int = int(subcategory_id) if subcategory_id not in (None, "") else None
    except (TypeError, ValueError):
        raise TaxonomyValidationError("Choose a valid subcategory.")

    subcategory = None
    if subcategory_id_int is not None:
        subcategory = (
            db.query(Subcategory)
            .filter(Subcategory.id == subcategory_id_int, Subcategory.category_id == category.id)
            .first()
        )
        if subcategory is None:
            raise TaxonomyValidationError("The selected subcategory does not belong to this category.")

    available_subcategories = db.query(Subcategory.id).filter(Subcategory.category_id == category.id).first()
    if available_subcategories is not None and subcategory is None:
        raise TaxonomyValidationError("Choose a valid subcategory.")

    canonical_subcategory = str(getattr(subcategory, "name", "") or "").strip() or None
    valid_third_levels = CATEGORY_TREE.get(category_name, {}).get(canonical_subcategory or "", ())
    submitted_third = str(third_level or "").strip()
    submitted_custom = str(custom_third_level or "").strip()

    if not valid_third_levels:
        if submitted_third or submitted_custom:
            raise TaxonomyValidationError("This category does not use a service level.")
        return {
            "category": category_name,
            "subcategory": canonical_subcategory,
            "third_level": None,
            "custom_third_level": None,
        }

    if submitted_third not in valid_third_levels:
        raise TaxonomyValidationError("Choose a valid service for the selected type.")
    if submitted_third == OTHER_VALUE:
        if not submitted_custom:
            raise TaxonomyValidationError("Enter the custom service name.")
        if len(submitted_custom) > 200:
            raise TaxonomyValidationError("The custom service name is too long.")
    elif submitted_custom:
        raise TaxonomyValidationError("A custom service name is allowed only after choosing Other.")

    return {
        "category": category_name,
        "subcategory": canonical_subcategory,
        "third_level": submitted_third,
        "custom_third_level": submitted_custom if submitted_third == OTHER_VALUE else None,
    }


def configured_catalog_rows() -> Iterable[tuple[str, str, str]]:
    """Yield category, subcategory and optional third level from central data."""
    for category, second_levels in CATEGORY_TREE.items():
        for subcategory, third_levels in second_levels.items():
            for third_level in third_levels:
                yield category, subcategory, third_level
