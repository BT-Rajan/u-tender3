"""The WhatsApp message templates U-Tender sends outside the 24-hour customer window.

Every event notification goes out as one of these. Each template is submitted to Meta once, in English and
in Arabic, under the same name. Meta approves them in its own Business Manager. This catalog is the
source of truth for the parameter counts and the wording, so the bodies can be pasted into Meta when a
template is created or resubmitted. The outbox refuses to send a template that Meta has not approved.

All templates are utility-category: they report something that happened to the recipient's own account
or tender. None of them is marketing.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class TemplateSpec:
    name: str
    parameters: int
    en: str
    ar: str


# Parameter values are substituted in order as {{1}}, {{2}}, ...
# Tender and party names are passed through as text, never as URLs.
CATALOG: dict[str, TemplateSpec] = {
    spec.name: spec
    for spec in [
        TemplateSpec(
            "document_approved", 1,
            "U-Tender: your {{1}} document was approved.",
            "يوتندر: تمت الموافقة على مستند {{1}} الخاص بك.",
        ),
        TemplateSpec(
            "document_rejected", 1,
            "U-Tender: your {{1}} document needs attention. Open U-Tender to upload it again.",
            "يوتندر: مستند {{1}} الخاص بك يحتاج إلى مراجعة. افتح يوتندر لإعادة رفعه.",
        ),
        TemplateSpec(
            "verification_status", 1,
            "U-Tender: {{1}}",
            "يوتندر: {{1}}",
        ),
        TemplateSpec(
            "account_status", 1,
            "U-Tender: {{1}}",
            "يوتندر: {{1}}",
        ),
        TemplateSpec(
            "payment_status", 1,
            "U-Tender: {{1}}",
            "يوتندر: {{1}}",
        ),
        TemplateSpec(
            "new_tender", 2,
            "U-Tender: a new tender in your trade is open. {{1}}. Bids close {{2}}.",
            "يوتندر: مناقصة جديدة في مجالك مفتوحة. {{1}}. تغلق العروض {{2}}.",
        ),
        TemplateSpec(
            "offer_received", 3,
            "U-Tender: {{2}} submitted an offer on {{1}}. Amount: {{3}}.",
            "يوتندر: قدم {{2}} عرضًا على {{1}}. المبلغ: {{3}}.",
        ),
        TemplateSpec(
            "offer_revised", 3,
            "U-Tender: {{2}} revised its offer on {{1}}. Amount: {{3}}.",
            "يوتندر: عدّل {{2}} عرضه على {{1}}. المبلغ: {{3}}.",
        ),
        TemplateSpec(
            "award_won", 1,
            "U-Tender: your offer on {{1}} was accepted. Congratulations.",
            "يوتندر: تم قبول عرضك على {{1}}. مبروك.",
        ),
        TemplateSpec(
            "award_lost", 1,
            "U-Tender: the owner of {{1}} went with another offer. Thank you for bidding.",
            "يوتندر: اختار مالك {{1}} عرضًا آخر. شكرًا لمشاركتك.",
        ),
        TemplateSpec(
            "tender_amended", 2,
            "U-Tender: {{1}} was amended. {{2}}",
            "يوتندر: تم تعديل {{1}}. {{2}}",
        ),
        TemplateSpec(
            "deadline_reminder", 1,
            "U-Tender: bidding on {{1}} closes within 24 hours.",
            "يوتندر: تغلق العروض على {{1}} خلال 24 ساعة.",
        ),
        TemplateSpec(
            "tender_status", 2,
            "U-Tender: {{1}} is {{2}}.",
            "يوتندر: {{1}} {{2}}.",
        ),
    ]
}

LANGUAGES = ("en", "ar")


class TemplateError(ValueError):
    """A template was asked for with the wrong parameters. A programming error, caught by tests."""


def body_for(name: str, language: str) -> str:
    spec = CATALOG.get(name)
    if spec is None:
        raise TemplateError(f"Unknown template: {name}")
    if language not in LANGUAGES:
        raise TemplateError(f"Unsupported template language: {language}")
    return spec.en if language == "en" else spec.ar


def components_for(name: str, values: list[str]) -> list[dict]:
    """The body component for a template, with its parameters in order.

    The count must match the catalog exactly. Meta rejects a message whose parameter count is wrong.
    """
    spec = CATALOG.get(name)
    if spec is None:
        raise TemplateError(f"Unknown template: {name}")
    if len(values) != spec.parameters:
        raise TemplateError(f"{name} takes {spec.parameters} parameter(s), got {len(values)}")
    parameters = [{"type": "text", "text": _clean(value)} for value in values]
    return [{"type": "body", "parameters": parameters}]


def _clean(value: object) -> str:
    # Meta rejects newlines and runs of spaces inside a template parameter. Length is capped to stay well inside its limit.
    return " ".join(str(value).split())[:300]
