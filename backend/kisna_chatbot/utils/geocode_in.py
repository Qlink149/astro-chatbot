"""Place → (lat, lon) for birth charts. Bundled Indian city table first, geopy fallback."""

from datetime import datetime
from functools import lru_cache

from kisna_chatbot.utils.logger_config import logger

# Bundled coordinates for top Indian cities (offline, fast, reliable).
INDIAN_CITIES: dict[str, tuple[float, float]] = {
    "mumbai": (19.0760, 72.8777), "delhi": (28.7041, 77.1025), "new delhi": (28.6139, 77.2090),
    "bangalore": (12.9716, 77.5946), "bengaluru": (12.9716, 77.5946), "hyderabad": (17.3850, 78.4867),
    "ahmedabad": (23.0225, 72.5714), "chennai": (13.0827, 80.2707), "kolkata": (22.5726, 88.3639),
    "surat": (21.1702, 72.8311), "pune": (18.5204, 73.8567), "jaipur": (26.9124, 75.7873),
    "lucknow": (26.8467, 80.9462), "kanpur": (26.4499, 80.3319), "nagpur": (21.1458, 79.0882),
    "indore": (22.7196, 75.8577), "thane": (19.2183, 72.9781), "bhopal": (23.2599, 77.4126),
    "visakhapatnam": (17.6868, 83.2185), "vizag": (17.6868, 83.2185), "patna": (25.5941, 85.1376),
    "vadodara": (22.3072, 73.1812), "baroda": (22.3072, 73.1812), "ghaziabad": (28.6692, 77.4538),
    "ludhiana": (30.9010, 75.8573), "agra": (27.1767, 78.0081), "nashik": (19.9975, 73.7898),
    "faridabad": (28.4089, 77.3178), "meerut": (28.9845, 77.7064), "rajkot": (22.3039, 70.8022),
    "varanasi": (25.3176, 82.9739), "banaras": (25.3176, 82.9739), "srinagar": (34.0837, 74.7973),
    "aurangabad": (19.8762, 75.3433), "dhanbad": (23.7957, 86.4304), "amritsar": (31.6340, 74.8723),
    "navi mumbai": (19.0330, 73.0297), "allahabad": (25.4358, 81.8463), "prayagraj": (25.4358, 81.8463),
    "ranchi": (23.3441, 85.3096), "howrah": (22.5958, 88.2636), "coimbatore": (11.0168, 76.9558),
    "jabalpur": (23.1815, 79.9864), "gwalior": (26.2183, 78.1828), "vijayawada": (16.5062, 80.6480),
    "jodhpur": (26.2389, 73.0243), "madurai": (9.9252, 78.1198), "raipur": (21.2514, 81.6296),
    "kota": (25.2138, 75.8648), "guwahati": (26.1445, 91.7362), "chandigarh": (30.7333, 76.7794),
    "solapur": (17.6599, 75.9064), "hubli": (15.3647, 75.1240), "hubballi": (15.3647, 75.1240),
    "tiruchirappalli": (10.7905, 78.7047), "trichy": (10.7905, 78.7047), "bareilly": (28.3670, 79.4304),
    "mysore": (12.2958, 76.6394), "mysuru": (12.2958, 76.6394), "tiruppur": (11.1085, 77.3411),
    "gurgaon": (28.4595, 77.0266), "gurugram": (28.4595, 77.0266), "aligarh": (27.8974, 78.0880),
    "jalandhar": (31.3260, 75.5762), "bhubaneswar": (20.2961, 85.8245), "salem": (11.6643, 78.1460),
    "warangal": (17.9689, 79.5941), "guntur": (16.3067, 80.4365), "bhiwandi": (19.2813, 73.0483),
    "saharanpur": (29.9680, 77.5552), "gorakhpur": (26.7606, 83.3732), "bikaner": (28.0229, 73.3119),
    "amravati": (20.9374, 77.7796), "noida": (28.5355, 77.3910), "jamshedpur": (22.8046, 86.2029),
    "bhilai": (21.1938, 81.3509), "cuttack": (20.4625, 85.8830), "firozabad": (27.1592, 78.3957),
    "kochi": (9.9312, 76.2673), "cochin": (9.9312, 76.2673), "nellore": (14.4426, 79.9865),
    "bhavnagar": (21.7645, 72.1519), "dehradun": (30.3165, 78.0322), "durgapur": (23.5204, 87.3119),
    "asansol": (23.6739, 86.9524), "rourkela": (22.2604, 84.8536), "nanded": (19.1383, 77.3210),
    "kolhapur": (16.7050, 74.2433), "ajmer": (26.4499, 74.6399), "akola": (20.7002, 77.0082),
    "gulbarga": (17.3297, 76.8343), "kalaburagi": (17.3297, 76.8343), "jamnagar": (22.4707, 70.0577),
    "ujjain": (23.1765, 75.7885), "loni": (28.7515, 77.2880), "siliguri": (26.7271, 88.3953),
    "jhansi": (25.4484, 78.5685), "ulhasnagar": (19.2215, 73.1645), "jammu": (32.7266, 74.8570),
    "sangli": (16.8524, 74.5815), "mangalore": (12.9141, 74.8560), "mangaluru": (12.9141, 74.8560),
    "erode": (11.3410, 77.7172), "belgaum": (15.8497, 74.4977), "belagavi": (15.8497, 74.4977),
    "ambattur": (13.1143, 80.1548), "tirunelveli": (8.7139, 77.7567), "malegaon": (20.5579, 74.5287),
    "gaya": (24.7955, 85.0002), "udaipur": (24.5854, 73.7125), "maheshtala": (22.5086, 88.2532),
    "davanagere": (14.4644, 75.9218), "kozhikode": (11.2588, 75.7804), "calicut": (11.2588, 75.7804),
    "kurnool": (15.8281, 78.0373), "rajpur sonarpur": (22.4491, 88.3915), "rajahmundry": (17.0005, 81.8040),
    "bokaro": (23.6693, 86.1511), "south dumdum": (22.6100, 88.4000), "bellary": (15.1394, 76.9214),
    "patiala": (30.3398, 76.3869), "gopalpur": (22.6210, 88.4800), "agartala": (23.8315, 91.2868),
    "bhagalpur": (25.2425, 86.9842), "muzaffarnagar": (29.4727, 77.7085), "bhatpara": (22.8664, 88.4011),
    "panihati": (22.6941, 88.3745), "latur": (18.4088, 76.5604), "dhule": (20.9042, 74.7749),
    "rohtak": (28.8955, 76.6066), "korba": (22.3595, 82.7501), "bhilwara": (25.3407, 74.6313),
    "berhampur": (19.3150, 84.7941), "muzaffarpur": (26.1225, 85.3906), "ahmednagar": (19.0948, 74.7480),
    "mathura": (27.4924, 77.6737), "kollam": (8.8932, 76.6141), "avadi": (13.1147, 80.1098),
    "kadapa": (14.4674, 78.8241), "kamarhati": (22.6700, 88.3700), "sambalpur": (21.4669, 83.9812),
    "bilaspur": (22.0797, 82.1391), "shahjahanpur": (27.8830, 79.9100), "satara": (17.6805, 74.0183),
    "bijapur": (16.8302, 75.7100), "vijayapura": (16.8302, 75.7100), "rampur": (28.8103, 79.0250),
    "shivamogga": (13.9299, 75.5681), "shimoga": (13.9299, 75.5681), "chandrapur": (19.9615, 79.2961),
    "junagadh": (21.5222, 70.4579), "thrissur": (10.5276, 76.2144), "alwar": (27.5530, 76.6346),
    "bardhaman": (23.2324, 87.8615), "kulti": (23.7310, 86.8450), "kakinada": (16.9891, 82.2475),
    "nizamabad": (18.6725, 78.0941), "parbhani": (19.2686, 76.7708), "tumkur": (13.3379, 77.1173),
    "tumakuru": (13.3379, 77.1173), "khammam": (17.2473, 80.1514), "ozhukarai": (11.9394, 79.7784),
    "bihar sharif": (25.1979, 85.5140), "panipat": (29.3909, 76.9635), "darbhanga": (26.1542, 85.8918),
    "bally": (22.6500, 88.3400), "aizawl": (23.7271, 92.7176), "dewas": (22.9676, 76.0534),
    "ichalkaranji": (16.6910, 74.4605), "karnal": (29.6857, 76.9905), "bathinda": (30.2110, 74.9455),
    "jalna": (19.8410, 75.8864), "eluru": (16.7107, 81.0952), "kirari suleman nagar": (28.7285, 77.0553),
    "barasat": (22.7228, 88.4800), "purnia": (25.7771, 87.4753), "satna": (24.6005, 80.8322),
    "mau": (25.9417, 83.5611), "sonipat": (28.9931, 77.0151), "farrukhabad": (27.3826, 79.5941),
    "sagar": (23.8388, 78.7378), "durg": (21.1904, 81.2849), "imphal": (24.8170, 93.9368),
    "ratlam": (23.3315, 75.0367), "hapur": (28.7306, 77.7759), "arrah": (25.5541, 84.6603),
    "anantapur": (14.6819, 77.6006), "karimnagar": (18.4386, 79.1288), "etawah": (26.7855, 79.0154),
    "ambernath": (19.1864, 73.1926), "north dumdum": (22.6520, 88.4030), "bharatpur": (27.2152, 77.4977),
    "begusarai": (25.4182, 86.1272), "gandhidham": (23.0753, 70.1337), "baranagar": (22.6430, 88.3650),
    "tiruvottiyur": (13.1600, 80.3000), "pondicherry": (11.9416, 79.8083), "puducherry": (11.9416, 79.8083),
    "sikar": (27.6094, 75.1399), "thoothukudi": (8.7642, 78.1348), "tuticorin": (8.7642, 78.1348),
    "rewa": (24.5362, 81.3037), "mirzapur": (25.1449, 82.5653), "raichur": (16.2120, 77.3439),
    "pali": (25.7711, 73.3234), "ramagundam": (18.7550, 79.4740), "haridwar": (29.9457, 78.1642),
    "vellore": (12.9165, 79.1325), "kasganj": (27.8090, 78.6450), "sirsa": (29.5321, 75.0318),
    "shimla": (31.1048, 77.1734), "manali": (32.2432, 77.1892), "gangtok": (27.3389, 88.6065),
    "shillong": (25.5788, 91.8933), "itanagar": (27.0844, 93.6053), "kohima": (25.6751, 94.1086),
    "panaji": (15.4909, 73.8278), "goa": (15.2993, 74.1240), "margao": (15.2832, 73.9862),
    "porbandar": (21.6417, 69.6293), "dwarka": (22.2442, 68.9685), "somnath": (20.8880, 70.4013),
    "haldwani": (29.2183, 79.5130), "nainital": (29.3803, 79.4636), "rishikesh": (30.0869, 78.2676),
    "tirupati": (13.6288, 79.4192), "puri": (19.8135, 85.8312), "ayodhya": (26.7922, 82.1998),
    "vrindavan": (27.5820, 77.6996), "pushkar": (26.4897, 74.5511), "hampi": (15.3350, 76.4600),
    "kanyakumari": (8.0883, 77.5385), "rameswaram": (9.2876, 79.3129), "kedarnath": (30.7346, 79.0669),
    "amaravati": (16.5730, 80.3580), "hosur": (12.7409, 77.8253), "hisar": (29.1492, 75.7217),
    "kharagpur": (22.3460, 87.2320), "dindigul": (10.3624, 77.9695), "moradabad": (28.8386, 78.7733),
    "jalgaon": (21.0077, 75.5626), "una": (31.4685, 76.2708), "nagercoil": (8.1833, 77.4119),
    "kottayam": (9.5916, 76.5222), "alappuzha": (9.4981, 76.3388), "palakkad": (10.7867, 76.6548),
    "kannur": (11.8745, 75.3704), "thiruvananthapuram": (8.5241, 76.9366), "trivandrum": (8.5241, 76.9366),
}


