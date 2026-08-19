from __future__ import annotations

import unicodedata

_VIRAMA = {
    "hi": "\u094d",
    "bn": "\u09cd",
    "ta": "\u0bcd",
    "te": "\u0c4d",
}

_DEVANAGARI_C = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "ṅ",
    "च": "c", "छ": "ch", "ज": "j", "झ": "jh", "ञ": "ñ",
    "ट": "ṭ", "ठ": "ṭh", "ड": "ḍ", "ढ": "ḍh", "ण": "ṇ",
    "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m",
    "य": "y", "र": "r", "ल": "l", "व": "v",
    "श": "ś", "ष": "ṣ", "स": "s", "ह": "h",
}
_DEVANAGARI_IV = {
    "अ": "a", "आ": "ā", "इ": "i", "ई": "ī", "उ": "u", "ऊ": "ū",
    "ऋ": "ṛ", "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au",
}
_DEVANAGARI_VS = {
    "ा": "ā", "ि": "i", "ी": "ī", "ु": "u", "ू": "ū",
    "ृ": "ṛ", "े": "e", "ै": "ai", "ो": "o", "ौ": "au",
    "ं": "ṃ", "ः": "ḥ",
}

_BENGALI_C = {
    "ক": "k", "খ": "kh", "গ": "g", "ঘ": "gh", "ঙ": "ṅ",
    "চ": "c", "ছ": "ch", "জ": "j", "ঝ": "jh", "ঞ": "ñ",
    "ট": "ṭ", "ঠ": "ṭh", "ড": "ḍ", "ঢ": "ḍh", "ণ": "ṇ",
    "ত": "t", "থ": "th", "দ": "d", "ধ": "dh", "ন": "n",
    "প": "p", "ফ": "ph", "ব": "b", "ভ": "bh", "ম": "m",
    "য": "y", "র": "r", "ল": "l",
    "শ": "ś", "ষ": "ṣ", "স": "s", "হ": "h", "ড়": "ṛ", "য়": "ẏ",
}
_BENGALI_IV = {
    "অ": "ô", "আ": "a", "ই": "i", "ঈ": "ī", "উ": "u", "ঊ": "ū",
    "ঋ": "ṛ", "এ": "e", "ঐ": "oi", "ও": "o", "ঔ": "ou",
}
_BENGALI_VS = {
    "া": "a", "ি": "i", "ী": "ī", "ু": "u", "ূ": "ū",
    "ৃ": "ṛ", "ে": "e", "ৈ": "oi", "ো": "o", "ৌ": "ou",
    "ং": "ṃ", "ঃ": "ḥ",
}

_TAMIL_C = {
    "க": "k", "ங": "ṅ", "ச": "c", "ஞ": "ñ", "ட": "ṭ", "ண": "ṇ",
    "த": "t", "ந": "n", "ப": "p", "ம": "m", "ய": "y", "ர": "r",
    "ல": "l", "வ": "v", "ழ": "ḻ", "ள": "ḷ", "ற": "ṟ", "ன": "ṉ",
    "ஜ": "j", "ஷ": "ṣ", "ஸ": "s", "ஹ": "h",
}
_TAMIL_IV = {
    "அ": "a", "ஆ": "ā", "இ": "i", "ஈ": "ī", "உ": "u", "ஊ": "ū",
    "எ": "e", "ஏ": "ē", "ஐ": "ai", "ஒ": "o", "ஓ": "ō", "ஔ": "au",
}
_TAMIL_VS = {
    "ா": "ā", "ி": "i", "ீ": "ī", "ு": "u", "ூ": "ū",
    "ெ": "e", "ே": "ē", "ை": "ai", "ொ": "o", "ோ": "ō", "ௌ": "au",
    "ஂ": "ṃ",
}

