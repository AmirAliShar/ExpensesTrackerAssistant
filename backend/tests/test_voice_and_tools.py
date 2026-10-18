import pytest
from decimal import Decimal
from fastapi import HTTPException
from app.voice.stt import transcribe_audio_groq
from app.analytics.service import calculate_analytics_summary


@pytest.mark.asyncio
async def test_transcribe_audio_rejects_empty_payload():
    """Verify speech-to-text service rejects empty or corrupted audio bytes."""
    with pytest.raises(HTTPException) as exc_info:
        await transcribe_audio_groq(b"")
    assert exc_info.value.status_code == 400
    assert "empty or corrupted" in exc_info.value.detail


def test_deterministic_financial_analytics():
    """Verify financial metrics are calculated deterministically without LLM hallucination."""
    class DummyTx:
        def __init__(self, amount, tx_type, category):
            self.id = 1
            self.user_id = 1
            self.amount = Decimal(str(amount))
            self.type = tx_type
            self.category = category
            self.date = "2026-10-13"
            self.description = "Test"
            self.created_at = None

    class DummyQuery:
        def __init__(self, items):
            self.items = items
        def filter(self, *args, **kwargs):
            return self
        def order_by(self, *args, **kwargs):
            return self
        def all(self):
            return self.items

    class DummySession:
        def query(self, *args, **kwargs):
            return DummyQuery([
                DummyTx(100000.0, "income", "Salary"),
                DummyTx(30000.0, "income", "Freelance"),
                DummyTx(25000.0, "expense", "Food"),
                DummyTx(15000.0, "expense", "Travel"),
            ])

    summary = calculate_analytics_summary(DummySession(), user_id=1)

    assert summary["total_income"] == 130000.0
    assert summary["total_expenses"] == 40000.0
    assert summary["net_savings"] == 90000.0
    # Savings rate: (90000 / 130000) * 100 = 69.2%
    assert summary["savings_rate"] == 69.2
    assert len(summary["categories"]) == 2
    assert summary["categories"][0]["category"] == "Food"
    assert summary["categories"][0]["amount"] == 25000.0
    assert summary["categories"][0]["percentage"] == 62.5
