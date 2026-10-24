import pytest

import notify


@pytest.fixture
def sent(monkeypatch):
    monkeypatch.setenv("TELEGRAM_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
    messages = []

    class Resp:
        def raise_for_status(self):
            pass

    def fake_post(url, json, timeout):
        assert url == "https://api.telegram.org/bottok/sendMessage"
        assert json["chat_id"] == "123"
        messages.append(json["text"])
        return Resp()

    monkeypatch.setattr(notify.requests, "post", fake_post)
    return messages


def jobs(n):
    return [{"title": f"Job {i}", "company": "Co", "link": f"https://a.com/{i}",
             "score": 8, "reason": "fit"} for i in range(n)]


def test_send_telegram(sent):
    notify.send_telegram("hello")
    assert sent == ["hello"]


def test_send_telegram_splits_long_text(sent):
    notify.send_telegram("\n".join(["x" * 100] * 100))
    assert len(sent) == 3
    assert all(len(m) <= notify.MAX_LEN for m in sent)


def test_five_jobs_sent_individually(sent):
    notify.notify_jobs(jobs(5))
    assert len(sent) == 5
    assert "https://a.com/0" in sent[0]


def test_more_than_five_jobs_sent_as_summary(sent):
    notify.notify_jobs(jobs(6))
    assert len(sent) == 1
    assert sent[0].startswith("6 new jobs")
    assert "https://a.com/5" in sent[0]


def test_no_jobs_sends_nothing(sent):
    notify.notify_jobs([])
    assert sent == []