_TELUGU_C = {
    "క": "k", "ఖ": "kh", "గ": "g", "ఘ": "gh", "ఙ": "ṅ",
    "చ": "c", "ఛ": "ch", "జ": "j", "ఝ": "jh", "ఞ": "ñ",
    "ట": "ṭ", "ఠ": "ṭh", "డ": "ḍ", "ఢ": "ḍh", "ణ": "ṇ",
    "త": "t", "థ": "th", "ద": "d", "ధ": "dh", "న": "n",
    "ప": "p", "ఫ": "ph", "బ": "b", "భ": "bh", "మ": "m",
    "య": "y", "ర": "r", "ల": "l", "వ": "v", "ళ": "ḷ",
    "శ": "ś", "ష": "ṣ", "స": "s", "హ": "h", "ఱ": "ṟ",
}
_TELUGU_IV = {
    "అ": "a", "ఆ": "ā", "ఇ": "i", "ఈ": "ī", "ఉ": "u", "ఊ": "ū",
    "ఋ": "ṛ", "ఎ": "e", "ఏ": "ē", "ఐ": "ai", "ఒ": "o", "ఓ": "ō", "ఔ": "au",
}
_TELUGU_VS = {
    "ా": "ā", "ి": "i", "ీ": "ī", "ు": "u", "ూ": "ū",
    "ృ": "ṛ", "ె": "e", "ే": "ē", "ై": "ai", "ొ": "o", "ో": "ō", "ౌ": "au",
    "ం": "ṃ", "ః": "ḥ",
}

_ARABIC = {
    "ا": "ā", "أ": "a", "إ": "i", "آ": "ā", "ء": "ʾ", "ب": "b", "ت": "t",
    "ث": "th", "ج": "j", "ح": "ḥ", "خ": "kh", "د": "d", "ذ": "dh", "ر": "r",
    "ز": "z", "س": "s", "ش": "sh", "ص": "ṣ", "ض": "ḍ", "ط": "ṭ", "ظ": "ẓ",
    "ع": "ʿ", "غ": "gh", "ف": "f", "ق": "q", "ك": "k", "ل": "l", "م": "m",
    "ن": "n", "ه": "h", "و": "w", "ي": "y", "ى": "ā", "ة": "h", "ؤ": "ʾ",
    "ئ": "ʾ", "لا": "lā",
}
_PERSIAN = {**_ARABIC, "پ": "p", "چ": "ch", "ژ": "zh", "گ": "g", "ک": "k", "ی": "y"}
_URDU = {
    **_PERSIAN,
    "ٹ": "ṭ", "ڈ": "ḍ", "ڑ": "ṛ", "ے": "e", "ہ": "h", "ھ": "h", "ں": "n",
}
_HEBREW = {
    "א": "ʾ", "ב": "b", "ג": "g", "ד": "d", "ה": "h", "ו": "v", "ז": "z",
    "ח": "ḥ", "ט": "ṭ", "י": "y", "כ": "k", "ך": "k", "ל": "l", "מ": "m",
    "ם": "m", "נ": "n", "ן": "n", "ס": "s", "ע": "ʿ", "פ": "p", "ף": "p",
    "צ": "ts", "ץ": "ts", "ק": "q", "ר": "r", "ש": "sh", "ת": "t",
}

_THAI_C = {
    "ก": "k", "ข": "kh", "ฃ": "kh", "ค": "kh", "ฅ": "kh", "ฆ": "kh", "ง": "ng",
    "จ": "ch", "ฉ": "ch", "ช": "ch", "ซ": "s", "ฌ": "ch", "ญ": "y",
    "ฎ": "d", "ฏ": "t", "ฐ": "th", "ฑ": "th", "ฒ": "th", "ณ": "n",
    "ด": "d", "ต": "t", "ถ": "th", "ท": "th", "ธ": "th", "น": "n",
    "บ": "b", "ป": "p", "ผ": "ph", "ฝ": "f", "พ": "ph", "ฟ": "f", "ภ": "ph", "ม": "m",
    "ย": "y", "ร": "r", "ฤ": "rue", "ล": "l", "ฦ": "lue", "ว": "w",
    "ศ": "s", "ษ": "s", "ส": "s", "ห": "h", "ฬ": "l", "อ": "", "ฮ": "h",
}
_THAI_V = {
    "ะ": "a", "ั": "a", "า": "a", "ำ": "am", "ิ": "i", "ี": "i",
    "ึ": "ue", "ื": "ue", "ุ": "u", "ู": "u",
    "เ": "e", "แ": "ae", "โ": "o", "ใ": "ai", "ไ": "ai", "ๅ": "a",
}

