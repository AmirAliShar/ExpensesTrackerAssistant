import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Optional, Sequence


@dataclass(frozen=True)
class PersonalLoanIntent:
    action: str
    loan_type: Optional[str] = None
    person_name: Optional[str] = None
    amount: Optional[Decimal] = None
    transaction_date: Optional[date] = None
    due_date: Optional[date] = None


_AMOUNT_PATTERN = re.compile(
    r"(?:\b(?:rs\.?|pkr|rupees?)\s*|₹\s*)([\d,]+(?:\.\d{1,2})?)",
    re.IGNORECASE,
)
_BARE_AMOUNT_PATTERN = re.compile(r"\b([\d,]+(?:\.\d{1,2})?)\b")
_ISO_DATE_PATTERN = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")


def _extract_amount(text: str) -> Optional[Decimal]:
    without_dates = _ISO_DATE_PATTERN.sub("", text)
    match = _AMOUNT_PATTERN.search(without_dates) or _BARE_AMOUNT_PATTERN.search(without_dates)
    if not match:
        return None
    try:
        return Decimal(match.group(1).replace(",", ""))
    except (InvalidOperation, ValueError):
        return None


def _extract_date(text: str, marker: str = "") -> Optional[date]:
    if marker:
        marker_match = re.search(rf"\b{marker}\b\s*(?:on\s*)?(\d{{4}}-\d{{2}}-\d{{2}})", text, re.IGNORECASE)
        if marker_match:
            try:
                return date.fromisoformat(marker_match.group(1))
            except ValueError:
                return None
    match = _ISO_DATE_PATTERN.search(text)
    if match:
        try:
            return date.fromisoformat(match.group(1))
        except ValueError:
            return None
    if re.search(r"\byesterday\b", text, re.IGNORECASE):
        return date.today() - timedelta(days=1)
    if re.search(r"\btoday\b", text, re.IGNORECASE):
        return date.today()
    return None


