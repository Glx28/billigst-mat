"""Tests for src.notify — email formatting."""

from src.notify import build_email, build_email_html


class TestBuildEmail:
    def test_subject_has_trigger_count(self):
        triggers = [
            {
                "type": "new_best",
                "message": "Ny billigste egg",
                "item": "Egg",
                "price": "30",
            },
            {
                "type": "below_threshold",
                "message": "Under terskel",
                "item": "Egg",
                "price": "30",
            },
        ]
        subject, body = build_email(["Leaderboard A"], triggers)
        assert "2 varsler" in subject

    def test_body_contains_leaderboards(self):
        leaderboards = ["📦 Egg (sortert etter kr/stk):\n  1. Egg 12pk — 3.00 kr/stk"]
        _, body = build_email(leaderboards, [])
        assert "Egg" in body
        assert "3.00" in body

    def test_body_contains_triggers(self):
        triggers = [{"type": "new_best", "message": "Ny billigste kylling"}]
        _, body = build_email([], triggers)
        assert "VARSLER" in body
        assert "Ny billigste kylling" in body

    def test_no_triggers_no_varsler_section(self):
        _, body = build_email(["Some leaderboard"], [])
        assert "VARSLER" not in body

    def test_empty_inputs(self):
        subject, body = build_email([], [])
        # No triggers = no count in subject
        assert "Matpris-oppdatering" in subject
        assert "varsler" not in subject.lower()


class TestBuildEmailHtml:
    def test_html_has_structure(self):
        group_data = [
            {
                "display_name": "🥚 Egg",
                "top_items": [
                    {
                        "name": "Test Egg",
                        "source": "kassal",
                        "normalized_unit_price": 3.5,
                        "price": 50,
                        "store": "SPAR",
                        "target_unit": "piece",
                        "url": "",
                    }
                ],
            }
        ]
        triggers = [{"type": "new_best", "message": "Ny billigste egg"}]
        subject, html = build_email_html(group_data, triggers)
        assert "<html>" in html
        assert "Egg" in html
        assert "Varsler" in html

    def test_html_no_triggers(self):
        group_data = [
            {
                "display_name": "🥚 Egg",
                "top_items": [
                    {
                        "name": "Test Egg",
                        "source": "kassal",
                        "normalized_unit_price": 3.5,
                        "price": 50,
                        "store": "SPAR",
                        "target_unit": "piece",
                        "url": "",
                    }
                ],
            }
        ]
        _, html = build_email_html(group_data, [])
        assert "Varsler" not in html
        assert "Egg" in html

    def test_html_subject(self):
        subject, _ = build_email_html([], [{"type": "x", "message": "m"}])
        assert "1 varsler" in subject