_TONE = {
    "\u0300": "˨˩",
    "\u0309": "˧˩",
    "\u0303": "˧˥",
    "\u0301": "˧˥",
    "\u0323": "˧˨ʔ",
}

_VI_INIT = (
    ("ngh", "ŋ"), ("ng", "ŋ"), ("gh", "ɣ"), ("kh", "x"), ("nh", "ɲ"),
    ("ph", "f"), ("th", "tʰ"), ("tr", "ʈ"), ("ch", "tɕ"), ("gi", "z"),
    ("qu", "kw"), ("đ", "ɗ"), ("d", "z"), ("r", "z"), ("g", "ɣ"),
    ("k", "k"), ("c", "k"), ("q", "k"), ("b", "ɓ"), ("p", "p"),
    ("t", "t"), ("m", "m"), ("n", "n"), ("l", "l"), ("s", "s"),
    ("x", "s"), ("h", "h"), ("v", "v"), ("y", "j"),
)
_VI_VOWEL = (
    ("uyên", "wiən"), ("ươu", "ɨəw"), ("ươi", "ɨəj"), ("iêu", "iəw"),
    ("yêu", "iəw"), ("uya", "iə"), ("uyu", "iu"), ("ươu", "ɨəw"),
    ("ươi", "ɨəj"), ("ươu", "ɨəw"), ("uya", "iə"),
    ("ươ", "ɨə"), ("uô", "uo"), ("iê", "iə"), ("yê", "iə"),
    ("uyê", "wiə"), ("oa", "wa"), ("oe", "wɛ"), ("uy", "wi"),
    ("ai", "aj"), ("ao", "aw"), ("au", "aw"), ("ay", "ăj"),
    ("eo", "ɛw"), ("êu", "ew"), ("iu", "iw"), ("oi", "ɔj"),
    ("ôi", "oj"), ("ơi", "ɤj"), ("ua", "uə"), ("ui", "uj"),
    ("ưi", "ɨj"), ("ưu", "ɨw"), ("ia", "iə"),
    ("a", "a"), ("ă", "ă"), ("â", "ə"), ("e", "ɛ"), ("ê", "e"),
    ("i", "i"), ("o", "ɔ"), ("ô", "o"), ("ơ", "ɤ"), ("u", "u"),
    ("ư", "ɨ"), ("y", "i"),
)
_VI_FINAL = (
    ("nh", "ŋ̟"), ("ng", "ŋ"), ("ch", "k̟"), ("c", "k"),
    ("p", "p"), ("t", "t"), ("m", "m"), ("n", "n"),
)