def _normalize(place: str) -> str:
    return " ".join((place or "").strip().lower().replace(",", " ").split())


@lru_cache(maxsize=1)
def _get_tz_finder():
    from timezonefinder import TimezoneFinder

    return TimezoneFinder()


def geocode_place(place: str) -> tuple[float, float] | None:
    """Resolve a place name to (lat, lon). Bundled table first, Nominatim fallback."""
    key = _normalize(place)
    if not key:
        return None
    if key in INDIAN_CITIES:
        return INDIAN_CITIES[key]
    # Try first token ("jaipur rajasthan" → "jaipur")
    first = key.split(" ")[0]
    if first in INDIAN_CITIES:
        return INDIAN_CITIES[first]
    try:
        from geopy.geocoders import Nominatim

        geolocator = Nominatim(user_agent="samara-by-clara", timeout=6)
        loc = geolocator.geocode(f"{place}, India") or geolocator.geocode(place)
        if loc:
            return (float(loc.latitude), float(loc.longitude))
    except Exception as e:
        logger.warning("Nominatim geocode failed", extra={"place": place, "error": str(e)})
    return None


def timezone_offset_for(lat: float, lon: float, year: int, month: int, day: int) -> float:
    """UTC offset (hours) at birth place/date. Defaults to IST 5.5 on failure."""
    try:
        import pytz

        tz_name = _get_tz_finder().timezone_at(lat=lat, lng=lon)
        if tz_name:
            dt = pytz.timezone(tz_name).localize(datetime(year, month, day, 12, 0))
            return dt.utcoffset().total_seconds() / 3600.0
    except Exception as e:
        logger.warning("Timezone lookup failed", extra={"lat": lat, "lon": lon, "error": str(e)})
    return 5.5
