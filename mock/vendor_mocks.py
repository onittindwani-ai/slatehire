"""Mock Ashby, Workable, Greenhouse, Cal.com and Google Calendar servers, written from the vendors' public docs read on 2026-11-23. Nothing here is the real service, and the shapes are only as good as that reading."""

from __future__ import annotations

import base64

from fastapi import FastAPI, Header, Request, Response
from fastapi.responses import JSONResponse

RESUME = b"Customer Support Specialist, Sample Co, 2020 to 2026\n* Wrote replies to customer emails every day and trained 3 colleagues, cutting errors by 12 percent.\n* Ran the helpdesk ticket queue.\n"


def _files(app: FastAPI) -> None:
    @app.get("/files/{name}")
    def files(name: str):
        return Response(RESUME, media_type="text/plain")


class AshbyMock:
    def __init__(self, key="ashby-mock-key"):
        self.key, self.app = key, FastAPI()
        _files(self.app)
        self.jobs = {"job-1": {"cand-1", "cand-2", "cand-3", "cand-4"}, "job-2": {"cand-5"}}  # which candidates applied to which job
        self.people = [{"id": f"cand-{i}", "name": f"Sample Person {i}", "primaryEmailAddress": {"value": f"p{i}@mail.example.test"}, "primaryPhoneNumber": {"value": "(555) 010-0101"},
                        "resumeFileHandle": {"handle": f"h{i}"}, "doNotContact": i == 3} for i in range(1, 6)]

        def authed(a: str | None) -> bool:
            return bool(a) and base64.b64decode(a.split()[1]).decode() == f"{self.key}:"

        @self.app.post("/candidate.list")
        async def lst(request: Request, authorization: str | None = Header(default=None)):
            if not authed(authorization):
                return JSONResponse({"success": False, "errors": ["unauthorized"]}, 401)
            body = await request.json()
            start = int(body.get("cursor") or 0)
            page = self.people[start:start + 2]
            more = start + 2 < len(self.people)
            return {"success": True, "results": page, "moreDataAvailable": more, "nextCursor": str(start + 2) if more else None}

        @self.app.post("/application.list")
        async def apps(request: Request, authorization: str | None = Header(default=None)):
            if not authed(authorization):
                return JSONResponse({"success": False, "errors": ["unauthorized"]}, 401)
            body = await request.json()
            ids = sorted(self.jobs.get(body.get("jobId"), set()))
            return {"success": True, "results": [{"id": f"app-{i}", "candidate": {"id": i}} for i in ids], "moreDataAvailable": False, "nextCursor": None}

        @self.app.post("/file.info")
        async def info(request: Request, authorization: str | None = Header(default=None)):
            if not authed(authorization):
                return JSONResponse({"success": False}, 401)
            return {"success": True, "results": {"url": "http://127.0.0.1/files/resume.txt", "fileName": "resume.txt"}}


class WorkableMock:
    def __init__(self, token="wk-mock-token"):
        self.token, self.app = token, FastAPI()
        _files(self.app)
        self.people = [{"id": f"w{i}", "name": f"Sample Worker {i}", "email": f"w{i}@mail.example.test", "phone": "", "disqualified": i == 2, "resume_metadata": {"filename": "resume.txt"}, "shortcode": "SUP" if i <= 3 else "OPS"} for i in range(1, 6)]

        @self.app.get("/spi/v3/candidates")
        def lst(request: Request, authorization: str | None = Header(default=None)):
            if authorization != f"Bearer {self.token}":
                return JSONResponse({"error": "unauthorized"}, 401)
            start = int(request.query_params.get("since_id", "0"))
            code = request.query_params.get("shortcode") or request.query_params.get("job")
            pool = [p for p in self.people if not code or p["shortcode"] == code]
            page = pool[start:start + 2]
            nxt = f"http://testserver/spi/v3/candidates?since_id={start + 2}&shortcode={code}" if code and start + 2 < len(pool) else f"http://testserver/spi/v3/candidates?since_id={start + 2}" if start + 2 < len(pool) else None
            return {"candidates": page, "paging": {"next": nxt} if nxt else {}}

        @self.app.get("/spi/v3/candidates/{cid}")
        def one(cid: str, authorization: str | None = Header(default=None)):
            if authorization != f"Bearer {self.token}":
                return JSONResponse({"error": "unauthorized"}, 401)
            return {"candidate": {"id": cid, "resume_url": "http://127.0.0.1/files/resume.txt"}}


class GreenhouseMock:
    def __init__(self, token="gh-mock-token"):
        self.token, self.app = token, FastAPI()
        _files(self.app)
        self.people = [{"id": i, "first_name": "Sample", "last_name": f"Hire{i}", "email_addresses": [{"value": f"g{i}@mail.example.test"}], "phone_numbers": [], "attachments": [{"type": "resume", "filename": "resume.txt", "url": "http://127.0.0.1/files/resume.txt"}], "jobs": [{"id": 77 if i <= 3 else 88}]} for i in range(1, 6)]

        @self.app.get("/v1/candidates")
        def lst(request: Request, response: Response, authorization: str | None = Header(default=None)):
            if authorization != "Basic " + base64.b64encode(f"{self.token}:".encode()).decode():
                return JSONResponse({"message": "unauthorized"}, 401)
            page = int(request.query_params.get("page", "1"))
            per = 2
            job = request.query_params.get("job_id")
            pool = [p for p in self.people if not job or any(str(j["id"]) == job for j in p["jobs"])]
            if page * per < len(pool):
                response.headers["Link"] = f'<http://testserver/v1/candidates?page={page + 1}&per_page={per}' + (f"&job_id={job}" if job else "") + '>; rel="next"'
            return pool[(page - 1) * per:page * per]


class CalComMock:
    def __init__(self, key="cal-mock-key"):
        self.key, self.bookings, self.app = key, [], FastAPI()

        @self.app.get("/me")
        def me(authorization: str | None = Header(default=None)):
            return {"data": {"id": 1}} if authorization == f"Bearer {self.key}" else JSONResponse({"error": "unauthorized"}, 401)

        @self.app.post("/bookings")
        async def book(request: Request, authorization: str | None = Header(default=None), cal_api_version: str | None = Header(default=None)):
            if authorization != f"Bearer {self.key}":
                return JSONResponse({"error": "unauthorized"}, 401)
            body = await request.json()
            if not cal_api_version or not body.get("attendee", {}).get("email") or not body.get("start", "").endswith("Z"):
                return JSONResponse({"error": "bad body"}, 400)
            self.bookings.append(body)
            return {"status": "success", "data": {"uid": f"bk-{len(self.bookings)}"}}


class GoogleCalendarMock:
    def __init__(self, token="gcal-mock-token"):
        self.token, self.events, self.app = token, [], FastAPI()

        @self.app.get("/calendars/{cal}")
        def cal(cal: str, authorization: str | None = Header(default=None)):
            return {"id": cal} if authorization == f"Bearer {self.token}" else JSONResponse({"error": "unauthorized"}, 401)

        @self.app.post("/calendars/{cal}/events")
        async def ins(cal: str, request: Request, authorization: str | None = Header(default=None)):
            if authorization != f"Bearer {self.token}":
                return JSONResponse({"error": "unauthorized"}, 401)
            body = await request.json()
            if not body.get("start", {}).get("dateTime") or not body.get("end", {}).get("dateTime"):
                return JSONResponse({"error": "bad body"}, 400)
            self.events.append({**body, "query": dict(request.query_params)})
            return {"id": f"ev-{len(self.events)}"}