_LATIN_RULES: dict[str, tuple[tuple[str, str], ...]] = {
    "es": (
        ("que", "ke"), ("qui", "ki"), ("gue", "ge"), ("gui", "gi"),
        ("ce", "se"), ("ci", "si"), ("ge", "xe"), ("gi", "xi"),
        ("ll", "ʝ"), ("ch", "tʃ"), ("rr", "r"), ("ñ", "ɲ"),
        ("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"), ("ü", "u"),
        ("j", "x"), ("h", ""), ("v", "b"), ("z", "s"), ("c", "k"),
        ("q", "k"), ("y", "ʝ"), ("x", "ks"), ("w", "w"),
    ),
    "it": (
        ("sche", "ske"), ("schi", "ski"), ("sce", "ʃe"), ("sci", "ʃi"),
        ("che", "ke"), ("chi", "ki"), ("cia", "tʃa"), ("cio", "tʃo"),
        ("ciu", "tʃu"), ("gia", "dʒa"), ("gio", "dʒo"), ("giu", "dʒu"),
        ("ce", "tʃe"), ("ci", "tʃi"), ("ge", "dʒe"), ("gi", "dʒi"),
        ("gn", "ɲ"), ("gl", "ʎ"), ("à", "a"), ("è", "ɛ"), ("é", "e"),
        ("ì", "i"), ("ò", "ɔ"), ("ù", "u"), ("h", ""), ("z", "ts"),
        ("c", "k"), ("q", "k"),
    ),
    "pt": (
        ("nh", "ɲ"), ("lh", "ʎ"), ("ch", "ʃ"), ("ão", "ɐ̃w"), ("õe", "õj"),
        ("ce", "se"), ("ci", "si"), ("ge", "ʒe"), ("gi", "ʒi"),
        ("á", "a"), ("â", "ɐ"), ("ã", "ɐ̃"), ("é", "ɛ"), ("ê", "e"),
        ("í", "i"), ("ó", "ɔ"), ("ô", "o"), ("õ", "õ"), ("ú", "u"),
        ("ç", "s"), ("j", "ʒ"), ("x", "ʃ"), ("h", ""), ("c", "k"),
        ("q", "k"),
    ),
    "fr": (
        ("eaux", "o"), ("eau", "o"), ("ch", "ʃ"), ("gn", "ɲ"),
        ("ou", "u"), ("oi", "wa"), ("ai", "ɛ"), ("ei", "ɛ"),
        ("au", "o"), ("eu", "ø"), ("œu", "œ"), ("ph", "f"),
        ("qu", "k"), ("ç", "s"), ("é", "e"), ("è", "ɛ"), ("ê", "ɛ"),
        ("à", "a"), ("ù", "y"), ("û", "y"), ("ô", "o"), ("î", "i"),
        ("â", "a"), ("j", "ʒ"), ("h", ""),
    ),
    "de": (
        ("tsch", "tʃ"), ("sch", "ʃ"), ("ch", "x"), ("ck", "k"),
        ("ei", "aɪ"), ("ie", "iː"), ("eu", "ɔʏ"), ("äu", "ɔʏ"),
        ("äh", "ɛː"), ("öh", "øː"), ("üh", "yː"),
        ("ß", "s"), ("ä", "ɛ"), ("ö", "ø"), ("ü", "y"),
        ("j", "j"), ("w", "v"), ("v", "f"), ("z", "ts"),
        ("q", "k"),
    ),
    "nl": (
        ("ij", "ɛi"), ("ei", "ɛi"), ("ui", "œy"), ("oe", "u"),
        ("aa", "aː"), ("ee", "eː"), ("oo", "oː"), ("uu", "yː"),
        ("ch", "x"), ("sj", "ʃ"), ("tj", "tʃ"), ("ng", "ŋ"),
        ("j", "j"), ("w", "ʋ"), ("v", "v"), ("z", "z"), ("g", "ɣ"),
    ),
    "pl": (
        ("dź", "dʑ"), ("dż", "dʐ"), ("sz", "ʃ"), ("cz", "tʃ"),
        ("rz", "ʐ"), ("ch", "x"), ("dzi", "dʑi"),
        ("ś", "ɕ"), ("ć", "tɕ"), ("ń", "ɲ"), ("ź", "ʑ"), ("ż", "ʐ"),
        ("ł", "w"), ("ą", "ɔw̃"), ("ę", "ɛw̃"), ("ó", "u"),
    ),
    "cs": (
        ("ch", "x"), ("dž", "dʒ"), ("č", "tʃ"), ("š", "ʃ"), ("ž", "ʒ"),
        ("ř", "r̝"), ("ň", "ɲ"), ("ť", "c"), ("ď", "ɟ"),
        ("á", "aː"), ("é", "ɛː"), ("í", "iː"), ("ó", "oː"), ("ú", "uː"),
        ("ů", "uː"), ("ý", "iː"), ("ě", "ɛ"),
    ),
    "sv": (
        ("sj", "ɧ"), ("skj", "ɧ"), ("stj", "ɧ"), ("tj", "ɕ"),
        ("ng", "ŋ"), ("å", "oː"), ("ä", "ɛ"), ("ö", "ø"),
    ),
    "da": (
        ("ng", "ŋ"), ("aa", "ɔ"), ("å", "ɔ"), ("æ", "ɛ"), ("ø", "ø"),
        ("d", "ð"),
    ),
    "no": (
        ("kj", "ç"), ("skj", "ʃ"), ("ng", "ŋ"),
        ("å", "oː"), ("æ", "ɛ"), ("ø", "ø"),
    ),
    "fi": (
        ("ng", "ŋ"), ("ää", "æː"), ("öö", "øː"), ("aa", "ɑː"),
        ("ee", "eː"), ("ii", "iː"), ("oo", "oː"), ("uu", "uː"),
        ("yy", "yː"), ("ä", "æ"), ("ö", "ø"), ("y", "y"),
    ),
    "hu": (
        ("sz", "s"), ("zs", "ʒ"), ("cs", "tʃ"), ("gy", "ɟ"),
        ("ny", "ɲ"), ("ty", "c"), ("ly", "j"),
        ("á", "aː"), ("é", "eː"), ("í", "iː"), ("ó", "oː"),
        ("ö", "ø"), ("ő", "øː"), ("ú", "uː"), ("ü", "y"), ("ű", "yː"),
        ("s", "ʃ"),
    ),
    "ro": (
        ("che", "ke"), ("chi", "ki"), ("ghe", "ge"), ("ghi", "gi"),
        ("ce", "tʃe"), ("ci", "tʃi"), ("ge", "dʒe"), ("gi", "dʒi"),
        ("ă", "ə"), ("â", "ɨ"), ("î", "ɨ"), ("ș", "ʃ"), ("ş", "ʃ"),
        ("ț", "ts"), ("ţ", "ts"),
    ),
    "tr": (
        ("ç", "tʃ"), ("ş", "ʃ"), ("ğ", ""), ("c", "dʒ"),
        ("ı", "ɯ"), ("ö", "ø"), ("ü", "y"),
    ),
    "id": (
        ("ny", "ɲ"), ("ng", "ŋ"), ("sy", "ʃ"), ("kh", "x"),
        ("c", "tʃ"), ("j", "dʒ"), ("y", "j"),
    ),
    "ms": (
        ("ny", "ɲ"), ("ng", "ŋ"), ("sy", "ʃ"), ("kh", "x"),
        ("c", "tʃ"), ("j", "dʒ"), ("y", "j"),
    ),
    "sw": (
        ("ny", "ɲ"), ("ng", "ŋ"), ("sh", "ʃ"), ("ch", "tʃ"),
        ("dh", "ð"), ("th", "θ"), ("gh", "ɣ"), ("j", "dʒ"), ("y", "j"),
    ),
}


