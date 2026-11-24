"""Rubric vocabulary for the offline scorer (look_for terms) and the phrases the seed resumes use. Developer data, not held out."""

TERMS = {
    "cs_written": ["email", "reply", "replies", "written", "wrote", "writing", "response", "message", "correspondence", "letter", "tone", "wording", "answer"],
    "cs_diagnosis": ["troubleshoot", "diagnos", "root cause", "root-cause", "cause of", "investigat", "debug", "logs", "fault", "narrow", "trace", "fix"],
    "cs_tools": ["ticket", "helpdesk", "help desk", "zendesk", "intercom", "freshdesk", "crm", "knowledge base", "live chat", "queue", "inbox", "wiki", "platform", "saved repl", "macro"],
    "cs_deescalate": ["upset", "angry", "complaint", "de-escalat", "calm", "frustrat", "difficult customer", "escalat", "dispute", "heated", "apolog"],
    "cs_improve": ["improv", "process", "help article", "help page", "documentation", "feedback", "report", "template", "reduce", "streamlin", "workflow"],
    "ops_schedule": ["schedule", "scheduling", "calendar", "shift", "rota", "timetable", "plan", "dispatch", "coordinat", "deliver", "logistic"],
    "ops_vendor": ["vendor", "supplier", "contract", "negotiat", "purchase order", "quote", "procure", "orders"],
    "ops_data": ["spreadsheet", "excel", "sheet", "pivot", "formula", "tracker", "tracking", "report", "inventory", "stock", "dashboard", "workbook"],
    "ops_process": ["procedure", "process", "standard operating", "sop", "checklist", "step-by-step", "routine", "instructions", "documented", "workflow"],
    "ops_budget": ["budget", "cost", "spend", "saving", "expense", "invoice", "forecast", "overcharge"],
    "da_sql": ["sql", "query", "queries", "join", "database", "postgres", "mysql", "warehouse", "aggregat"],
    "da_viz": ["dashboard", "chart", "visuali", "tableau", "power bi", "bi tool", "looker", "graph", "plot", "report"],
    "da_stats": ["statistic", "significance", "regression", "a/b", "experiment", "hypothesis", "confidence", "probability", "forecast", "test"],
    "da_clean": ["clean", "duplicate", "validation", "data quality", "missing value", "outlier", "audit", "wrong", "format"],
    "da_story": ["present", "explain", "stakeholder", "executive", "recommend", "story", "non-technical", "briefed", "slides", "communicat", "plain language"],
}

# (short phrase with one matching term, long phrase with three)
SUBJECTS = {
    "cs_written": ("customer emails", "customer emails with written replies in a friendly tone"),
    "cs_diagnosis": ("troubleshooting", "troubleshooting and root cause investigation of faults"),
    "cs_tools": ("the helpdesk", "the ticket queue, helpdesk and knowledge base"),
    "cs_deescalate": ("upset customers", "angry customers and heated complaint calls with calm apologies"),
    "cs_improve": ("the support process", "the support process, help articles and feedback templates"),
    "ops_schedule": ("the weekly schedule", "the weekly schedule, shift rota and delivery timetable"),
    "ops_vendor": ("supplier calls", "supplier contracts, quotes and negotiation"),
    "ops_data": ("the stock sheet", "the stock spreadsheet, pivot tables and formulas"),
    "ops_process": ("the returns procedure", "the returns procedure with a checklist and step-by-step instructions"),
    "ops_budget": ("the monthly budget", "the monthly budget, cost sheet and expense forecast"),
    "da_sql": ("SQL queries", "SQL queries, joins and aggregations on the warehouse database"),
    "da_viz": ("weekly charts", "dashboards, charts and visualizations in Tableau"),
    "da_stats": ("simple statistics", "statistics, significance tests and experiment design"),
    "da_clean": ("cleaning exports", "cleaning data, removing duplicates and validation checks"),
    "da_story": ("monthly slides", "presenting and explaining results to stakeholders with a clear recommendation"),
}

TEMPLATES = {
    1: ["Observed {s} during my first weeks and read about how it is done.", "Shadowed a senior colleague who handled {s}."],
    2: ["Handled routine {s} every day.", "Took care of routine {s} each week."],
    3: ["Handled {s} independently every day.", "Responsible for {s} across the team, every week."],
    4: ["Improved {s}, which cut errors by {n} percent.", "Redesigned {s} and reduced handling time by {n} percent."],
    5: ["Led {s} for a team of {k}, trained {m} colleagues and owned the results, cutting errors by {n} percent.", "Built and led {s} for {k} people, coached {m} new hires and saved about {n} hours a week."],
}
FILLER = ["Organised the team lunch rota.", "Covered the front desk during holiday weeks.", "Took part in the quarterly safety walk.", "Welcomed visitors and signed them in."]