def _clean_person(value: str) -> Optional[str]:
    value = re.split(
        r"\b(?:to borrow|as a loan|for a loan|loan|on|today|yesterday|tomorrow|because|since|due|by)\b",
        value,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    value = re.sub(r"^(?:to|from|with)\s+", "", value.strip(), flags=re.IGNORECASE)
    value = re.sub(r"^(?:my|the)\s+", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s+", " ", value).strip(" .,!?:;")
    if not value or len(value) > 255 or value.lower() in {"friends", "family", "people", "others", "everyone", "anyone"}:
        return None
    return value


def _person_after(text: str, marker: str) -> Optional[str]:
    match = re.search(rf"\b{marker}\b\s+(.+)", text, re.IGNORECASE)
    if not match:
        return None
    return _clean_person(match.group(1))


def _person_before_amount(text: str, verb_pattern: str) -> Optional[str]:
    amount_match = _AMOUNT_PATTERN.search(text) or _BARE_AMOUNT_PATTERN.search(text)
    prefix = text[:amount_match.start()] if amount_match else text
    match = re.search(rf"\b(?:{verb_pattern})\b\s+(.+)", prefix, re.IGNORECASE)
    if match:
        return _clean_person(match.group(1))
    return None


def _person_before_verb(text: str, verb_pattern: str) -> Optional[str]:
    amount_match = _AMOUNT_PATTERN.search(text) or _BARE_AMOUNT_PATTERN.search(text)
    prefix = text[:amount_match.start()] if amount_match else text
    match = re.search(rf"(.+?)\s+(?:{verb_pattern})\b", prefix, re.IGNORECASE)
    if not match:
        return None
    person = _clean_person(match.group(1))
    if person and person.lower() in {"i", "we", "you"}:
        return None
    return person


def _person_after_verb(text: str, verb_pattern: str) -> Optional[str]:
    amount_match = _AMOUNT_PATTERN.search(text) or _BARE_AMOUNT_PATTERN.search(text)
    suffix = text[:amount_match.start()] if amount_match else text
    match = re.search(rf"\b(?:{verb_pattern})\b\s+(.+)", suffix, re.IGNORECASE)
    return _clean_person(match.group(1)) if match else None


def _fallback_context_query(query: str, context: Sequence[object]) -> Optional[str]:
    if len(context) < 2:
        return None
    assistant_text = str(getattr(context[-1], "content", "")).lower()
    previous_user = str(getattr(context[-2], "content", ""))
    clean_query = query.strip()
    if clean_query.lower() in {"loan", "a loan", "it was a loan", "it is a loan", "loan, please"}:
        if "loan, a gift" in assistant_text or "loan, gift" in assistant_text or "loan, a gift, or" in assistant_text:
            return f"{previous_user} as a loan"
    if "loan, a gift" in assistant_text or "loan, gift" in assistant_text:
        if re.search(r"\bgift\b", clean_query, re.IGNORECASE):
            return f"{previous_user} as a gift"
        if re.search(r"\bpayment\b", clean_query, re.IGNORECASE):
            return f"{previous_user} as a payment"

    if "what amount should i record" in assistant_text and _extract_amount(clean_query) is not None:
        return f"{previous_user} Rs. {_extract_amount(clean_query)}"

    if "who was the other person" in assistant_text:
        previous_intent = classify_personal_loan_intent(previous_user)
        if previous_intent and previous_intent.action in {"create_lending", "repayment_lending"}:
            return f"{previous_user} to {clean_query}" if previous_intent.action == "create_lending" else f"{previous_user} from {clean_query}"
        if previous_intent and previous_intent.action in {"create_borrowing", "repayment_borrowing"}:
            return f"{previous_user} from {clean_query}" if previous_intent.action == "create_borrowing" else f"{previous_user} to {clean_query}"
    return None


def classify_personal_loan_intent(
    query: str,
    context: Sequence[object] = (),
) -> Optional[PersonalLoanIntent]:
    """Recognize unambiguous loan actions and simple follow-ups without treating gifts as expenses."""
    text = query.strip()
    lower = text.lower()
    if not text:
        return None

    previous_query = _fallback_context_query(text, context)
    if previous_query:
        parsed = classify_personal_loan_intent(previous_query)
        if parsed and parsed.action == "ambiguous_transfer":
            return PersonalLoanIntent(
                action="create_lending",
                loan_type="lent",
                person_name=parsed.person_name,
                amount=parsed.amount,
                transaction_date=parsed.transaction_date,
                due_date=parsed.due_date,
            )
        return parsed

    if re.search(r"\b(loan summary|loan overview|summari[sz]e my loans)\b", lower):
        return PersonalLoanIntent(action="summary")

    if re.search(r"\b(who has borrowed from me|who borrowed money from me|show all my pending loans|all outstanding loans|all pending loans)\b", lower):
        return PersonalLoanIntent(action="outstanding", loan_type="lent")
    if re.search(r"\b(who have i borrowed from|who did i borrow from|show all my borrowed loans)\b", lower):
        return PersonalLoanIntent(action="outstanding", loan_type="borrowed")
    if re.search(r"\b(show|list|get)\b.*\b(pending|outstanding)\b.*\bloans?\b", lower):
        return PersonalLoanIntent(action="outstanding")

    amount = _extract_amount(text)
    transaction_date = _extract_date(text)
    due_date = _extract_date(text, "due")

    if re.search(r"\b(my loan history|loan history|history of loans)\b", lower):
        person = _person_after(text, "for")
        return PersonalLoanIntent(action="history", person_name=person)

    balance_match = re.search(
        r"\bhow much(?: money)?\s+(?:does\s+)?(.+?)\s+(?:still\s+)?owe me\b|\bwhat does\s+(.+?)\s+still owe me\b",
        text,
        re.IGNORECASE,
    )
    if balance_match:
        name = balance_match.group(1) or balance_match.group(2)
        return PersonalLoanIntent(action="balance", loan_type="lent", person_name=_clean_person(name))
    if re.search(r"\bhow much(?: money)?\s+(?:do i|i)\s+owe\b", lower):
        name = _person_after(text, "owe")
        if not name:
            name = _person_after(text, "to")
        return PersonalLoanIntent(action="balance", loan_type="borrowed", person_name=name)

    if re.search(r"\b(?:paid me back|repaid me|returned .*?\s+to me|received .*?\s+back from)\b", lower):
        person = _person_after(text, "from") or _person_before_verb(text, "returned|repaid|paid")
        return PersonalLoanIntent(
            action="repayment_lending",
            loan_type="lent",
            person_name=person,
            amount=amount,
            transaction_date=transaction_date,
        )

    if re.search(r"\b(?:i|we)\s+(?:returned|repaid|paid back)\b", lower):
        person = _person_after(text, "to") or _person_after_verb(text, "returned|repaid|paid back")
        return PersonalLoanIntent(
            action="repayment_borrowing",
            loan_type="borrowed",
            person_name=person,
            amount=amount,
            transaction_date=transaction_date,
        )

    if re.search(r"\b(?:returned|repaid)\b", lower) or re.search(r"\bpaid me\b", lower):
        person = _person_before_verb(text, "returned|repaid|paid")
        return PersonalLoanIntent(
            action="repayment_lending",
            loan_type="lent",
            person_name=person,
            amount=amount,
            transaction_date=transaction_date,
        )

    if re.search(r"\b(?:borrowed|took a loan|took out a loan|loan from)\b", lower):
        person = _person_after(text, "from") or _person_after(text, "loan from")
        return PersonalLoanIntent(
            action="create_borrowing",
            loan_type="borrowed",
            person_name=person,
            amount=amount,
            transaction_date=transaction_date,
            due_date=due_date,
        )

    if re.search(r"\b(?:lent|loaned|gave .*?\bto borrow|gave .*?\bas a loan)\b", lower):
        person = _person_before_amount(text, "lent|loaned|gave")
        if not person:
            person = _person_after(text, "to")
        return PersonalLoanIntent(
            action="create_lending",
            loan_type="lent",
            person_name=person,
            amount=amount,
            transaction_date=transaction_date,
            due_date=due_date,
        )

    if re.search(r"\b(?:gave|give|sent|transferred|gifted)\b", lower):
        if re.search(r"\b(?:gift|gifted)\b", lower):
            person = _person_before_amount(text, "gave|give|sent|transferred|gifted")
            return PersonalLoanIntent(
                action="gift_expense",
                person_name=person,
                amount=amount,
                transaction_date=transaction_date,
            )
        if re.search(r"\b(?:payment|service|bought|purchase|invoice|bill)\b", lower):
            person = _person_before_amount(text, "gave|give|sent|transferred|gifted")
            return PersonalLoanIntent(
                action="payment_expense",
                person_name=person,
                amount=amount,
                transaction_date=transaction_date,
            )
        if re.search(r"\b(?:gift|gifted|donat|paid|payment|service|bought|purchase|invoice|bill)\b", lower):
            return None
        person = _person_before_amount(text, "gave|give|sent|transferred|gifted")
        if person:
            return PersonalLoanIntent(
                action="ambiguous_transfer",
                person_name=person,
                amount=amount,
                transaction_date=transaction_date,
            )

    return None
