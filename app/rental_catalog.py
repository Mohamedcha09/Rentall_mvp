"""Curated, multilingual rental taxonomy definitions.

This module is deliberately data-only.  ``catalog_taxonomy`` turns these
definitions into the runtime validation and presentation helpers used by the
marketplace.  L1/L2 rows remain persisted lookup records; this file describes
the canonical additive catalog which a migration can seed into an isolated or
operator-approved database.

The structure has a maximum of three levels:

    category -> subcategory -> optional equipment/type

It does not encode attributes such as colour, model year, capacity, fuel, or
whether an operator is included.  Those are cross-cutting listing attributes,
not mutually-exclusive taxonomy children.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .rental_research_aliases import RESEARCH_PATH_ALIASES


@dataclass(frozen=True)
class CatalogValue:
    """One stable canonical value with display labels in supported languages."""

    canonical: str
    french: str
    arabic: str

    def labels(self) -> dict[str, str]:
        return {"en": self.canonical, "fr": self.french, "ar": self.arabic}


@dataclass(frozen=True)
class CatalogBranch:
    """A persisted L2 value and its optional in-code L3 choices."""

    value: CatalogValue
    third_levels: tuple[CatalogValue, ...] = ()


@dataclass(frozen=True)
class CatalogCategory:
    """A canonical L1 value, compatibility aliases, and its branches."""

    value: CatalogValue
    branches: tuple[CatalogBranch, ...]
    aliases: tuple[str, ...] = ()
    presentation: tuple[tuple[str, str], ...] = ()


def v(canonical: str, french: str, arabic: str) -> CatalogValue:
    return CatalogValue(canonical, french, arabic)


def b(value: CatalogValue, *third_levels: CatalogValue) -> CatalogBranch:
    return CatalogBranch(value, tuple(third_levels))


def c(
    value: CatalogValue,
    *branches: CatalogBranch,
    aliases: tuple[str, ...] = (),
    presentation: tuple[tuple[str, str], ...] = (),
) -> CatalogCategory:
    return CatalogCategory(value, tuple(branches), aliases, presentation)


OTHER = v("Other", "Autre", "أخرى")


def choices(*values: CatalogValue) -> tuple[CatalogValue, ...]:
    """Add the explicit, parent-scoped Other option to a real L3 branch."""
    return tuple(values) + (OTHER,)


VEHICLE_PRESENTATION = (
    ("level2", "vehicle_group"),
    ("level3", "vehicle_type"),
    ("custom_level3", "custom_vehicle_type"),
)
EQUIPMENT_PRESENTATION = (
    ("level2", "equipment_group"),
    ("level3", "equipment_type"),
    ("custom_level3", "custom_equipment_type"),
)
SPACE_PRESENTATION = (
    ("level2", "space_group"),
    ("level3", "space_type"),
    ("custom_level3", "custom_space_type"),
)
ITEM_PRESENTATION = (
    ("level2", "rental_group"),
    ("level3", "item_type"),
    ("custom_level3", "custom_item_type"),
)


# The active catalog intentionally excludes aviation, crewed charter, and
# regulated medical-device branches.  Those are documented as gated proposals
# in the audit report rather than being presented as ordinary self-service
# listings before compliance and insurance requirements exist.
RENTAL_CATEGORIES: tuple[CatalogCategory, ...] = (
    c(
        v("Vehicles", "Véhicules", "المركبات"),
        b(v("Cars", "Voitures", "السيارات"), *choices(
            v("Economy Cars", "Voitures économiques", "سيارات اقتصادية"),
            v("Compact Cars", "Voitures compactes", "سيارات مدمجة"),
            v("Sedans", "Berlines", "سيارات سيدان"),
            v("SUVs", "VUS", "سيارات دفع رباعي"),
            v("Coupes", "Coupés", "سيارات كوبيه"),
            v("Convertibles", "Cabriolets", "سيارات مكشوفة"),
            v("Luxury Cars", "Voitures de luxe", "سيارات فاخرة"),
            v("Sports Cars", "Voitures sportives", "سيارات رياضية"),
            v("Classic Cars", "Voitures classiques", "سيارات كلاسيكية"),
            v("Limousines / Stretch Cars", "Limousines / voitures allongées", "ليموزين / سيارات طويلة"),
        )),
        b(v("Buses", "Autobus", "الحافلات"), *choices(
            v("School Buses", "Autobus scolaires", "حافلات مدرسية"),
            v("City / Transit Buses", "Autobus urbains / de transport", "حافلات مدينة / نقل عام"),
            v("Shuttle Buses", "Navettes", "حافلات نقل مكوكية"),
            v("Minibuses", "Minibus", "حافلات صغيرة"),
            v("Coach / Tour Buses", "Autocars de tourisme", "حافلات سياحية"),
            v("Party Buses", "Autobus festifs", "حافلات حفلات"),
        )),
        b(v("Trucks & Vans", "Camions et fourgonnettes", "الشاحنات والفانات"), *choices(
            v("Pickup Trucks", "Camionnettes", "شاحنات بيك أب"),
            v("Cargo Vans", "Fourgonnettes cargo", "فانات شحن"),
            v("Passenger Vans", "Fourgonnettes de passagers", "فانات ركاب"),
            v("Box Trucks", "Camions cubes", "شاحنات صندوقية"),
            v("Refrigerated Trucks", "Camions frigorifiques", "شاحنات مبردة"),
            v("Dump Trucks", "Camions-bennes", "شاحنات قلابة"),
        )),
        b(v("Trailers & RVs", "Remorques et VR", "المقطورات والمركبات الترفيهية"), *choices(
            v("Utility Trailers", "Remorques utilitaires", "مقطورات متعددة الاستخدام"),
            v("Cargo Trailers", "Remorques cargo", "مقطورات شحن"),
            v("Car Haulers", "Remorques porte-voitures", "مقطورات نقل سيارات"),
            v("Travel Trailers", "Roulottes", "مقطورات سفر"),
            v("Campervans", "Fourgons aménagés", "فانات تخييم"),
            v("Motorhomes", "Autocaravanes", "بيوت متنقلة"),
        )),
        b(v("Bicycles & Micro-mobility", "Vélos et micromobilité", "الدراجات والتنقل الخفيف"), *choices(
            v("Road Bikes", "Vélos de route", "دراجات طريق"),
            v("Mountain Bikes", "Vélos de montagne", "دراجات جبلية"),
            v("E-Bikes", "Vélos électriques", "دراجات كهربائية"),
            v("Cargo Bikes", "Vélos-cargos", "دراجات شحن"),
            v("E-Scooters", "Trottinettes électriques", "سكوترات كهربائية"),
        )),
        b(v("Motorcycles & Scooters", "Motos et scooters", "الدراجات النارية والسكوترات"), *choices(
            v("Motorcycles", "Motocyclettes", "دراجات نارية"),
            v("Scooters", "Scooters", "سكوترات"),
            v("Mopeds", "Cyclomoteurs", "دراجات بخارية خفيفة"),
        )),
        aliases=("vehicle",),
        presentation=VEHICLE_PRESENTATION,
    ),
    c(
        v("Housing & Stays", "Logements et séjours", "السكن والإقامات"),
        b(v("Apartments & Homes", "Appartements et maisons", "شقق ومنازل")),
        b(v("Vacation Properties", "Propriétés de vacances", "عقارات للإجازات")),
        b(v("Rooms & Shared Stays", "Chambres et séjours partagés", "غرف وإقامات مشتركة")),
        b(v("Parking & Storage", "Stationnement et entreposage", "مواقف وتخزين")),
        aliases=("housing",),
        presentation=SPACE_PRESENTATION,
    ),
    c(
        v("Electronics", "Électronique", "الإلكترونيات"),
        b(v("Computers & Tablets", "Ordinateurs et tablettes", "الحواسيب والأجهزة اللوحية"), *choices(
            v("Laptops", "Ordinateurs portables", "حواسيب محمولة"),
            v("Desktop Computers", "Ordinateurs de bureau", "حواسيب مكتبية"),
            v("Tablets", "Tablettes", "أجهزة لوحية"),
            v("Monitors", "Moniteurs", "شاشات"),
        )),
        b(v("Cameras & Video", "Caméras et vidéo", "الكاميرات والفيديو"), *choices(
            v("DSLR / Mirrorless Cameras", "Appareils reflex / hybrides", "كاميرات DSLR / بدون مرآة"),
            v("Cinema Cameras", "Caméras de cinéma", "كاميرات سينمائية"),
            v("Lenses", "Objectifs", "عدسات"),
            v("Tripods & Stabilizers", "Trépieds et stabilisateurs", "حوامل ثلاثية ومثبتات"),
        )),
        b(v("Networking & Communications", "Réseaux et communications", "الشبكات والاتصالات"), *choices(
            v("Wi-Fi Kits", "Kits Wi-Fi", "أطقم واي فاي"),
            v("Routers & Switches", "Routeurs et commutateurs", "أجهزة توجيه ومحولات"),
            v("Walkie-Talkies", "Talkies-walkies", "أجهزة اتصال لاسلكي"),
            v("Satellite Phones", "Téléphones satellites", "هواتف فضائية"),
        )),
        b(v("Office Tech", "Technologie de bureau", "تقنية المكاتب"), *choices(
            v("Projectors", "Projecteurs", "أجهزة عرض"),
            v("Projection Screens", "Écrans de projection", "شاشات عرض"),
            v("Printers & Scanners", "Imprimantes et numériseurs", "طابعات وماسحات ضوئية"),
        )),
        b(v("Gaming & VR", "Jeux vidéo et RV", "الألعاب والواقع الافتراضي"), *choices(
            v("Game Consoles", "Consoles de jeux", "أجهزة ألعاب"),
            v("VR Headsets", "Casques de RV", "نظارات واقع افتراضي"),
            v("Racing Simulators", "Simulateurs de course", "محاكيات سباق"),
        )),
        aliases=("electronics",),
        presentation=EQUIPMENT_PRESENTATION,
    ),
    c(
        v("Furniture", "Mobilier", "الأثاث"),
        b(v("Home Furniture", "Mobilier résidentiel", "أثاث منزلي")),
        b(v("Office Furniture", "Mobilier de bureau", "أثاث مكتبي")),
        b(v("Event Furniture", "Mobilier événementiel", "أثاث مناسبات")),
        b(v("Appliances", "Électroménagers", "أجهزة منزلية")),
        b(v("Rugs & Decor", "Tapis et décoration", "سجاد وديكور")),
        aliases=("furniture",),
        presentation=ITEM_PRESENTATION,
    ),
    c(
        v("Clothing & Costumes", "Vêtements et costumes", "الملابس والأزياء التنكرية"),
        b(v("Formal & Bridal", "Tenues de cérémonie et mariage", "ملابس رسمية وزفاف"), *choices(
            v("Wedding Dresses", "Robes de mariée", "فساتين زفاف"),
            v("Suits & Tuxedos", "Costumes et smokings", "بدلات وتوكسيدو"),
            v("Evening Wear", "Tenues de soirée", "ملابس سهرة"),
        )),
        b(v("Costumes & Theatrical", "Costumes et théâtre", "أزياء تنكرية ومسرحية"), *choices(
            v("Character Costumes", "Costumes de personnages", "أزياء شخصيات"),
            v("Period Costumes", "Costumes d'époque", "أزياء تاريخية"),
            v("Stage Costumes", "Costumes de scène", "أزياء مسرحية"),
        )),
        b(v("Outdoor & Specialty", "Plein air et spécialisé", "ملابس خارجية ومتخصصة")),
        b(v("Accessories", "Accessoires", "إكسسوارات")),
        aliases=("clothing",),
        presentation=ITEM_PRESENTATION,
    ),
    c(
        v("Tools & Equipment", "Outils et équipement", "الأدوات والمعدات"),
        b(v("Power Tools", "Outils électriques", "أدوات كهربائية"), *choices(
            v("Drills & Drivers", "Perceuses et visseuses", "مثاقب ومفكات كهربائية"),
            v("Saws", "Scies", "مناشير"),
            v("Sanders", "Ponceuses", "صنفرة كهربائية"),
            v("Grinders", "Meuleuses", "جلاخات"),
        )),
        b(v("Hand Tools", "Outils manuels", "أدوات يدوية")),
        b(v("Plumbing & Pipe Tools", "Outils de plomberie et tuyauterie", "أدوات سباكة وأنابيب")),
        b(v("Electrical & Testing Tools", "Outils électriques et de test", "أدوات كهرباء واختبار")),
        b(v("Cleaning & Restoration Equipment", "Équipement de nettoyage et restauration", "معدات تنظيف وترميم"), *choices(
            v("Carpet Cleaners", "Nettoyeurs de tapis", "منظفات سجاد"),
            v("Pressure Washers", "Laveuses à pression", "غسالات ضغط"),
            v("Floor Scrubbers", "Autolaveuses", "ماكينات تنظيف أرضيات"),
            v("Steam Cleaners", "Nettoyeurs vapeur", "منظفات بخارية"),
        )),
        b(v("Surveying & Inspection", "Arpentage et inspection", "مسح وفحص"), *choices(
            v("Laser Levels", "Niveaux laser", "مستويات ليزر"),
            v("Total Stations", "Stations totales", "محطات مسح متكاملة"),
            v("Thermal Cameras", "Caméras thermiques", "كاميرات حرارية"),
            v("Inspection Cameras", "Caméras d'inspection", "كاميرات فحص"),
        )),
        aliases=("tools",),
        presentation=EQUIPMENT_PRESENTATION,
    ),
    c(
        v("Baby & Kids", "Bébés et enfants", "الأطفال والرضع"),
        b(v("Travel & Safety", "Voyage et sécurité", "السفر والسلامة")),
        b(v("Nursery & Sleep", "Chambre et sommeil", "الحضانة والنوم")),
        b(v("Toys & Play", "Jouets et jeux", "الألعاب واللعب")),
        b(v("Party & Event Gear", "Équipement de fête", "معدات حفلات")),
        presentation=ITEM_PRESENTATION,
    ),
    c(
        v("Sports & Outdoors", "Sports et plein air", "الرياضة والأنشطة الخارجية"),
        b(v("Camping & Outdoors", "Camping et plein air", "التخييم والأنشطة الخارجية"), *choices(
            v("Tents", "Tentes", "خيام"),
            v("Sleeping Bags", "Sacs de couchage", "أكياس نوم"),
            v("Coolers", "Glacières", "مبردات"),
            v("Camping Stoves", "Réchauds de camping", "مواقد تخييم"),
        )),
        b(v("Winter Sports", "Sports d'hiver", "رياضات شتوية"), *choices(
            v("Skis", "Skis", "زلاجات"),
            v("Snowboards", "Planches à neige", "ألواح تزلج على الثلج"),
            v("Snowshoes", "Raquettes à neige", "أحذية ثلج"),
        )),
        b(v("Water Sports", "Sports nautiques", "رياضات مائية"), *choices(
            v("Kayaks", "Kayaks", "كاياك"),
            v("Canoes", "Canoës", "زوارق كانو"),
            v("Paddleboards", "Planches à pagaie", "ألواح تجديف"),
        )),
        b(v("Fitness Equipment", "Équipement de fitness", "معدات لياقة"), *choices(
            v("Treadmills", "Tapis de course", "أجهزة مشي"),
            v("Exercise Bikes", "Vélos d'exercice", "دراجات رياضية"),
            v("Weights", "Poids et haltères", "أوزان ودمبل"),
        )),
        b(v("Team Sports", "Sports d'équipe", "رياضات جماعية")),
        b(v("Fishing Equipment", "Équipement de pêche", "معدات صيد")),
        aliases=("sports", "Sports Equipment"),
        presentation=ITEM_PRESENTATION,
    ),
    c(
        v("Books & Learning", "Livres et apprentissage", "الكتب والتعلم"),
        b(v("Books", "Livres", "كتب")),
        b(v("Classroom Equipment", "Équipement de classe", "معدات صفية")),
        b(v("Lab & Science Kits", "Kits de laboratoire et sciences", "أطقم مختبر وعلوم"), *choices(
            v("Microscopes", "Microscopes", "مجاهر"),
            v("Science Kits", "Kits scientifiques", "أطقم علمية"),
            v("Lab Glassware", "Verrerie de laboratoire", "زجاجيات مختبر"),
        )),
        b(v("Training & Presentation", "Formation et présentation", "تدريب وعروض")),
        aliases=("books",),
        presentation=ITEM_PRESENTATION,
    ),
    c(
        v("Events & Production Equipment", "Équipement événementiel et de production", "معدات المناسبات والإنتاج"),
        b(v("Tents & Canopies", "Tentes et auvents", "الخيام والمظلات"), *choices(
            v("Frame Tents", "Tentes à structure", "خيام بإطار"),
            v("Pole Tents", "Tentes à mâts", "خيام بأعمدة"),
            v("Pop-up Canopies", "Auvents pliants", "مظلات قابلة للطي"),
        )),
        b(v("Staging & Flooring", "Scène et planchers", "منصات وأرضيات"), *choices(
            v("Stage Platforms", "Plateformes de scène", "منصات مسرح"),
            v("Risers", "Estrades", "منصات مرتفعة"),
            v("Portable Dance Floors", "Planchers de danse portatifs", "أرضيات رقص متنقلة"),
            v("Runways", "Passerelles", "ممرات عرض"),
        )),
        b(v("Audio Equipment", "Équipement audio", "معدات صوت"), *choices(
            v("PA Systems", "Systèmes de sonorisation", "أنظمة صوت عامة"),
            v("Speakers", "Haut-parleurs", "مكبرات صوت"),
            v("Microphones", "Microphones", "ميكروفونات"),
            v("Mixers", "Tables de mixage", "خلاطات صوت"),
        )),
        b(v("Lighting Equipment", "Équipement d'éclairage", "معدات إضاءة"), *choices(
            v("LED Lighting", "Éclairage DEL", "إضاءة LED"),
            v("Moving Lights", "Éclairages mobiles", "إضاءات متحركة"),
            v("Lighting Controllers", "Contrôleurs d'éclairage", "وحدات تحكم إضاءة"),
        )),
        b(v("Video & Displays", "Vidéo et affichage", "فيديو وشاشات"), *choices(
            v("LED Walls", "Murs DEL", "جدران LED"),
            v("Video Switchers", "Mélangeurs vidéo", "مبدلات فيديو"),
            v("Live Streaming Kits", "Kits de diffusion en direct", "أطقم بث مباشر"),
        )),
        b(v("Photo Booths & Signage", "Photomatons et signalisation", "أكشاك تصوير ولافتات"), *choices(
            v("Photo Booths", "Photomatons", "أكشاك تصوير"),
            v("Digital Signage", "Affichage numérique", "لافتات رقمية"),
            v("Backdrops", "Toiles de fond", "خلفيات تصوير"),
        )),
        b(v("Crowd Control & Safety", "Gestion des foules et sécurité", "إدارة الحشود والسلامة"), *choices(
            v("Queue Stanchions", "Poteaux de file", "أعمدة تنظيم الطوابير"),
            v("Temporary Signage", "Signalisation temporaire", "لافتات مؤقتة"),
            v("Emergency Lighting", "Éclairage d’urgence", "إضاءة طوارئ"),
        )),
        b(v("Event Furniture", "Mobilier événementiel", "أثاث مناسبات")),
        presentation=EQUIPMENT_PRESENTATION,
    ),
    c(
        v("Food & Concession Equipment", "Équipement de restauration et de concession", "معدات الطعام وأكشاك البيع"),
        b(v("Popcorn Equipment", "Équipement à popcorn", "معدات الفشار"), *choices(
            v("Popcorn Machines", "Machines à popcorn", "ماكينات فشار"),
            v("Popcorn Warmers", "Chauffe-popcorn", "مسخنات فشار"),
            v("Popcorn Carts", "Chariots à popcorn", "عربات فشار"),
        )),
        b(v("Hot Dog Equipment", "Équipement à hot-dogs", "معدات هوت دوغ"), *choices(
            v("Hot Dog Rollers", "Rouleurs à hot-dogs", "دوارات هوت دوغ"),
            v("Hot Dog Steamers", "Cuiseurs vapeur à hot-dogs", "مبخرات هوت دوغ"),
            v("Hot Dog Carts", "Chariots à hot-dogs", "عربات هوت دوغ"),
        )),
        b(v("Donut Equipment", "Équipement à beignes", "معدات الدونات"), *choices(
            v("Donut Makers", "Machines à beignes", "ماكينات دونات"),
            v("Donut Fryers", "Friteuses à beignes", "قلايات دونات"),
            v("Donut Display Equipment", "Présentoirs à beignes", "معدات عرض دونات"),
        )),
        b(v("Frozen & Dessert Equipment", "Équipement glacé et desserts", "معدات مجمدة وحلويات"), *choices(
            v("Cotton Candy Machines", "Machines à barbe à papa", "ماكينات غزل البنات"),
            v("Slush Machines", "Machines à granité", "ماكينات سلاش"),
            v("Soft-Serve Machines", "Machines à crème glacée molle", "ماكينات آيس كريم ناعم"),
            v("Ice Cream Equipment", "Équipement de crème glacée", "معدات آيس كريم"),
            v("Chocolate Fountains", "Fontaines de chocolat", "نوافير شوكولاتة"),
            v("Crepe Stations", "Stations à crêpes", "محطات كريب"),
            v("Waffle Makers", "Gaufriers", "ماكينات وافل"),
        )),
        b(v("Cooking Equipment", "Équipement de cuisson", "معدات طبخ"), *choices(
            v("Commercial Coffee Machines", "Machines à café commerciales", "ماكينات قهوة تجارية"),
            v("Pizza Ovens", "Fours à pizza", "أفران بيتزا"),
            v("Commercial Fryers", "Friteuses commerciales", "قلايات تجارية"),
            v("Grills & Griddles", "Grils et plaques", "شوايات وصاج"),
        )),
        b(v("Serving & Beverage Equipment", "Service et boissons", "معدات تقديم ومشروبات"), *choices(
            v("Beverage Dispensers", "Distributeurs de boissons", "موزعات مشروبات"),
            v("Mobile Bars", "Bars mobiles", "بارات متنقلة"),
            v("Serving Counters", "Comptoirs de service", "كاونترات تقديم"),
            v("Beverage Coolers", "Refroidisseurs de boissons", "مبردات مشروبات"),
        )),
        b(v("Mobile Food Units", "Unités alimentaires mobiles", "وحدات طعام متنقلة"), *choices(
            v("Mobile Kitchens", "Cuisines mobiles", "مطابخ متنقلة"),
            v("Food Trailers", "Remorques alimentaires", "مقطورات طعام"),
            v("Food Carts", "Chariots alimentaires", "عربات طعام"),
        )),
        b(v("Sanitation & Dishwashing", "Hygiène et lavage de vaisselle", "نظافة وغسل أطباق"), *choices(
            v("Dishwashing Equipment", "Équipement de lavage", "معدات غسل أطباق"),
            v("Commercial Sanitizers", "Désinfecteurs commerciaux", "معدات تعقيم تجارية"),
        )),
        presentation=EQUIPMENT_PRESENTATION,
    ),
    c(
        v("Construction & Industrial Equipment", "Équipement de construction et industriel", "معدات البناء والصناعة"),
        b(v("Earthmoving", "Terrassement", "معدات حفر وتسوية"), *choices(
            v("Excavators", "Excavatrices", "حفارات"),
            v("Skid Steers", "Chargeuses compactes", "لودرات انزلاقية"),
            v("Backhoes", "Rétrocaveuses", "حفارات خلفية"),
            v("Loaders", "Chargeuses", "لودرات"),
            v("Bulldozers", "Bouteurs", "جرافات"),
        )),
        b(v("Aerial Access", "Accès en hauteur", "الوصول للارتفاعات"), *choices(
            v("Scissor Lifts", "Nacelles à ciseaux", "رافعات مقصية"),
            v("Boom Lifts", "Nacelles articulées", "رافعات ذراعية"),
            v("Vertical Mast Lifts", "Nacelles à mât vertical", "رافعات عمودية"),
        )),
        b(v("Concrete & Masonry", "Béton et maçonnerie", "خرسانة وبناء"), *choices(
            v("Concrete Mixers", "Bétonnières", "خلاطات خرسانة"),
            v("Concrete Saws", "Scies à béton", "مناشير خرسانة"),
            v("Breakers", "Marteaux-piqueurs", "مطارق تكسير"),
            v("Trowels", "Truelles mécaniques", "ماكينات تسوية خرسانة"),
        )),
        b(v("Compaction & Paving", "Compactage et pavage", "دمك ورصف"), *choices(
            v("Plate Compactors", "Plaques vibrantes", "هراسات لوحية"),
            v("Rollers", "Rouleaux compresseurs", "مداحل"),
            v("Asphalt Cutters", "Scies à asphalte", "قواطع أسفلت"),
        )),
        b(v("Air & Pneumatic", "Air et pneumatique", "هواء ومعدات هوائية"), *choices(
            v("Air Compressors", "Compresseurs d'air", "ضواغط هواء"),
            v("Pneumatic Tools", "Outils pneumatiques", "أدوات هوائية"),
        )),
        b(v("Welding & Fabrication", "Soudage et fabrication", "لحام وتصنيع"), *choices(
            v("Welders", "Postes à souder", "ماكينات لحام"),
            v("Plasma Cutters", "Découpeurs plasma", "قواطع بلازما"),
            v("Pipe Threaders", "Fileteuses de tuyaux", "ماكينات قلاوظ أنابيب"),
        )),
        b(v("Trench & Shoring", "Tranchées et étaiement", "خنادق وتدعيم"), *choices(
            v("Trench Boxes", "Caissons de tranchée", "صناديق خنادق"),
            v("Shoring Systems", "Systèmes d'étaiement", "أنظمة تدعيم"),
            v("Confined-Space Gear", "Équipement d'espace clos", "معدات أماكن مغلقة"),
        )),
        presentation=EQUIPMENT_PRESENTATION,
    ),
    c(
        v("Agriculture & Landscaping", "Agriculture et aménagement paysager", "الزراعة وتنسيق الحدائق"),
        b(v("Tractors & Implements", "Tracteurs et accessoires", "جرارات وملحقات"), *choices(
            v("Compact Tractors", "Tracteurs compacts", "جرارات صغيرة"),
            v("Tillers", "Motobineuses", "آلات حرث"),
            v("Seeders", "Semoirs", "بذارات"),
            v("Harvesting Equipment", "Équipement de récolte", "معدات حصاد"),
        )),
        b(v("Lawn & Garden", "Pelouse et jardin", "العشب والحدائق"), *choices(
            v("Mowers", "Tondeuses", "جزازات"),
            v("Aerators", "Aérateurs", "مهويات تربة"),
            v("Trimmers", "Coupe-bordures", "مشذبات"),
            v("Leaf Blowers", "Souffleurs à feuilles", "منفاخ أوراق"),
        )),
        b(v("Forestry & Tree Care", "Foresterie et entretien des arbres", "الغابات والعناية بالأشجار"), *choices(
            v("Chainsaws", "Scies à chaîne", "مناشير جنزير"),
            v("Wood Chippers", "Broyeurs de branches", "فرامات أغصان"),
            v("Stump Grinders", "Dessoucheuses", "ماكينات طحن جذوع"),
        )),
        b(v("Irrigation & Water", "Irrigation et eau", "الري والمياه"), *choices(
            v("Water Pumps", "Pompes à eau", "مضخات مياه"),
            v("Irrigation Systems", "Systèmes d'irrigation", "أنظمة ري"),
            v("Water Tanks", "Réservoirs d'eau", "خزانات مياه"),
        )),
        b(v("Livestock & Farm Handling", "Bétail et manutention agricole", "مواشي ومناولة زراعية")),
        presentation=EQUIPMENT_PRESENTATION,
    ),
    c(
        v("Warehousing & Logistics", "Entreposage et logistique", "المستودعات واللوجستيات"),
        b(v("Forklifts & Telehandlers", "Chariots élévateurs et télescopiques", "رافعات شوكية وتلسكوبية"), *choices(
            v("Forklifts", "Chariots élévateurs", "رافعات شوكية"),
            v("Reach Trucks", "Chariots à mât rétractable", "رافعات ممرات ضيقة"),
            v("Telehandlers", "Chariots télescopiques", "رافعات تلسكوبية"),
            v("Pallet Stackers", "Gerbeurs", "مكدسات منصات"),
        )),
        b(v("Pallet & Manual Handling", "Palettes et manutention manuelle", "منصات ومناولة يدوية"), *choices(
            v("Pallet Jacks", "Transpalettes", "رافعات منصات يدوية"),
            v("Dollies", "Diables", "عربات نقل"),
            v("Hand Trucks", "Chariots manuels", "عربات يد"),
            v("Utility Carts", "Chariots utilitaires", "عربات متعددة الاستخدام"),
        )),
        b(v("Storage & Containers", "Entreposage et conteneurs", "تخزين وحاويات"), *choices(
            v("Shipping Containers", "Conteneurs maritimes", "حاويات شحن"),
            v("Mobile Storage Containers", "Conteneurs d'entreposage mobiles", "حاويات تخزين متنقلة"),
        )),
        b(v("Loading & Dock", "Chargement et quai", "تحميل وأرصفة"), *choices(
            v("Loading Ramps", "Rampes de chargement", "منحدرات تحميل"),
            v("Dock Plates", "Plaques de quai", "ألواح رصيف"),
            v("Conveyors", "Convoyeurs", "سيور ناقلة"),
        )),
        b(v("Packaging & Labeling", "Emballage et étiquetage", "تغليف ووضع ملصقات"), *choices(
            v("Label Printers", "Imprimantes d'étiquettes", "طابعات ملصقات"),
            v("Stretch Wrappers", "Filmeuses", "ماكينات تغليف مطاطي"),
        )),
        presentation=EQUIPMENT_PRESENTATION,
    ),
    c(
        v("Temporary Infrastructure & Site Services", "Infrastructure temporaire et services de chantier", "بنية تحتية مؤقتة وخدمات موقع"),
        b(v("Power Generation", "Production d'énergie", "توليد الطاقة"), *choices(
            v("Generators", "Génératrices", "مولدات"),
            v("Load Banks", "Bancs de charge", "بنوك أحمال"),
            v("Power Distribution Panels", "Panneaux de distribution", "لوحات توزيع طاقة"),
            v("Battery Storage", "Stockage sur batteries", "تخزين بطاريات"),
        )),
        b(v("Climate Control", "Contrôle climatique", "التحكم بالمناخ"), *choices(
            v("Portable Air Conditioners", "Climatiseurs portatifs", "مكيفات متنقلة"),
            v("Heaters", "Chauffages", "مدافئ"),
            v("Air Handlers", "Traitement d'air", "وحدات معالجة هواء"),
            v("Chillers", "Refroidisseurs", "مبردات صناعية"),
        )),
        b(v("Drying & Air Quality", "Séchage et qualité de l'air", "التجفيف وجودة الهواء"), *choices(
            v("Dehumidifiers", "Déshumidificateurs", "مزيلات رطوبة"),
            v("Air Scrubbers", "Épurateurs d'air", "منقيات هواء"),
            v("Industrial Fans", "Ventilateurs industriels", "مراوح صناعية"),
        )),
        b(v("Sanitation", "Installations sanitaires", "خدمات صحية"), *choices(
            v("Portable Toilets", "Toilettes portatives", "مراحيض متنقلة"),
            v("Mobile Showers", "Douches mobiles", "حمامات متنقلة"),
            v("Restroom Trailers", "Remorques sanitaires", "مقطورات دورات مياه"),
            v("Handwash Stations", "Stations de lavage des mains", "محطات غسل يدين"),
        )),
        b(v("Fencing & Traffic Control", "Clôtures et contrôle de la circulation", "أسوار وتحكم مروري"), *choices(
            v("Temporary Fencing", "Clôtures temporaires", "أسوار مؤقتة"),
            v("Crowd Barriers", "Barrières de foule", "حواجز حشود"),
            v("Traffic Signs & Cones", "Panneaux et cônes de circulation", "إشارات وأقماع مرورية"),
        )),
        b(v("Mobile Offices & Structures", "Bureaux mobiles et structures", "مكاتب وهياكل متنقلة"), *choices(
            v("Mobile Offices", "Bureaux mobiles", "مكاتب متنقلة"),
            v("Construction Trailers", "Remorques de chantier", "مقطورات بناء"),
            v("Temporary Structures", "Structures temporaires", "هياكل مؤقتة"),
        )),
        b(v("Pumps & Water Management", "Pompes et gestion de l'eau", "مضخات وإدارة مياه"), *choices(
            v("Centrifugal Pumps", "Pompes centrifuges", "مضخات طرد مركزي"),
            v("Submersible Pumps", "Pompes submersibles", "مضخات غاطسة"),
            v("Water Treatment Units", "Unités de traitement de l'eau", "وحدات معالجة مياه"),
        )),
        presentation=EQUIPMENT_PRESENTATION,
    ),
    c(
        v("Marine & Watercraft", "Maritime et embarcations", "البحرية والمراكب"),
        b(v("Boats", "Bateaux", "القوارب"), *choices(
            v("Fishing Boats", "Bateaux de pêche", "قوارب صيد"),
            v("Pontoon Boats", "Bateaux pontons", "قوارب بونتون"),
            v("Sailboats", "Voiliers", "قوارب شراعية"),
            v("Speedboats", "Bateaux rapides", "قوارب سريعة"),
        )),
        b(v("Personal Watercraft", "Motomarines", "مراكب شخصية مائية"), *choices(
            v("Jet Skis", "Motomarines", "جت سكي"),
            v("Water Scooters", "Scooters des mers", "سكوترات مائية"),
        )),
        b(v("Marine Gear", "Équipement nautique", "معدات بحرية"), *choices(
            v("Life Jackets & Safety Gear", "Gilets de sauvetage et équipement de sécurité", "سترات نجاة ومعدات سلامة"),
            v("Anchors & Docking Gear", "Ancres et équipement d’amarrage", "مراسي ومعدات رسو"),
            v("Marine Navigation Gear", "Équipement de navigation maritime", "معدات ملاحة بحرية"),
        )),
        presentation=VEHICLE_PRESENTATION,
    ),
    c(
        v("Spaces & Studios", "Espaces et studios", "مساحات واستوديوهات"),
        b(v("Event Venues", "Lieux événementiels", "أماكن مناسبات"), *choices(
            v("Banquet Halls", "Salles de banquet", "قاعات حفلات"),
            v("Conference Rooms", "Salles de conférence", "قاعات مؤتمرات"),
            v("Outdoor Venues", "Lieux extérieurs", "أماكن خارجية"),
        )),
        b(v("Studios", "Studios", "استوديوهات"), *choices(
            v("Photo Studios", "Studios photo", "استوديوهات تصوير"),
            v("Film Studios", "Studios de cinéma", "استوديوهات أفلام"),
            v("Podcast Studios", "Studios de balado", "استوديوهات بودكاست"),
            v("Music Rehearsal Studios", "Studios de répétition musicale", "استوديوهات تدريب موسيقي"),
        )),
        b(v("Meeting & Workspaces", "Réunion et espaces de travail", "اجتماعات ومساحات عمل"), *choices(
            v("Meeting Rooms", "Salles de réunion", "غرف اجتماعات"),
            v("Training Rooms", "Salles de formation", "غرف تدريب"),
            v("Coworking Offices", "Bureaux partagés", "مكاتب عمل مشترك"),
        )),
        b(v("Workshops & Maker Spaces", "Ateliers et espaces de fabrication", "ورش ومساحات تصنيع"), *choices(
            v("Woodworking Workshops", "Ateliers de menuiserie", "ورش نجارة"),
            v("Fabrication Shops", "Ateliers de fabrication", "ورش تصنيع"),
            v("Craft Studios", "Studios d'artisanat", "استوديوهات حرف"),
        )),
        b(v("Commercial Kitchens", "Cuisines commerciales", "مطابخ تجارية"), *choices(
            v("Shared Kitchens", "Cuisines partagées", "مطابخ مشتركة"),
            v("Production Kitchens", "Cuisines de production", "مطابخ إنتاج"),
        )),
        presentation=SPACE_PRESENTATION,
    ),
    c(
        v("Retail & Vending Equipment", "Équipement de commerce et de vente", "معدات التجزئة والبيع"),
        b(v("Display & Merchandising", "Présentation et marchandisage", "العرض والترويج"), *choices(
            v("Shelving", "Rayonnage", "أرفف"),
            v("Display Cases", "Vitrines", "واجهات عرض"),
            v("Garment Racks", "Portants à vêtements", "حوامل ملابس"),
            v("Mannequins", "Mannequins", "دمى عرض"),
        )),
        b(v("POS & Checkout", "Point de vente et caisse", "نقاط البيع والصندوق"), *choices(
            v("Cash Registers", "Caisses enregistreuses", "صناديق تسجيل"),
            v("Receipt Printers", "Imprimantes de reçus", "طابعات إيصالات"),
            v("Barcode Scanners", "Lecteurs de codes-barres", "ماسحات باركود"),
        )),
        b(v("Kiosks & Booths", "Kiosques et stands", "أكشاك وأجنحة"), *choices(
            v("Pop-up Kiosks", "Kiosques éphémères", "أكشاك مؤقتة"),
            v("Market Stalls", "Étalages de marché", "أكشاك سوق"),
            v("Exhibition Booths", "Stands d'exposition", "أجنحة معرض"),
        )),
        b(v("Vending & Refrigerated Merchandising", "Distributeurs et présentation réfrigérée", "بيع آلي وعرض مبرد"), *choices(
            v("Vending Machines", "Distributeurs automatiques", "ماكينات بيع آلي"),
            v("Cold Beverage Vending", "Distributeurs de boissons froides", "بيع مشروبات باردة آلي"),
        )),
        presentation=EQUIPMENT_PRESENTATION,
    ),
    c(
        v("Music & Performance Equipment", "Équipement musical et de spectacle", "معدات الموسيقى والعروض"),
        b(v("Musical Instruments", "Instruments de musique", "آلات موسيقية"), *choices(
            v("Guitars", "Guitares", "قيثارات"),
            v("Keyboards", "Claviers", "لوحات مفاتيح موسيقية"),
            v("Drum Kits", "Batteries", "طبول"),
            v("String Instruments", "Instruments à cordes", "آلات وترية"),
        )),
        b(v("DJ Equipment", "Équipement de DJ", "معدات دي جي"), *choices(
            v("DJ Controllers", "Contrôleurs DJ", "وحدات تحكم دي جي"),
            v("Turntables", "Platines", "مشغلات أسطوانات"),
            v("DJ Mixers", "Tables de mixage DJ", "خلاطات دي جي"),
        )),
        b(v("Amplification & Backline", "Amplification et backline", "تضخيم ومعدات فرقة"), *choices(
            v("Guitar Amplifiers", "Amplificateurs de guitare", "مضخمات غيتار"),
            v("Bass Amplifiers", "Amplificateurs de basse", "مضخمات باس"),
            v("Keyboard Amplifiers", "Amplificateurs de clavier", "مضخمات كيبورد"),
        )),
        b(v("Rehearsal & Performance Gear", "Équipement de répétition et scène", "معدات تدريب وعروض"), *choices(
            v("Music Stands", "Pupitres", "حوامل نوتة موسيقية"),
            v("Stage Monitors", "Retours de scène", "شاشات مراقبة مسرح"),
        )),
        presentation=EQUIPMENT_PRESENTATION,
    ),
    c(
        v("Hobbies & Creative Equipment", "Équipement de loisirs et création", "معدات الهوايات والإبداع"),
        b(v("Printing & Fabrication", "Impression et fabrication", "طباعة وتصنيع"), *choices(
            v("3D Printers", "Imprimantes 3D", "طابعات ثلاثية الأبعاد"),
            v("Laser Cutters", "Découpeuses laser", "قواطع ليزر"),
            v("Heat Presses", "Presses à chaud", "مكابس حرارية"),
        )),
        b(v("Sewing & Textile", "Couture et textile", "خياطة ونسيج"), *choices(
            v("Sewing Machines", "Machines à coudre", "ماكينات خياطة"),
            v("Embroidery Machines", "Machines à broder", "ماكينات تطريز"),
            v("Serger Machines", "Surjeteuses", "ماكينات أوفرلوك"),
        )),
        b(v("Arts & Crafts", "Arts et artisanat", "فنون وحرف"), *choices(
            v("Pottery Wheels", "Tours de potier", "دواليب فخار"),
            v("Easels", "Chevalets", "حوامل رسم"),
            v("Craft Tools", "Outils d'artisanat", "أدوات حرف"),
        )),
        b(v("Games & Recreation", "Jeux et loisirs", "ألعاب وترفيه"), *choices(
            v("Board Games", "Jeux de société", "ألعاب لوحية"),
            v("Arcade Machines", "Bornes d'arcade", "ماكينات أركيد"),
            v("Table Games", "Jeux de table", "ألعاب طاولة"),
        )),
        presentation=EQUIPMENT_PRESENTATION,
    ),
)


# Research-backed extension, 2026-10-03
# ---------------------------------------
#
# The initial expanded rental tree above remains the stable baseline.  This
# layer is deliberately additive: it extends named branches or appends a small
# number of clearly separate L1 categories without rewriting an existing
# canonical value, its lookup identity, or a stored Item.  Keeping the data in
# this same central module ensures Create, Edit, Explore, validation, Search,
# and Finder consume the very same tree through ``catalog_taxonomy``.


@dataclass(frozen=True)
class ResearchBranchExtension:
    """A research-derived L2 branch or extra L3 choices for an L2 branch."""

    category: str
    value: CatalogValue
    third_levels: tuple[CatalogValue, ...] = ()


def xb(
    category: str,
    value: CatalogValue,
    *third_levels: CatalogValue,
) -> ResearchBranchExtension:
    return ResearchBranchExtension(category, value, tuple(third_levels))


# One normal active L1 is justified: its two substantial professional
# instrument families stay discoverable without overloading general tools.
# Lab, mobility and aviation references remain explicitly review-gated in the
# evidence manifest instead of creating misleading active category shells.
RESEARCH_CATEGORY_VALUES: dict[str, CatalogValue] = {
    "Test & Measurement Equipment": v(
        "Test & Measurement Equipment",
        "Équipement d'essai et de mesure",
        "معدات الاختبار والقياس",
    ),
}
RESEARCH_CATEGORY_ALIASES: dict[str, tuple[str, ...]] = {
    "Test & Measurement Equipment": (
        "Test and Measurement Equipment",
        "Test & Measurement",
    ),
}


# Values below exclude ``Other``.  The merge helper adds one parent-scoped
# Other choice only where a real third level exists, preserving the current
# custom_third_level contract rather than creating a fourth level.
RESEARCH_BRANCH_EXTENSIONS: tuple[ResearchBranchExtension, ...] = (
    # R45 — vehicle travel accessories.
    xb("Vehicles", v("Vehicle Travel Accessories", "Accessoires de voyage pour véhicule", "ملحقات سفر المركبات"),
       v("Roof Cargo Boxes", "Coffres de toit", "صناديق سقف للسيارات")),

    # R36 — camera and specialist production equipment, kept with the
    # existing camera branch instead of creating a duplicate film category.
    xb("Electronics", v("Cameras & Video", "Caméras et vidéo", "الكاميرات والفيديو"),
       v("Broadcast Cameras", "Caméras de diffusion", "كاميرات بث"),
       v("Cinema Prime Lenses", "Objectifs cinéma à focale fixe", "عدسات سينمائية ثابتة"),
       v("Cinema Zoom Lenses", "Objectifs cinéma zoom", "عدسات سينمائية متغيرة"),
       v("Anamorphic Lenses", "Objectifs anamorphiques", "عدسات أنامورفية"),
       v("Director Viewfinders", "Viseurs de réalisateur", "مناظير مخرج")),

    # R40 — decor assets belong under the existing decor branch; this avoids
    # a weak top-level category for two related physical asset types.
    xb("Furniture", v("Rugs & Decor", "Tapis et décoration", "سجاد وديكور"),
       v("Artwork Rentals", "Location d'œuvres d'art", "تأجير أعمال فنية"),
       v("Tropical Plant Rentals", "Location de plantes tropicales", "تأجير نباتات استوائية")),

    # R13–R16, R20, R27 — tools and specialist workshop equipment.
    xb("Tools & Equipment", v("Power Tools", "Outils électriques", "أدوات كهربائية"),
       v("Angle Grinders", "Meuleuses d'angle", "جلاخات زاوية"),
       v("Belt Sanders", "Ponceuses à bande", "صنفرة شريطية"),
       v("Orbital Sanders", "Ponceuses orbitales", "صنفرة مدارية"),
       v("Circular Saws", "Scies circulaires", "مناشير دائرية"),
       v("Miter Saws", "Scies à onglet", "مناشير زاوية"),
       v("Band Saws", "Scies à ruban", "مناشير شريطية"),
       v("Reciprocating Saws", "Scies alternatives", "مناشير ترددية"),
       v("Table Saws", "Scies sur table", "مناشير طاولة"),
       v("Electric Planers", "Raboteuses électriques", "فارات كهربائية"),
       v("Routers", "Défonceuses", "فارات راوتر"),
       v("Magnetic Drills", "Perceuses magnétiques", "مثاقب مغناطيسية"),
       v("Heat Guns", "Pistolets thermiques", "مسدسات حرارية"),
       v("Metal Shears & Nibblers", "Cisailles et grignoteuses pour métal", "مقصات وقواطع معدنية")),
    xb("Tools & Equipment", v("Automotive Workshop Tools", "Outils d'atelier automobile", "أدوات ورش السيارات"),
       v("Battery Boosters", "Booster de batterie", "معززات بطارية"),
       v("Battery Testers", "Testeurs de batterie", "أجهزة فحص البطاريات"),
       v("Battery Chargers", "Chargeurs de batterie", "شواحن بطاريات"),
       v("Cooling-System Pressure Testers", "Testeurs de pression du circuit de refroidissement", "أجهزة فحص ضغط نظام التبريد"),
       v("Automotive Inspection Borescopes", "Endoscopes d'inspection automobile", "مناظير فحص سيارات"),
       v("Hydraulic Body Repair Kits", "Kits de réparation de carrosserie hydrauliques", "أطقم إصلاح هيكل هيدروليكية"),
       v("Vibratory Tumblers", "Tonneaux vibrants", "أجهزة صقل اهتزازية"),
       v("Ultrasonic Cleaners", "Nettoyeurs à ultrasons", "منظفات بالموجات فوق الصوتية"),
       v("Large Socket & Ratchet Sets", "Grandes douilles et jeux de cliquets", "أطقم لقمة وسقاطة كبيرة"),
       v("Engine Stands", "Supports moteur", "حوامل محرك"),
       v("Jack Stands", "Chandelles", "حوامل رفع"),
       v("Transmission Jacks", "Crics de transmission", "رافعات ناقل حركة"),
       v("Impact Wrenches", "Clés à chocs", "مفاتيح صدم"),
       v("Torque Wrenches", "Clés dynamométriques", "مفاتيح عزم"),
       v("Tailpipe Expanders", "Élargisseurs de tuyau d'échappement", "موسعات أنبوب عادم"),
       v("Valve Spring Compressors", "Compresseurs de ressorts de soupape", "ضواغط نوابض صمام")),
    xb("Tools & Equipment", v("Floor Installation & Removal", "Pose et retrait de revêtements de sol", "تركيب وإزالة الأرضيات"),
       v("Drum Floor Sanders", "Ponceuses à parquet à tambour", "صنفرة أرضيات أسطوانية"),
       v("Orbital Floor Sanders", "Ponceuses de sol orbitales", "صنفرة أرضيات مدارية"),
       v("Floor Edge Sanders", "Ponceuses de bordure de sol", "صنفرة حواف أرضيات"),
       v("Carpet Knee Kickers", "Tendeurs de tapis à genou", "دافعات سجاد بالركبة"),
       v("Floor Stripping Machines", "Machines de décapage de sol", "ماكينات إزالة طبقات الأرضيات"),
       v("Tile Cutters", "Coupe-carreaux", "قواطع بلاط"),
       v("Vinyl Flooring Cutters", "Coupe-revêtements vinyle", "قواطع أرضيات فينيل"),
       v("Hardwood Floor Nailers", "Cloueuses pour planchers de bois", "مسدسات مسامير أرضيات خشبية"),
       v("Concrete Floor Grinders", "Ponceuses de béton", "جلاخات أرضيات خرسانية"),
       v("Dust Extractors", "Extracteurs de poussière", "شفاطات غبار")),
    xb("Tools & Equipment", v("Plumbing & Pipe Tools", "Outils de plomberie et tuyauterie", "أدوات سباكة وأنابيب"),
       v("Pipe Benders", "Cintreuses de tuyaux", "ثنيات أنابيب"),
       v("Pipe Cutters", "Coupe-tuyaux", "قواطع أنابيب"),
       v("Pipe Threading Machines", "Machines à fileter les tuyaux", "ماكينات قلاوظ أنابيب"),
       v("Pipe Crimping Tools", "Outils de sertissage de tuyaux", "أدوات كبس أنابيب"),
       v("Flange Spreaders", "Écarteurs de brides", "موسعات فلنجات"),
       v("Sewer Inspection Cameras", "Caméras d'inspection d'égout", "كاميرات فحص مجاري"),
       v("Pipe Freezing Machines", "Machines de congélation de tuyaux", "ماكينات تجميد أنابيب"),
       v("Pipe Plugs", "Bouchons de tuyaux", "سدادات أنابيب")),
    xb("Tools & Equipment", v("Cleaning & Restoration Equipment", "Équipement de nettoyage et restauration", "معدات تنظيف وترميم"),
       v("Carpet Extractors", "Extracteurs pour tapis", "ماكينات استخراج وتنظيف السجاد"),
       v("Floor Polishers", "Polisseuses de sol", "ماكينات تلميع أرضيات"),
       v("Walk-Behind Scrubbers", "Autolaveuses accompagnées", "ماكينات تنظيف أرضيات خلفية"),
       v("Ride-On Scrubbers", "Autolaveuses autoportées", "ماكينات تنظيف أرضيات راكبة"),
       v("Handheld Sweepers", "Balayeuses portatives", "مكانس يدوية"),
       v("Walk-Behind Sweepers", "Balayeuses accompagnées", "مكانس خلفية"),
       v("Ride-On Sweepers", "Balayeuses autoportées", "مكانس راكبة"),
       v("Wet & Dry Vacuums", "Aspirateurs eau et poussière", "مكانس رطبة وجافة"),
       v("Hot-Water Pressure Washers", "Laveuses à pression à eau chaude", "غسالات ضغط بماء ساخن"),
       v("Cold-Water Pressure Washers", "Laveuses à pression à eau froide", "غسالات ضغط بماء بارد")),
    xb("Tools & Equipment", v("Surveying & Inspection", "Arpentage et inspection", "مسح وفحص"),
       v("3D Laser Scanners", "Scanners laser 3D", "ماسحات ليزر ثلاثية الأبعاد"),
       v("Robotic Total Stations", "Stations totales robotisées", "محطات مسح روبوتية"),
       v("GNSS Survey Receivers", "Récepteurs GNSS d'arpentage", "مستقبلات GNSS للمسح"),
       v("Digital Levels", "Niveaux numériques", "مستويات رقمية"),
       v("Automatic Optical Levels", "Niveaux optiques automatiques", "مستويات بصرية تلقائية"),
       v("Pipe Lasers", "Lasers pour canalisations", "ليزر أنابيب"),
       v("Underground Utility Detectors", "Détecteurs de réseaux souterrains", "كاشفات مرافق تحت الأرض")),

    # R42 — a formerly two-level family gains useful, non-overlapping types.
    xb("Baby & Kids", v("Travel & Safety", "Voyage et sécurité", "السفر والسلامة"),
       v("Car Seats", "Sièges d'auto", "مقاعد سيارات"),
       v("Strollers", "Poussettes", "عربات أطفال"),
       v("Child Wagons", "Chariots pour enfants", "عربات نقل للأطفال")),
    xb("Baby & Kids", v("Nursery & Sleep", "Chambre et sommeil", "الحضانة والنوم"),
       v("Cribs", "Lits de bébé", "أسرة أطفال"),
       v("High Chairs", "Chaises hautes", "كراسي طعام أطفال"),
       v("Baby Bathing Equipment", "Équipement de bain pour bébé", "معدات استحمام أطفال"),
       v("Bouncers", "Transats", "كراسي هزازة للأطفال"),
       v("Baby Swings", "Balancelles pour bébé", "أراجيح أطفال")),
    xb("Baby & Kids", v("Toys & Play", "Jouets et jeux", "الألعاب واللعب"),
       v("Toys, Books & Games Kits", "Kits de jouets, livres et jeux", "أطقم ألعاب وكتب وأنشطة")),

    # R44 — camping and paddling additions that do not duplicate full boats.
    xb("Sports & Outdoors", v("Camping & Outdoors", "Camping et plein air", "التخييم والأنشطة الخارجية"),
       v("Camping Equipment Kits", "Kits d'équipement de camping", "أطقم معدات تخييم"),
       v("Sleeping Equipment Kits", "Kits de couchage", "أطقم نوم للتخييم"),
       v("Packrafts", "Rafts gonflables légers", "قوارب باكرافت")),

    # R05, R37, R38 — reusable event equipment and production systems.
    xb("Events & Production Equipment", v("Tableware & Linen", "Vaisselle et linge", "أدوات مائدة ومفروشات"),
       v("Dinner Plates", "Assiettes de table", "أطباق طعام"),
       v("Glassware", "Verrerie", "أدوات زجاجية"),
       v("Cutlery Sets", "Services de couverts", "أطقم أدوات مائدة"),
       v("Canape Serving Dishes", "Plats de service pour canapés", "أطباق تقديم مقبلات"),
       v("Pastry & Serving Cutlery", "Couverts à pâtisserie et de service", "أدوات حلويات وتقديم"),
       v("Table Linen", "Linge de table", "مفروشات طاولات"),
       v("Service Linen", "Linge de service", "مفروشات خدمة"),
       v("Chair Sashes", "Nœuds de chaise", "أوشحة كراسي")),
    xb("Events & Production Equipment", v("Video & Displays", "Vidéo et affichage", "فيديو وشاشات"),
       v("Media Servers", "Serveurs média", "خوادم وسائط"),
       v("Video Production Systems", "Systèmes de production vidéo", "أنظمة إنتاج فيديو")),
    xb("Events & Production Equipment", v("Audio Equipment", "Équipement audio", "معدات صوت"),
       v("Lavalier Microphones", "Microphones-cravates", "ميكروفونات لافالير"),
       v("Shotgun Microphones", "Microphones canon", "ميكروفونات شوتغن"),
       v("Boom Poles", "Perches de prise de son", "أعمدة بوم صوت")),
    xb("Events & Production Equipment", v("Rigging & Truss", "Accrochage et structures", "تعليق وهياكل مسرح"),
       v("Rigging Equipment", "Équipement d'accrochage", "معدات تعليق"),
       v("Pipe-and-Drape Systems", "Systèmes de tringles et rideaux", "أنظمة أنابيب وستائر")),
    xb("Events & Production Equipment", v("Interpretation & Tour Audio", "Interprétation et audio de visite", "ترجمة فورية وصوت للجولات"),
       v("Soundproof Interpretation Booths", "Cabines d'interprétation insonorisées", "كبائن ترجمة فورية عازلة للصوت"),
       v("Wireless Interpretation Receivers", "Récepteurs d'interprétation sans fil", "مستقبلات ترجمة فورية لاسلكية"),
       v("Interpretation Headsets", "Casques d'interprétation", "سماعات ترجمة فورية"),
       v("Portable Tour Audio Systems", "Systèmes audio portatifs pour visites", "أنظمة صوت محمولة للجولات")),

    # R01–R04 — food equipment.  Existing concession leaves retain their
    # identities; specific missing equipment is added to their real parent.
    xb("Food & Concession Equipment", v("Frozen & Dessert Equipment", "Équipement glacé et desserts", "معدات مجمدة وحلويات"),
       v("Shaved Ice Machines", "Machines à glace pilée", "ماكينات ثلج مجروش"),
       v("Nacho Cheese Dispensers", "Distributeurs de fromage à nachos", "موزعات جبن ناتشو")),
    xb("Food & Concession Equipment", v("Commercial Kitchen Equipment", "Équipement de cuisine commerciale", "معدات مطبخ تجاري"),
       v("Catering Ovens", "Fours de traiteur", "أفران تموين"),
       v("Hot Cupboards", "Armoires chauffantes", "خزائن تسخين"),
       v("Commercial Refrigerators", "Réfrigérateurs commerciaux", "ثلاجات تجارية"),
       v("Commercial Freezers", "Congélateurs commerciaux", "مجمدات تجارية"),
       v("Preparation Tables", "Tables de préparation", "طاولات تحضير")),
    xb("Food & Concession Equipment", v("Serving & Beverage Equipment", "Service et boissons", "معدات تقديم ومشروبات"),
       v("Rectangular Chafing Dishes", "Chafing dishes rectangulaires", "أطباق تسخين مستطيلة"),
       v("Round Roll-Top Chafing Dishes", "Chafing dishes ronds à couvercle roulant", "أطباق تسخين دائرية بغطاء متحرك"),
       v("Insulated Beverage Dispensers", "Distributeurs de boissons isothermes", "موزعات مشروبات معزولة"),
       v("Hot Chocolate Urns", "Urnes à chocolat chaud", "أوعية شوكولاتة ساخنة"),
       v("Beverage Cooling Troughs", "Bacs de refroidissement pour boissons", "أحواض تبريد مشروبات")),

    # R17–R19 and R24 — industrial / construction specialisms.
    xb("Construction & Industrial Equipment", v("Welding & Fabrication", "Soudage et fabrication", "لحام وتصنيع"),
       v("Welding Power Sources", "Sources de puissance de soudage", "مصادر طاقة لحام"),
       v("Orbital Welding Systems", "Systèmes de soudage orbital", "أنظمة لحام مداري"),
       v("Tube Cutting Machines", "Machines de coupe de tubes", "ماكينات قطع أنابيب دقيقة"),
       v("Pipe Cutting Machines", "Machines de coupe de tuyaux", "ماكينات قطع أنابيب"),
       v("Tube Facing Machines", "Machines de dressage de tubes", "ماكينات تسوية وجه الأنابيب")),
    xb("Construction & Industrial Equipment", v("Hydraulic Maintenance Tools", "Outils de maintenance hydraulique", "أدوات صيانة هيدروليكية"),
       v("Hydraulic Torque Wrenches", "Clés dynamométriques hydrauliques", "مفاتيح عزم هيدروليكية"),
       v("Low-Height Hydraulic Cylinders", "Vérins hydrauliques à faible hauteur", "أسطوانات هيدروليكية منخفضة الارتفاع"),
       v("Hollow-Plunger Hydraulic Cylinders", "Vérins hydrauliques à piston creux", "أسطوانات هيدروليكية بمكبس مجوف"),
       v("Lock-Nut Hydraulic Cylinders", "Vérins hydrauliques à écrou de verrouillage", "أسطوانات هيدروليكية بصمولة قفل"),
       v("Pancake Hydraulic Cylinders", "Vérins hydrauliques plats", "أسطوانات هيدروليكية مسطحة"),
       v("Hydraulic Hand Pumps", "Pompes hydrauliques manuelles", "مضخات هيدروليكية يدوية"),
       v("Hydraulic Electric Pumps", "Pompes hydrauliques électriques", "مضخات هيدروليكية كهربائية"),
       v("Hydraulic Nut Splitters", "Casse-écrous hydrauliques", "قواطع صواميل هيدروليكية"),
       v("Hydraulic Punches", "Poinçonneuses hydrauliques", "مثاقب هيدروليكية"),
       v("Hydraulic Cutterheads", "Têtes de coupe hydrauliques", "رؤوس قطع هيدروليكية")),
    xb("Construction & Industrial Equipment", v("Concrete & Masonry", "Béton et maçonnerie", "خرسانة وبناء"),
       v("Mortar Mixers", "Malaxeurs à mortier", "خلاطات مونة"),
       v("Concrete Vibrators", "Vibreurs à béton", "هزازات خرسانة"),
       v("Concrete Buggies", "Buggys à béton", "عربات خرسانة"),
       v("Concrete Buckets", "Bennes à béton", "دلاؤ خرسانة"),
       v("Concrete Floor Saws", "Scies de sol à béton", "مناشير أرضيات خرسانية"),
       v("Diamond Core Drills", "Carotteuses diamantées", "مثاقب لقم ماسية"),
       v("Masonry Saws", "Scies à maçonnerie", "مناشير بناء"),
       v("Tile Saws", "Scies à carrelage", "مناشير بلاط"),
       v("Rebar Cutters", "Coupe-barres d'armature", "قواطع حديد تسليح"),
       v("Rebar Benders", "Cintreuses de barres d'armature", "ثنيات حديد تسليح"),
       v("Rebar Tying Tools", "Outils à ligaturer les armatures", "أدوات ربط حديد التسليح"),
       v("Concrete Scarifiers", "Scarfieuses à béton", "ماكينات تخشين خرسانة"),
       v("Portable Shot Blasters", "Grenailleuses portatives", "ماكينات قذف حبيبات متنقلة")),
    xb("Construction & Industrial Equipment", v("Trench & Shoring", "Tranchées et étaiement", "خنادق وتدعيم"),
       v("Trench Shields", "Blindages de tranchée", "دروع خنادق"),
       v("Hydraulic Shoring", "Étaiement hydraulique", "تدعيم هيدروليكي"),
       v("Manhole Braces", "Étais de regard", "دعامات غرف تفتيش"),
       v("Bedding Boxes", "Caissons de lit de pose", "صناديق فرشة أنابيب"),
       v("Ground Protection Mats", "Plaques de protection du sol", "حصائر حماية أرضية"),
       v("Steel Road Plates", "Plaques routières en acier", "ألواح طرق فولاذية"),
       v("Composite Trench Covers", "Couvercles de tranchée composites", "أغطية خنادق مركبة"),
       v("Temporary Guardrails", "Garde-corps temporaires", "درابزين مؤقت"),
       v("Trench Bridges", "Ponts de tranchée", "جسور خنادق"),
       v("Manhole Vacuum Testers", "Testeurs de vide pour regards", "أجهزة اختبار تفريغ غرف تفتيش"),
       v("Davit & Tripod Retrieval Systems", "Systèmes de récupération à potence et trépied", "أنظمة استرجاع بذراع وحامل ثلاثي")),
    xb("Construction & Industrial Equipment", v("Geotextile & Site Textile Tools", "Outils géotextiles et textiles de chantier", "أدوات جيوتكستيل ونسيج مواقع"),
       v("Portable Geotextile Sewing Machines", "Machines à coudre géotextiles portatives", "ماكينات خياطة جيوتكستيل محمولة")),

    # R31–R33 — agriculture and small-harvest processing.
    xb("Agriculture & Landscaping", v("Tractors & Implements", "Tracteurs et accessoires", "جرارات وملحقات"),
       v("Tractors", "Tracteurs", "جرارات"),
       v("Utility Terrain Vehicles", "Véhicules utilitaires tout-terrain", "مركبات تضاريس متعددة الاستخدام"),
       v("Cultivation Equipment", "Équipement de culture", "معدات زراعة وحراثة"),
       v("Post-Hole Borers", "Tarières", "مثاقب حفر أعمدة"),
       v("Agricultural Trailers", "Remorques agricoles", "مقطورات زراعية")),
    xb("Agriculture & Landscaping", v("Lawn & Garden", "Pelouse et jardin", "العشب والحدائق"),
       v("Hedge Cutters", "Taille-haies", "قواطع سياج"),
       v("Lawn Dethatchers", "Démousseurs de pelouse", "ماكينات إزالة قش العشب"),
       v("Broadcast Seed Spreaders", "Épandeurs à semences", "موزعات بذور"),
       v("Sod Cutters", "Découpeuses de gazon", "قواطع عشب")),
    xb("Agriculture & Landscaping", v("Livestock & Farm Handling", "Bétail et manutention agricole", "مواشي ومناولة زراعية"),
       v("Fencing Equipment", "Équipement de clôture", "معدات أسوار")),
    xb("Agriculture & Landscaping", v("Small-Harvest Processing", "Transformation de petites récoltes", "معالجة محاصيل صغيرة"),
       v("Honey Extractor Kits", "Kits d'extracteur de miel", "أطقم استخراج عسل"),
       v("Apple Crushers", "Broyeurs de pommes", "طواحين تفاح"),
       v("Apple Presses", "Presses à pommes", "مكابس تفاح"),
       v("Orchard Tripod Ladders", "Échelles tripodes de verger", "سلالم بستان ثلاثية")),

    # R06 and R26 — logistics, packaging and moving equipment.
    xb("Warehousing & Logistics", v("Packaging & Labeling", "Emballage et étiquetage", "تغليف ووضع ملصقات"),
       v("Vacuum Packaging Machines", "Machines d'emballage sous vide", "ماكينات تغليف مفرغ")),
    xb("Warehousing & Logistics", v("Storage & Containers", "Entreposage et conteneurs", "تخزين وحاويات"),
       v("Refrigerated Containers", "Conteneurs réfrigérés", "حاويات مبردة")),
    xb("Warehousing & Logistics", v("Pallet & Manual Handling", "Palettes et manutention manuelle", "منصات ومناولة يدوية"),
       v("Air-Cushion Appliance Lifters", "Élévateurs d'appareils à coussin d'air", "رافعات أجهزة بوسادة هوائية"),
       v("Powered Stair-Climbing Dollies", "Diables motorisés monte-escaliers", "عربات صعود سلالم كهربائية"),
       v("Tree Dollies", "Chariots pour arbres", "عربات نقل أشجار")),

    # R21–R25 — temporary utility and site equipment.
    xb("Temporary Infrastructure & Site Services", v("Climate Control", "Contrôle climatique", "التحكم بالمناخ"),
       v("Spot Coolers", "Refroidisseurs ponctuels", "مبردات موضعية"),
       v("Cooling Towers", "Tours de refroidissement", "أبراج تبريد"),
       v("Electric Heaters", "Chauffages électriques", "مدافئ كهربائية"),
       v("Indirect-Fired Heaters", "Chauffages à combustion indirecte", "مدافئ احتراق غير مباشر"),
       v("Ground Heaters", "Chauffages de sol", "مدافئ أرضية")),
    xb("Temporary Infrastructure & Site Services", v("Drying & Air Quality", "Séchage et qualité de l'air", "التجفيف وجودة الهواء"),
       v("Refrigerant Dehumidifiers", "Déshumidificateurs à réfrigérant", "مزيلات رطوبة بالتبريد"),
       v("Desiccant Dehumidifiers", "Déshumidificateurs à dessiccant", "مزيلات رطوبة مجففة"),
       v("Carpet Dryers & Air Movers", "Séchoirs de tapis et ventilateurs", "مجففات سجاد ومحركات هواء")),
    xb("Temporary Infrastructure & Site Services", v("Power Generation", "Production d'énergie", "توليد الطاقة"),
       v("Transfer Switches", "Commutateurs de transfert", "مفاتيح تحويل"),
       v("Transformers", "Transformateurs", "محولات كهربائية"),
       v("Temporary Power Cables", "Câbles d'alimentation temporaires", "كابلات طاقة مؤقتة")),
    xb("Temporary Infrastructure & Site Services", v("Pumps & Water Management", "Pompes et gestion de l'eau", "مضخات وإدارة المياه"),
       v("Diaphragm Pumps", "Pompes à diaphragme", "مضخات غشائية"),
       v("Dewatering Pumps", "Pompes d'assèchement", "مضخات نزح مياه"),
       v("Fluid Storage Tanks", "Réservoirs de stockage de fluides", "خزانات تخزين سوائل")),

    # R28–R29 — distinct equipment area, justified by two substantial
    # instrument families rather than a one-off category.
    xb("Test & Measurement Equipment", v("Electrical Test Instruments", "Instruments de test électrique", "أجهزة اختبار كهربائية"),
       v("Ground Resistance Testers", "Testeurs de résistance de terre", "أجهزة اختبار مقاومة التأريض"),
       v("Low-Resistance Ohmmeters", "Ohmmètres basse résistance", "أوميترات مقاومة منخفضة"),
       v("Insulation Resistance Testers", "Testeurs de résistance d'isolement", "أجهزة اختبار عزل"),
       v("Phase Meters", "Indicateurs de phase", "أجهزة قياس الطور"),
       v("Cable Locators", "Localisateurs de câbles", "كاشفات كابلات"),
       v("Clamp Meters", "Pinces ampèremétriques", "مقاييس تيار كماشية"),
       v("High-Voltage Meters", "Voltmètres haute tension", "مقاييس جهد عال"),
       v("Hipot Testers", "Testeurs Hipot", "أجهزة اختبار Hipot"),
       v("Electronic Loads", "Charges électroniques", "أحمال إلكترونية"),
       v("Network Cable Testers", "Testeurs de câbles réseau", "أجهزة اختبار كابلات شبكة"),
       v("Optical Test Equipment", "Équipement de test optique", "معدات اختبار بصري"),
       v("Power Analyzers", "Analyseurs de puissance", "محللات طاقة"),
       v("RF Amplifiers", "Amplificateurs RF", "مضخمات تردد لاسلكي"),
       v("Solar PV Testers", "Testeurs photovoltaïques", "أجهزة اختبار ألواح شمسية")),
    xb("Test & Measurement Equipment", v("Environmental Monitoring", "Surveillance environnementale", "مراقبة بيئية"),
       v("Water Quality Meters", "Compteurs de qualité de l'eau", "مقاييس جودة المياه"),
       v("Water Sampling Equipment", "Équipement d'échantillonnage de l'eau", "معدات أخذ عينات مياه"),
       v("Water-Level Meters", "Mesureurs de niveau d'eau", "مقاييس مستوى الماء"),
       v("Pressure Transducers", "Transducteurs de pression", "محولات ضغط"),
       v("Flow Probes", "Sondes de débit", "مجسات تدفق"),
       v("Gas Detectors", "Détecteurs de gaz", "كاشفات غاز"),
       v("PID Detectors", "Détecteurs PID", "كاشفات PID"),
       v("Noise & Sound Meters", "Sonomètres", "مقاييس ضوضاء وصوت"),
       v("Indoor Air Monitoring Equipment", "Équipement de surveillance de l'air intérieur", "معدات مراقبة هواء داخلي")),

    # R34–R35 — specialist retail equipment.
    xb("Retail & Vending Equipment", v("POS & Checkout", "Point de vente et caisse", "نقاط البيع والصندوق"),
       v("POS Hardware Kits", "Kits de matériel de point de vente", "أطقم أجهزة نقاط بيع"),
       v("Inventory Scanning Terminals", "Terminaux de lecture d'inventaire", "أجهزة مسح مخزون"),
       v("Thermal Badge Printers", "Imprimantes thermiques de badges", "طابعات شارات حرارية")),

    # R39 — music and studio equipment.
    xb("Music & Performance Equipment", v("Musical Instruments", "Instruments de musique", "آلات موسيقية"),
       v("Bass Guitars", "Guitares basses", "قيثارات باس"),
       v("Synthesizers", "Synthétiseurs", "آلات سينث"),
       v("Orchestral Instruments", "Instruments d'orchestre", "آلات أوركسترالية")),
    xb("Music & Performance Equipment", v("Amplification & Backline", "Amplification et backline", "تضخيم ومعدات فرقة"),
       v("Instrument Amplifiers", "Amplificateurs d'instruments", "مضخمات آلات موسيقية")),
    xb("Music & Performance Equipment", v("Recording & Studio Equipment", "Équipement d'enregistrement et de studio", "معدات تسجيل واستوديو"),
       v("Recording Equipment", "Équipement d'enregistrement", "معدات تسجيل")),

    # R07, R09–R10 — making and textile equipment.  Industrial 3D-printer
    # programmes are tracked as review-gated long-term offerings rather than
    # appearing as ordinary self-service Hobbies listings.
    xb("Hobbies & Creative Equipment", v("Sewing & Textile", "Couture et textile", "خياطة ونسيج"),
       v("Coverstitch Machines", "Machines à point de recouvrement", "ماكينات كوفرستيتش"),
       v("Fabric Cutting Tables", "Tables de coupe de tissu", "طاولات قص قماش"),
       v("Ironing Stations", "Postes de repassage", "محطات كي"),
       v("Fabric Die-Cutting Machines", "Machines de découpe de tissu", "ماكينات قطع قماش بالقوالب")),
    xb("Hobbies & Creative Equipment", v("Arts & Crafts", "Arts et artisanat", "فنون وحرف"),
       v("Button Badge Press Kits", "Kits de presse à badges", "أطقم مكبس شارات")),

    # R41 — a space/time booking is represented as a workspace, not as a
    # duplicate portable machine.
    xb("Spaces & Studios", v("Workshops & Maker Spaces", "Ateliers et espaces de fabrication", "ورش ومساحات تصنيع"),
       v("Sewing Workstations", "Postes de couture", "محطات خياطة"),
       v("Heat-Press Workstations", "Postes de presse à chaud", "محطات مكبس حراري")),
    xb("Spaces & Studios", v("Retail & Pop-up Spaces", "Espaces de vente éphémères", "مساحات بيع مؤقتة"),
       v("Pop-up Retail Spaces", "Espaces de vente éphémères", "مساحات بيع مؤقتة")),

    # R46 — boat type is taxonomy; crewed charter remains a rental-mode
    # mapping in the evidence report rather than a false equipment type.
    xb("Marine & Watercraft", v("Boats", "Bateaux", "القوارب"),
       v("Sailing Catamarans", "Catamarans à voile", "قوارب كاتاماران شراعية"),
       v("Monohull Sailboats", "Voiliers monocoques", "قوارب شراعية أحادية الهيكل"),
       v("Power Yachts", "Yachts à moteur", "يخوت بمحرك")),
)


def _extend_with_research(
    categories: tuple[CatalogCategory, ...],
    extensions: tuple[ResearchBranchExtension, ...],
) -> tuple[CatalogCategory, ...]:
    """Return an additive catalog without mutating baseline definitions.

    Existing L1/L2 identities retain their order and values.  A duplicate
    extension leaf is an authoring error rather than a silent replacement,
    which protects the catalog's stable canonical storage values.
    """

    ordered = list(categories)
    category_index = {category.value.canonical: index for index, category in enumerate(ordered)}
    seen_extension_paths: set[tuple[str, str, str]] = set()

    for extension in extensions:
        category_name = extension.category
        if category_name not in category_index:
            category_value = RESEARCH_CATEGORY_VALUES.get(category_name)
            if category_value is None:
                raise ValueError(f"Research extension has unknown category: {category_name!r}")
            category_index[category_name] = len(ordered)
            ordered.append(
                CatalogCategory(
                    category_value,
                    (),
                    RESEARCH_CATEGORY_ALIASES.get(category_name, ()),
                    EQUIPMENT_PRESENTATION,
                )
            )

        category_position = category_index[category_name]
        category = ordered[category_position]
        branches = list(category.branches)
        branch_position = next(
            (index for index, branch in enumerate(branches) if branch.value.canonical == extension.value.canonical),
            None,
        )

        extension_children = [
            child for child in extension.third_levels if child.canonical != OTHER.canonical
        ]
        for child in extension_children:
            key = (category_name, extension.value.canonical, child.canonical)
            if key in seen_extension_paths:
                raise ValueError(f"Duplicate research extension path: {key!r}")
            seen_extension_paths.add(key)

        if branch_position is None:
            children = choices(*extension_children) if extension_children else ()
            branches.append(CatalogBranch(extension.value, children))
        else:
            branch = branches[branch_position]
            base_children = [
                child for child in branch.third_levels if child.canonical != OTHER.canonical
            ]
            base_names = {child.canonical for child in base_children}
            duplicate_names = base_names.intersection(child.canonical for child in extension_children)
            if duplicate_names:
                raise ValueError(
                    f"Research extension repeats baseline leaf under {category_name!r} / "
                    f"{extension.value.canonical!r}: {sorted(duplicate_names)!r}"
                )
            children = choices(*(base_children + extension_children)) if (base_children or extension_children) else ()
            branches[branch_position] = CatalogBranch(branch.value, children)

        ordered[category_position] = CatalogCategory(
            category.value,
            tuple(branches),
            category.aliases,
            category.presentation,
        )

    return tuple(ordered)


RENTAL_CATEGORIES = _extend_with_research(RENTAL_CATEGORIES, RESEARCH_BRANCH_EXTENSIONS)


def _all_values() -> Iterable[CatalogValue]:
    for category in RENTAL_CATEGORIES:
        yield category.value
        for branch in category.branches:
            yield branch.value
            yield from branch.third_levels


def _validate_catalog() -> None:
    seen_categories: set[str] = set()
    labels: dict[tuple[str, str], str] = {}
    for category in RENTAL_CATEGORIES:
        canonical = category.value.canonical
        if not canonical or len(canonical) > 50:
            raise ValueError(f"Invalid Item.category value: {canonical!r}")
        if canonical in seen_categories:
            raise ValueError(f"Duplicate category: {canonical}")
        seen_categories.add(canonical)
        names = set()
        for branch in category.branches:
            if not branch.value.canonical or branch.value.canonical in names:
                raise ValueError(f"Duplicate or blank branch in {canonical}")
            names.add(branch.value.canonical)
            children = [child.canonical for child in branch.third_levels]
            if len(children) != len(set(children)):
                raise ValueError(f"Duplicate third-level choice in {canonical} / {branch.value.canonical}")
            if children and children[-1] != OTHER.canonical:
                raise ValueError(f"Configured third levels require explicit Other: {canonical} / {branch.value.canonical}")
            # The stored canonical values may be different while a translated
            # sibling label is accidentally identical.  That makes the form
            # ambiguous in that locale, so reject it at catalog import time.
            for language in ("en", "fr", "ar"):
                displayed: set[str] = set()
                for child in branch.third_levels:
                    label = child.labels()[language].strip().casefold()
                    if label in displayed:
                        raise ValueError(
                            "Duplicate sibling label in "
                            f"{canonical} / {branch.value.canonical} / {language}: {label!r}"
                        )
                    displayed.add(label)
    for value in _all_values():
        for language, label in value.labels().items():
            key = (value.canonical, language)
            previous = labels.get(key)
            if not label or (previous is not None and previous != label):
                raise ValueError(f"Missing/conflicting label: {value.canonical!r} / {language}")
            labels[key] = label


_validate_catalog()


RENTAL_CATEGORY_TREE: dict[str, dict[str, tuple[str, ...]]] = {
    category.value.canonical: {
        branch.value.canonical: tuple(value.canonical for value in branch.third_levels)
        for branch in category.branches
    }
    for category in RENTAL_CATEGORIES
}

RENTAL_VALUE_LABELS: dict[str, dict[str, str]] = {}
for _value in _all_values():
    RENTAL_VALUE_LABELS.setdefault(_value.canonical, _value.labels())

RENTAL_CATEGORY_ALIASES: dict[str, str] = {}
for _category in RENTAL_CATEGORIES:
    for _alias in (_category.value.canonical, *_category.aliases):
        _key = _alias.casefold()
        _existing = RENTAL_CATEGORY_ALIASES.setdefault(_key, _category.value.canonical)
        if _existing != _category.value.canonical:
            raise ValueError(f"Category alias collision: {_alias!r}")

RENTAL_CATEGORY_PRESENTATION: dict[str, dict[str, str]] = {
    category.value.canonical: dict(category.presentation)
    for category in RENTAL_CATEGORIES
}


def canonical_rental_category(value: str | None) -> str:
    raw = str(value or "").strip()
    return RENTAL_CATEGORY_ALIASES.get(raw.casefold(), raw)


def rental_path_aliases(
    category_name: str | None,
    subcategory_name: str | None = None,
    third_level_name: str | None = None,
) -> tuple[str, ...]:
    """Return research-source wording for one contextual rental path.

    These aliases are discoverability-only.  They intentionally do not relax
    the Create/Edit POST validator: listings still save one canonical L1/L2/L3
    path selected from the central tree.  Context keeps an alias attached to
    its real parent even where otherwise identical names appear elsewhere.
    """
    category = canonical_rental_category(category_name)
    subcategory = str(subcategory_name or "").strip()
    third_level = str(third_level_name or "").strip()
    if not category or not subcategory:
        return ()
    key: tuple[str, ...] = (
        (category, subcategory, third_level)
        if third_level
        else (category, subcategory)
    )
    return RESEARCH_PATH_ALIASES.get(key, ())


def _validate_research_path_aliases() -> None:
    """Fail fast if a discoverability alias points outside the live tree."""
    for path, aliases in RESEARCH_PATH_ALIASES.items():
        if len(path) not in {2, 3}:
            raise ValueError(f"Invalid research alias path depth: {path!r}")
        category, subcategory = path[:2]
        category = canonical_rental_category(category)
        branches = RENTAL_CATEGORY_TREE.get(category)
        if not branches or subcategory not in branches:
            raise ValueError(f"Research alias points to missing branch: {path!r}")
        if len(path) == 3 and path[2] not in branches[subcategory]:
            raise ValueError(f"Research alias points to missing type: {path!r}")
        seen: set[str] = set()
        for alias in aliases:
            normalized = str(alias or "").strip().casefold()
            if not normalized or normalized in seen:
                raise ValueError(f"Invalid duplicate research alias at {path!r}: {alias!r}")
            seen.add(normalized)


_validate_research_path_aliases()


def rental_seed_rows() -> tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...]:
    """Return canonical L1/L2 rows for tests and operator-facing exports.

    The Alembic seed intentionally carries an immutable snapshot of this
    output rather than importing it at migration runtime.
    """
    return tuple(
        (
            category.value.canonical,
            category.aliases,
            tuple(branch.value.canonical for branch in category.branches),
        )
        for category in RENTAL_CATEGORIES
    )


def iter_rental_catalog_rows() -> Iterable[tuple[str, str, str | None]]:
    """Yield all configured rows, including deliberately two-level branches."""
    for category in RENTAL_CATEGORIES:
        for branch in category.branches:
            if not branch.third_levels:
                yield category.value.canonical, branch.value.canonical, None
            else:
                for third in branch.third_levels:
                    yield category.value.canonical, branch.value.canonical, third.canonical
