#!/usr/bin/env python3
"""Write the four sample application emails the demo receives one by one when you press Run now.

  python3 tools/make_inbox.py
Everything is generated sample data. The files go to data/seed/inbox/.
"""
from __future__ import annotations

from email.message import EmailMessage
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "data" / "seed" / "inbox"
MAILS = [
    ("Wrenna Calloway", "wrenna.calloway@mail.example.test", "support", "Customer Support Specialist",
     "Summary\nI like writing clear answers to customers and fixing the cause of a problem.\n\nExperience\nCustomer Support Specialist, Brightwater Co, 2021 to 2026\n* Wrote replies to customer emails every day and trained 2 colleagues on tone and wording.\n* Investigated faults in the ticket queue, traced the root cause in the logs and wrote the fix into a help article.\n* Calmed upset customers on heated calls and cut repeat complaints by 12 percent.\n\nEducation\nDiploma, Ashgrove State College, 2019\n"),
    ("Tavish Oyelaran", "tavish.oyelaran@mail.example.test", "ops", "Operations Coordinator",
     "Summary\nI keep the week running: schedules, suppliers and the numbers.\n\nExperience\nCoordinator, Marlow and Finch Supply, 2020 to 2026\n* Built the weekly schedule and shift rota for 14 people.\n* Negotiated supplier quotes and saved about 9 percent on orders.\n* Kept the stock spreadsheet and a checklist for the returns procedure.\n\nEducation\nB.Sc., Fenwick College of Commerce, 2018\n"),
    ("Imara Delacroix-Hunt", "imara.delacroixhunt@mail.example.test", "analyst", "Data Analyst",
     "Summary\nAnalyst who likes plain explanations of what the numbers say.\n\nExperience\nData Analyst, Hearthstone Clinics, 2022 to 2026\n* Wrote SQL queries and joins on the warehouse database every week.\n* Built dashboards and charts in Tableau and explained results to stakeholders with a clear recommendation.\n* Cleaned data, removed duplicates and added validation checks.\n\nEducation\nB.A., Northmere Institute of Technology, 2021\n"),
    ("Corin Ashdown", "corin.ashdown@mail.example.test", "support", "Customer Support Specialist",
     "Summary\nNew to support, keen to learn.\n\nExperience\nShop assistant, Tidewell Logistics, 2023 to 2026\n* Took care of routine customer emails each week.\n* Observed how the helpdesk is used and read the help articles.\n\nEducation\nDiploma, Tallis Heath College, 2022\n"),
]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for i, (name, addr, role, title, body) in enumerate(MAILS, 1):
        m = EmailMessage()
        m["From"], m["To"], m["Subject"], m["Message-ID"], m["Date"] = f"{name} <{addr}>", "jobs@example.test", f"Application for {title}", f"<inbox-{i}@mail.example.test>", "Tue, 01 Dec 2026 09:00:00 +0000"
        m.set_content(f"{name}\n{addr}\n\n{body}")
        (OUT / f"{i:02d}-{role}.eml").write_bytes(bytes(m))
    print("wrote", len(MAILS), "emails to", OUT)


if __name__ == "__main__":
    main()