def abugida(
    text: str,
    consonants: dict[str, str],
    independent: dict[str, str],
    vowel_signs: dict[str, str],
    virama: str,
    inherent: str = "a",
    drop_final_a: bool = True,
) -> str:
    out: list[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        nxt = text[index + 1] if index + 1 < len(text) else ""
        if char in independent:
            out.append(independent[char])
            index += 1
        elif char in consonants:
            base = consonants[char]
            if nxt == virama:
                out.append(base)
                index += 2
            elif nxt in vowel_signs:
                out.append(base + vowel_signs[nxt])
                index += 2
            else:
                out.append(base + inherent)
                index += 1
        elif char in vowel_signs:
            out.append(vowel_signs[char])
            index += 1
        elif char.isspace() or char in "-'’":
            out.append(char)
            index += 1
        else:
            index += 1
    rendered = "".join(out).strip()
    if drop_final_a and rendered.endswith(inherent) and len(rendered) > 1:
        rendered = rendered[: -len(inherent)]
    return rendered


def map_chars(text: str, table: dict[str, str]) -> str:
    longest = sorted(table, key=len, reverse=True)
    index = 0
    out: list[str] = []
    while index < len(text):
        matched = False
        for key in longest:
            if text.startswith(key, index):
                out.append(table[key])
                index += len(key)
                matched = True
                break
        if not matched:
            if text[index].isspace():
                out.append(text[index])
            index += 1
    return "".join(out).strip()


def indic(lang: str, text: str) -> dict[str, str]:
    packs = {
        "hi": (_DEVANAGARI_C, _DEVANAGARI_IV, _DEVANAGARI_VS, "iast"),
        "bn": (_BENGALI_C, _BENGALI_IV, _BENGALI_VS, "iso15919"),
        "ta": (_TAMIL_C, _TAMIL_IV, _TAMIL_VS, "iso15919"),
        "te": (_TELUGU_C, _TELUGU_IV, _TELUGU_VS, "iso15919"),
    }
    pack = packs.get(lang)
    if pack is None:
        return {}
    consonants, independent, vowel_signs, system = pack
    rendered = abugida(text, consonants, independent, vowel_signs, _VIRAMA[lang])
    return {system: rendered} if rendered and rendered != text else {}


def semitic(lang: str, text: str) -> dict[str, str]:
    tables = {"ar": _ARABIC, "fa": _PERSIAN, "ur": _URDU, "he": _HEBREW}
    system = "un" if lang == "fa" else "alalc"
    table = tables.get(lang)
    if table is None:
        return {}
    rendered = map_chars(text, table)
    return {system: rendered} if rendered and rendered != text else {}


def thai(text: str) -> dict[str, str]:
    table = {**_THAI_C, **_THAI_V}
    rendered = map_chars(text, table).replace("  ", " ").strip()
    return {"rtgs": rendered} if rendered and rendered != text else {}


def _compose_viet_letters(nfd: str) -> tuple[str, str]:
    tone = "˧"
    letters: list[str] = []
    pending = ""
    for char in nfd:
        if char in _TONE:
            tone = _TONE[char]
            continue
        if char == "\u031b":
            if pending == "u":
                pending = "ư"
            elif pending == "o":
                pending = "ơ"
            continue
        if char == "\u0302":
            pending = {"a": "â", "e": "ê", "o": "ô"}.get(pending, pending)
            continue
        if char == "\u0306":
            if pending == "a":
                pending = "ă"
            continue
        if pending:
            letters.append(pending)
        pending = char
    if pending:
        letters.append(pending)
    return "".join(letters), tone


def _consume(source: str, pairs: tuple[tuple[str, str], ...]) -> tuple[str, str]:
    for key, value in pairs:
        if source.startswith(key):
            return value, source[len(key) :]
    return "", source


def vietnamese_ipa(text: str) -> dict[str, str]:
    pieces: list[str] = []
    for raw in text.replace("-", " ").split():
        nfd = unicodedata.normalize("NFD", raw.casefold())
        body, tone = _compose_viet_letters(nfd)
        initial, rest = _consume(body, _VI_INIT)
        vowel, rest = _consume(rest, _VI_VOWEL)
        final, rest = _consume(rest, _VI_FINAL)
        if not vowel and not initial:
            continue
        pieces.append(f"{initial}{vowel}{final}{tone}")
    if not pieces:
        fallback = "".join(ch for ch in text.casefold() if ch.isalpha() or ch.isspace()).strip()
        return {"ipa": f"/{fallback}/"} if fallback else {}
    return {"ipa": "/" + " ".join(pieces) + "/"}


def _g2p(text: str, rules: tuple[tuple[str, str], ...]) -> str:
    source = text.casefold()
    ordered = tuple(sorted(rules, key=lambda item: len(item[0]), reverse=True))
    index = 0
    out: list[str] = []
    while index < len(source):
        matched = False
        for src, dst in ordered:
            if source.startswith(src, index):
                out.append(dst)
                index += len(src)
                matched = True
                break
        if not matched:
            char = source[index]
            if char.isalpha() or char in "ˈˌː̃":
                out.append(char)
            elif char.isspace():
                out.append(" ")
            index += 1
    return "".join(out).strip()


def latin_ipa(lang: str, text: str) -> dict[str, str]:
    rules = _LATIN_RULES.get(lang)
    if rules is None:
        return {}
    rendered = _g2p(text, rules)
    if not rendered:
        rendered = "".join(ch for ch in text.casefold() if ch.isalpha() or ch.isspace()).strip()
    if not rendered:
        return {}
    return {"ipa": f"/{rendered}/"}
