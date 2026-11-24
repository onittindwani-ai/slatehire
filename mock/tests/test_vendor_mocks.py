from fastapi.testclient import TestClient

from mock.vendor_mocks import AshbyMock, CalComMock, GoogleCalendarMock, GreenhouseMock, WorkableMock


def test_every_mock_refuses_a_wrong_key():
    assert TestClient(AshbyMock().app).post("/candidate.list", json={}).status_code == 401
    assert TestClient(WorkableMock().app).get("/spi/v3/candidates").status_code == 401
    assert TestClient(GreenhouseMock().app).get("/v1/candidates").status_code == 401
    assert TestClient(CalComMock().app).post("/bookings", json={}).status_code == 401
    assert TestClient(GoogleCalendarMock().app).post("/calendars/primary/events", json={}).status_code == 401


def test_calendar_mocks_check_the_documented_body():
    m = CalComMock()
    c = TestClient(m.app)
    h = {"Authorization": f"Bearer {m.key}"}
    assert c.post("/bookings", headers=h, json={"start": "2026-12-04T10:00:00Z", "attendee": {"email": "a@b.test"}}).status_code == 400  # no cal-api-version
    ok = c.post("/bookings", headers={**h, "cal-api-version": "2026-02-25"}, json={"start": "2026-12-04T10:00:00Z", "attendee": {"email": "a@b.test"}})
    assert ok.json()["data"]["uid"] == "bk-1"
