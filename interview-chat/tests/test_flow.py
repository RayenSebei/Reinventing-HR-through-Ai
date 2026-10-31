"""End-to-end: CV -> approved invite -> interview -> evidence report -> human decision -> approved slots."""
from conftest import candidate_id_by_file, invite_and_get_token, login

ANSWERS = [
    "I built a booking REST API with Flask for a gym. I wrote the endpoints and the authentication myself.",
    "Members and sessions are stored in MySQL. I added an index on the session date and the planning query went from 2 seconds to 100 ms.",
    "With another freelancer we review each other's pull requests on GitHub; once we disagreed on folder structure and wrote a short decision note.",
    "I learned JavaScript in three weeks during the bootcamp by doing small exercises every day and building a small project.",
    "I followed a docker-compose tutorial to run Flask and MySQL in containers on my laptop, but not in production yet.",
    "I write unit tests with pytest for the price calculation functions and run them before every push.",
    "No, thank you.",
]


def run_interview(client, token, language="en", answers=ANSWERS):
    T = {"X-Interview-Token": token}
    r = client.post("/api/interview/start", headers=T, json={"language": language, "consent": True})
    assert r.status_code == 200, r.text
    completed, i = False, 0
    while not completed and i < 20:
        text = answers[min(i, len(answers) - 1)]
        r = client.post("/api/interview/message", headers=T, json={"text": text})
        assert r.status_code == 200, r.text
        completed = r.json()["completed"]
        i += 1
    assert completed
    return T


def test_full_flow(client):
    S, K = login(client, "sarra"), login(client, "karim")
    cid = candidate_id_by_file("yasmine")
    token = invite_and_get_token(client, cid)
    T = run_interview(client, token)

    # Report: evidence only, no score, human decision required
    rep = client.get(f"/api/candidates/{cid}/report", headers=S).json()
    assert rep["human_decision_required"] is True
    assert rep["interview_completed"] is True
    assert "score" not in rep
    assert rep["counts"]["must_have_with_evidence"] == rep["counts"]["must_have_total"]
    for row in rep["requirements"]:
        for q in row["interview_quotes"]:
            assert any(q.lower() in a.lower() for a in ANSWERS), "every quote must come from the candidate's words"

    # Decision without a reason is refused; with a reason it is recorded and slots are prepared, not sent
    assert client.post(f"/api/candidates/{cid}/decision", headers=S, json={"decision": "advance", "reason": "ok"}).status_code == 400
    r = client.post(f"/api/candidates/{cid}/decision", headers=S,
                    json={"decision": "advance", "reason": "Strong API and SQL evidence; check Docker in person"})
    assert r.status_code == 200, r.text
    slots = r.json()["slots_proposal"]
    outbox_before = len(client.get("/api/outbox", headers=S).json())
    r = client.post(f"/api/proposals/{slots['id']}/approve", headers=K, json={"payload_hash": slots["payload_hash"]})
    assert r.status_code == 200
    assert len(client.get("/api/outbox", headers=S).json()) == outbox_before + 1

    # Shortlist lists the candidate with a suggested position and a notice
    sl = client.get("/api/jobs/1/shortlist", headers=S).json()
    assert "not a decision" in sl["notice"]
    assert sl["candidates"][0]["id"] == cid

    # Finished interview cannot continue
    assert client.post("/api/interview/message", headers=T, json={"text": "hello again"}).status_code == 409
    assert client.get("/api/ledger/verify", headers=S).json()["valid"] is True


def test_arabic_and_french_interview(client):
    cid = candidate_id_by_file("salma")
    token = invite_and_get_token(client, cid)
    T = {"X-Interview-Token": token}
    h = client.post("/api/interview/start", headers=T, json={"language": "ar", "consent": True}).json()["history"]
    assert "مرحبا" in h[0]["text"]
    r = client.post("/api/interview/message", headers=T,
                    json={"text": "بنيت API باستعمال FastAPI لإدارة مكتبة، وكتبت كل الـ endpoints بنفسي مع قاعدة بيانات MySQL."}).json()
    assert r["bot"] and not r["completed"]


def test_consent_required(client):
    cid = candidate_id_by_file("amine")
    token = invite_and_get_token(client, cid)
    r = client.post("/api/interview/start", headers={"X-Interview-Token": token}, json={"language": "en", "consent": False})
    assert r.status_code == 400
