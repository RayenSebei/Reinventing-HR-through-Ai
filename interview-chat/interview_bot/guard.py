"""Input and output guards.

Input guard: flags prompt-injection and manipulation attempts in candidate
messages and CV text (English, French, Arabic). A flag never rejects a
candidate; it is shown to the recruiter, who decides.

Output guard: the interviewer's replies must stay inside a narrow contract
(ask a question, never score, never promise, never reveal instructions or other
candidates). Anything outside the contract is replaced by the next planned
question.

Heuristics are a first layer only. The main defence is structural: the
interviewer model has no tools, no database access and only ever sees this
candidate's own conversation, wrapped as data.
"""
import re

from .textutil import normalize

_INJECTION = [
    ("override_instructions", r"\b(ignore|disregard|forget|override|bypass)\b.{0,40}\b(instruction|instructions|rules|prompt|above|previous|prior|everything)\b"),
    ("override_instructions", r"\b(ignor\w*|oubli\w*|contourn\w*)\b.{0,40}\b(instructions?|consignes?|r[eè]gles?|prompt|tout)\b"),
    ("override_instructions", r"(تجاهل|انس|تخط)\S*.{0,30}(التعليمات|الأوامر|القواعد|كل)"),
    ("role_hijack", r"\b(you are now|act as|pretend (to be|you are)|from now on you|developer mode|jailbreak|dan mode)\b"),
    ("role_hijack", r"\b(tu es (maintenant|d[ée]sormais)|agis comme|fais comme si|mode d[ée]veloppeur)\b"),
    ("role_hijack", r"(أنت الآن|تصرف ك|من الآن فصاعدا)"),
    ("prompt_extraction", r"\b(system prompt|your (instructions|prompt|rules)|reveal|print|show|repeat)\b.{0,30}\b(prompt|instructions|rules|configuration)\b"),
    ("prompt_extraction", r"\b(prompt syst[eè]me|tes instructions|tes consignes|affiche|r[ée]p[eè]te)\b.{0,30}\b(prompt|instructions|consignes)\b"),
    ("prompt_extraction", r"(اعرض|أظهر|اكتب).{0,20}(التعليمات|البرومبت)"),
    ("score_manipulation", r"\b(give|rate|score|mark|rank|grade|put)\b.{0,25}\b(me|this candidate|this cv)\b.{0,30}\b(10|100|perfect|maximum|max|highest|top|first|best|hired|qualified)\b"),
    ("score_manipulation", r"\b(donne|mets|attribue|classe|note)[\s-]*(moi|-moi)?\b.{0,30}\b(10|20/20|100|maximum|maximale|parfait|premier|meilleur|top)\b"),
    ("score_manipulation", r"(أعطني|اعطني|ضعني|صنفني).{0,30}(أعلى|العلامة|الأول|الأفضل|10|100)"),
    ("score_manipulation", r"\b(you must|you should|you have to|tu dois)\b.{0,30}\b(hire|select|recommend|shortlist|recruter|s[ée]lectionner|recommander)\b"),
    ("score_manipulation", r"\b(best candidate|perfect match|meilleur candidat|candidat id[ée]al)\b.{0,40}\b(rank|note|score|class)"),
    ("data_exfiltration", r"\b(other|previous|all)\s+(candidates?|applicants?)\b"),
    ("data_exfiltration", r"\b(autres|les)\s+candidats\b"),
    ("data_exfiltration", r"(المرشحين الآخرين|باقي المرشحين)"),
    ("data_exfiltration", r"\b(show|give|reveal|list|send|dump|donne|montre|affiche|envoie)\b.{0,30}\b(database|api key|password|mot de passe|base de donn[ée]es|salaries|salaires|transcripts?|reports?)\b"),
    ("markup_injection", r"(<\s*/?\s*(system|assistant|instructions?|user)\s*>|\[/?inst\]|<\|im_start\|>|###\s*(system|instruction))"),
]

_COMPILED = [(label, re.compile(p, re.I | re.S)) for label, p in _INJECTION]


def scan(text: str) -> dict:
    norm = normalize(text)
    matches = sorted({label for label, rx in _COMPILED if rx.search(norm)})
    return {"injection": bool(matches), "matches": matches}


# ---------------------------------------------------------------- output contract

_FORBIDDEN_OUTPUT = [
    r"\b(score|rating|rated|note finale|/10|/20|out of 10|sur 10)\b",
    r"\b(you are hired|you're hired|you got the job|vous [eê]tes (pris|retenu|embauch)|you (are|have been) (selected|rejected|shortlisted))\b",
    r"\b(unfortunately you|malheureusement vous)\b",
    r"\b(system prompt|my instructions|mes instructions|interview plan|question plan)\b",
    r"\b(other candidates?|autres candidats|المرشحين)\b",
    r"\b(salary of|salaire de)\b",
]
_FORBIDDEN_RX = [re.compile(p, re.I) for p in _FORBIDDEN_OUTPUT]


def output_ok(text: str, max_chars: int = 600) -> bool:
    if not text or len(text) > max_chars:
        return False
    norm = normalize(text)
    return not any(rx.search(norm) for rx in _FORBIDDEN_RX)
