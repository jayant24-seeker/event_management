"""Hindi / English for the site's own words (menus, buttons, headings, badges).

Event details stay in the language the organizer wrote them in. In templates:
    {{ _("Register now") }}
returns the Hindi text when the visitor picked हिंदी, else the English as written.
Strings missing from HI simply stay in English.
"""
from flask import g, redirect, request, url_for

LANGS = {"en": "English", "hi": "हिंदी"}
COOKIE = "lang"

HI = {
    # Header, footer, menus
    "Explore": "खोजें",
    "Explore events": "इवेंट खोजें",
    "For organizers": "आयोजकों के लिए",
    "Sign in": "साइन इन",
    "Sign out": "साइन आउट",
    "My tickets": "मेरे टिकट",
    "Saved events": "सेव किए इवेंट",
    "Profile": "प्रोफ़ाइल",
    "Organizer dashboard": "आयोजक डैशबोर्ड",
    "Past events and results": "पिछले इवेंट और परिणाम",
    "Upcoming events": "आने वाले इवेंट",
    "Online events": "ऑनलाइन इवेंट",
    "Host your event": "अपना इवेंट होस्ट करें",
    "Pricing": "कीमत",
    "About": "हमारे बारे में",
    "Contact": "संपर्क",
    "Terms": "शर्तें",
    "Privacy": "गोपनीयता",
    "Refunds": "रिफ़ंड",
    "Organizers": "आयोजक",
    "Company": "कंपनी",
    "Discover and book runs, concerts, workshops and festivals across Rajasthan, Gujarat and Punjab.":
        "राजस्थान, गुजरात और पंजाब में दौड़, कॉन्सर्ट, वर्कशॉप और उत्सव खोजें और बुक करें।",
    "Search events or cities": "इवेंट या शहर खोजें",
    "Search": "खोजें",
    # Homepage
    "Find something to do this weekend": "इस वीकेंड के लिए कुछ खास खोजें",
    "Try:": "आज़माएँ:",
    "Browse by city": "शहर के अनुसार",
    "What's on near you": "आपके आसपास क्या हो रहा है",
    "Browse by category": "श्रेणी के अनुसार",
    "Upcoming": "आने वाले",
    "Don't miss these": "इन्हें मिस न करें",
    "See all events": "सभी इवेंट देखें",
    "Recently happened": "हाल ही में हुए",
    "Results, photos and memories": "परिणाम, फ़ोटो और यादें",
    "All past events": "सभी पिछले इवेंट",
    "Register now": "अभी रजिस्टर करें",
    "Only %d spots left": "सिर्फ़ %d जगह बाकी",
    "View details": "विवरण देखें",
    "Notify me": "मुझे सूचित करें",
    "See photos and results": "फ़ोटो और परिणाम देखें",
    "event": "इवेंट",
    "events": "इवेंट",
    # Badges and prices
    "Free": "निःशुल्क",
    "Sold out": "बिक गया",
    "Selling fast": "तेज़ी से बिक रहा",
    "Happening now": "अभी चल रहा",
    "Event ended": "इवेंट समाप्त",
    "Registration closed": "रजिस्ट्रेशन बंद",
    "Online": "ऑनलाइन",
    "From": "शुरुआत",
    # Explore
    "Past events": "पिछले इवेंट",
    "Filters": "फ़िल्टर",
    "All cities": "सभी शहर",
    "All categories": "सभी श्रेणियाँ",
    "Any date": "कोई भी तारीख",
    "Any price": "कोई भी कीमत",
    "Today": "आज",
    "This weekend": "इस वीकेंड",
    "This week": "इस हफ़्ते",
    "This month": "इस महीने",
    "Under ₹500": "₹500 से कम",
    "Under ₹1,000": "₹1,000 से कम",
    "Paid": "सशुल्क",
    "Soonest": "सबसे पहले",
    "Price: low to high": "कीमत: कम से ज़्यादा",
    "Most popular": "सबसे लोकप्रिय",
    "Show results": "परिणाम दिखाएँ",
    "All": "सभी",
    "Clear all": "सब हटाएँ",
    "No events match these filters": "इन फ़िल्टर से कोई इवेंट नहीं मिला",
    "Popular right now": "अभी लोकप्रिय",
    # Event page
    "Save": "सेव करें",
    "Saved": "सेव किया",
    "Share": "शेयर करें",
    "About this event": "इवेंट के बारे में",
    "Schedule": "कार्यक्रम",
    "How the day runs": "दिन का कार्यक्रम",
    "Route": "रूट",
    "The course": "रूट की जानकारी",
    "Venue": "स्थान",
    "What you get": "आपको क्या मिलेगा",
    "Kit and facilities": "किट और सुविधाएँ",
    "Prizes": "इनाम",
    "FAQs": "सवाल-जवाब",
    "Good to know": "जानने योग्य बातें",
    "Refund and cancellation policy": "रिफ़ंड और कैंसिलेशन नीति",
    "Get directions": "रास्ता देखें",
    "Organised by": "आयोजक",
    "View profile": "प्रोफ़ाइल देखें",
    "Bring your friends": "दोस्तों को बुलाएँ",
    "Copy link": "लिंक कॉपी करें",
    "Choose tickets": "टिकट चुनें",
    "Select tickets to continue": "आगे बढ़ने के लिए टिकट चुनें",
    "Add to calendar": "कैलेंडर में जोड़ें",
    "registered": "रजिस्टर्ड",
    "You may also like": "आपको ये भी पसंद आ सकते हैं",
    "Results": "परिणाम",
    "How it went": "कैसा रहा",
    "Register": "रजिस्टर करें",
    "Date": "तारीख",
    "Time": "समय",
    "Where": "कहाँ",
    "Language": "भाषा",
    "Age": "उम्र",
    "Registration closes": "रजिस्ट्रेशन की आखिरी तारीख",
    # City pages
    "Events in": "इवेंट:",
    "Happening this weekend": "इस वीकेंड",
    "Everything coming up": "आने वाले सभी इवेंट",
    "Questions about events in": "इवेंट से जुड़े सवाल:",
    # Following organizers
    "Follow": "फ़ॉलो करें",
    "Following": "फ़ॉलो कर रहे हैं",
    "For you": "आपके लिए",
    "From organizers you follow": "आपके फ़ॉलो किए आयोजकों से",
    # Reviews
    "Reviews": "समीक्षाएँ",
    "What people said": "लोगों ने क्या कहा",
    "You were there. How was it?": "आप वहाँ थे। कैसा रहा?",
    "Your review": "आपकी समीक्षा",
    "Post review": "समीक्षा भेजें",
    "Update review": "समीक्षा बदलें",
    "Booked on": "बुक किया:",
    # Explore calendar
    "Grid": "ग्रिड",
    "Calendar": "कैलेंडर",
    "Today": "आज",
    "Continues": "जारी",
    "Nothing on in this month yet.": "इस महीने अभी कोई इवेंट नहीं।",
    "Mon": "सोम", "Tue": "मंगल", "Wed": "बुध", "Thu": "गुरु", "Fri": "शुक्र", "Sat": "शनि", "Sun": "रवि",
    "Updates from the organizer": "आयोजक की ओर से सूचना",
    "Near me": "मेरे पास",
    "Finding you…": "आपको ढूँढ रहे हैं…",
    "Location is off": "लोकेशन बंद है",
    "Scan tickets": "टिकट स्कैन करें",
    # Questions
    "Questions": "सवाल",
    "Ask the organizer": "आयोजक से पूछें",
    "Your question": "आपका सवाल",
    "Ask": "पूछें",
    "e.g. Is there parking near the start?": "जैसे, क्या शुरुआत के पास पार्किंग है?",
    "Answers appear here, and we text you when yours is answered.": "जवाब यहाँ दिखेंगे, और आपके सवाल का जवाब आने पर हम आपको SMS करेंगे।",
    "to ask a question.": "करके सवाल पूछें।",
    "Check the FAQs above first.": "पहले ऊपर दिए FAQs देख लें।",
    "Waiting for an answer": "जवाब का इंतज़ार",
    "When are you free?": "आप कब फ़्री हैं?",
    "Find your next plan": "अपना अगला प्लान खोजें",
    "All upcoming": "सभी आने वाले",
    "This weekend": "इस वीकेंड", "This week": "इस हफ़्ते", "This month": "इस महीने",
    "From events that just happened": "हाल ही में हुए इवेंट से",
    "Browse by category": "श्रेणी के अनुसार देखें",
    "You're booking": "आप बुक कर रहे हैं",
    "Secure checkout": "सुरक्षित चेकआउट",
    "Help": "मदद",
    "Tomorrow": "कल",
    "In %d days": "%d दिन में",
    "Next up": "अगला",
    "Show tickets": "टिकट दिखाएँ",
    "Also coming up": "और भी आने वाले",
    "No upcoming tickets yet": "अभी कोई आने वाला टिकट नहीं",
    "When you book, your QR tickets show up here, and work offline at the gate.": "बुक करने पर आपके QR टिकट यहाँ दिखेंगे, और गेट पर बिना इंटरनेट भी चलेंगे।",
    "Find something to do": "कुछ करने को खोजें",
    "Past and cancelled": "पिछले और रद्द",
    "Cancelled": "रद्द",
    "You might like": "आपको पसंद आ सकते हैं",
    "Home": "होम",
    "Tickets": "टिकट",
    "Saved": "सेव",
    "Main": "मुख्य",
    # Offline page
    "No internet right now": "अभी इंटरनेट नहीं है",
    "Tickets you've opened on this phone before still work. Show the QR code at the gate.":
        "इस फ़ोन पर पहले खोले गए टिकट अब भी चलेंगे। गेट पर QR कोड दिखाएँ।",
    "Saved on this phone": "इस फ़ोन पर सेव",
    "Try again": "फिर से कोशिश करें",
}


def translate(text):
    return HI.get(text, text) if g.get("lang") == "hi" else text


def register_i18n(app):
    @app.before_request
    def pick_language():
        lang = request.cookies.get(COOKIE)
        g.lang = lang if lang in LANGS else "en"

    # A Jinja global (not just context), so imported macros can use _() too.
    app.jinja_env.globals.update(_=translate, LANGS=LANGS)

    @app.context_processor
    def i18n_globals():
        return {"lang": g.get("lang", "en")}

    @app.route("/lang/<code>")
    def set_language(code):
        target = request.referrer or url_for("main.home")
        # Only go back to a page on this site.
        if not target.startswith(request.host_url):
            target = url_for("main.home")
        response = redirect(target)
        if code in LANGS:
            response.set_cookie(COOKIE, code, max_age=60 * 60 * 24 * 365, samesite="Lax", httponly=True)
        return response
