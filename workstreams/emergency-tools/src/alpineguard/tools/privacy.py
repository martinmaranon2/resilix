"""
Removal of personal data from free text.

Architecture
------------
Incident descriptions, hand-off reasons and messages to other centres must not carry
the caller's phone number or e-mail address (whiteboard item "anonymize phone calls";
Swiss FADP / EU GDPR). ``scrub_pii`` replaces phone numbers, e-mail addresses and Swiss
social security numbers (AHV) with placeholders. It also removes a first and last name
that follow a self-introduction ("Ich bin Thomas Brunner", "Mein Name ist ...", "Hier ist
...", "My name is ...", "Je m'appelle ...", "Mi chiamo ..."). Other names are not found
by patterns; the agent system instruction forbids names, and a later version can add a
name detector.

Use cases
---------
1. ``update_incident`` stores only scrubbed descriptions.
2. ``find_related_incidents`` returns scrubbed transcripts.
3. ``notify_centre`` and ``handoff_to_operator`` scrub their free text.
"""

import re

_PHONE_INTERNATIONAL = re.compile(r"(?:\+|\b00)\d{2,3}(?:[\s\-/]?\(?\d\)?){7,12}")
_PHONE_SWISS_NATIONAL = re.compile(r"\b0\d{2}(?:[\s\-/]?\d){7}\b")
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_AHV_NUMBER = re.compile(r"\b756[.\s]?\d{4}[.\s]?\d{4}[.\s]?\d{2}\b")
_NAME_PART = r"[A-ZÄÖÜÉÈÀ][a-zäöüßéèàêçñ'\-]+"
_SELF_INTRODUCTION = re.compile(
    r"\b((?i:ich bin|ich heisse|ich heiße|mein name ist|hier ist|hier spricht|my name is|i am|this is|"
    r"je m'appelle|je suis|mi chiamo|sono|qui parla))\s+"
    rf"{_NAME_PART}\s+{_NAME_PART}"
)

PHONE_PLACEHOLDER = "[phone number removed]"
EMAIL_PLACEHOLDER = "[e-mail removed]"
ID_PLACEHOLDER = "[ID number removed]"
NAME_PLACEHOLDER = "[name removed]"


def scrub_pii(text: str) -> str:
    """
    Replace phone numbers, e-mail addresses, AHV numbers and self-introduced names in a text.

    Parameters:
        text: Free text, for example a transcript line or an incident description.

    Returns:
        The text with personal data replaced by placeholders.
    """
    cleaned = _SELF_INTRODUCTION.sub(lambda m: f"{m.group(1)} {NAME_PLACEHOLDER}", text)
    cleaned = _AHV_NUMBER.sub(ID_PLACEHOLDER, cleaned)
    cleaned = _EMAIL.sub(EMAIL_PLACEHOLDER, cleaned)
    cleaned = _PHONE_INTERNATIONAL.sub(PHONE_PLACEHOLDER, cleaned)
    cleaned = _PHONE_SWISS_NATIONAL.sub(PHONE_PLACEHOLDER, cleaned)
    return cleaned
