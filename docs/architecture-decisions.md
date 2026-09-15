# SPS Analytics Filing: Architecture Decisions

Why the system is shaped the way it is, and what was considered and rejected along the way.

This exists so a decision does not get re-litigated in six months by someone who was not in the conversation, and so the rejected options are on the record with their actual reasons rather than being rediscovered the hard way.

Full detail lives in the [design guide](sps-analytics-filing-flow-build-guide.md) and the [deployment guide](azure-function-build-guide.md). This page is the index and the reasoning.

---

## 1. Decisions

| # | Decision | Why, in one line | Detail |
| --- | --- | --- | --- |
| 1 | Four folder levels, `{YYYY}/{Retailer}/{NN Family}/{Brand}/` | Three levels puts ~624 files a year in one folder against a ceiling of 53 | Design guide 1.1 |
| 2 | Filename date is the retail week-ending Saturday, not the received date | A resend arriving a day later must resolve to the same filename | Design guide 1.2 |
| 3 | Overwrite on filename collision, library versioning on | A resend is nearly always a correction; versions do not count toward the folder ceiling | Design guide 1.4 |
| 4 | `SourceMessageId` is a replay guard, not the dedupe key | A resend is a new message with a new id, so an id check can never detect one | Design guide 1.4 |
| 5 | Mapping table in a SharePoint list | The analytics team adds a retailer without anyone touching code | Design guide 1.5 |
| 6 | One list with a `MapType` column, not four lists | One place to manage, and one read per run instead of four | Design guide 1.5 |
| 7 | Subject wins over attachment filename | The attachment name is a lossy copy of the subject and carries no date | Design guide 1.6 |
| 8 | Calendar year in the folder path, fiscal exposed as columns | Folder and filename agree; the fiscal view is a cross-cutting question, which is what views are for | Design guide 1.1 |
| 9 | Runtime is an Azure Function App | See rejected option A below | Deployment guide 1 |
| 10 | Backfill is an exported copy, deleted after go-live | Nothing else runs the parser on an ongoing basis, so no second copy survives to drift | Design guide 8.1 |
| 11 | The weekly control report stays in Power Automate | Four trivial actions; moving it would mean granting `Mail.Send` for no benefit | Deployment guide 1 |
| 12 | Non-sortable date rewriting is not built | Zero of 1,001 audited attachments carry any date | Design guide 6.9 |

### Superseded artifacts, kept deliberately

- **`docs/sps-fiscal-calendar-454.csv`** is no longer needed by the running system: `src/sps_filing/dates.py` computes the 4-5-4 calendar from the NRF rule. The CSV is retained as a human-readable reference and for anyone rebuilding this on Power Automate, where the calendar cannot be derived in an expression.
- **The Power Automate build guide** is retained as the reference specification of the parsing rules. Its sections 4 and 5 are still the source of truth for normalization and matching; its WDL expressions are no longer the implementation.

---

## 2. Rejected alternatives

### A. Power Automate, end to end

**Status:** built and fully specified, then superseded once IT committed to owning a Function App long term.

Three things drove the move:

1. **Power Automate has no regex.** Subject normalization needed a `Select` action walking the string one character at a time against an allowlist, and a `<>` / `><` substitution trick to collapse whitespace. Both work. Neither is readable, and neither can be unit tested.
2. **The parser could not be tested.** The nine-subject trace table had to be verified by sending nine emails and looking at the result. It is now `tests/test_trace_table.py` and runs in 0.15 seconds.
3. **Backfill needed a second copy of the parser**, and two copies of a parser drift.

The move immediately paid for itself: writing the tests caught a bug the Power Automate design shared, where normalizing a match token through the full subject pipeline strips a leading digit. `4-5-4 Calendar` became `5 4 CALENDAR`, the token stopped matching, and every Macys 4-5-4 rollup would have silently lost its calendar segment.

### B. Power Automate saves attachments to a staging folder, a Claude Agent organizes them

**Status:** rejected. This is the most attractive-looking option and the one most likely to be proposed again, so here is the full reasoning.

**It loses the data at the boundary.** The attachment filename is not an identifier for this feed:

- Five separate Dillards Qlik feeds carry the brand only in the subject (RL, LB PB, MG, MS, VA). Every one attaches a file named exactly `DILLARDS Qlik Sell Thru Sales Report.txt`.
- Zero of 1,001 audited attachments carry a date.

So the moment a file is saved to a staging folder, the information needed to file it stops existing. Those five Dillards files would collide on write and overwrite each other. Nothing downstream, a model included, can recover what was never carried across.

That is fixable: the staging step has to carry the subject, received date and message id forward, in the staging filename or a sidecar. But once you have done that, the "thin" flow still has the trigger, the attachment filter, the inline-image filter, the metadata capture and the write. You have kept most of the Power Automate surface and added a second system.

**It puts a non-deterministic component on a path that requires determinism.** The one-file-per-reporting-week rule depends on the same subject producing a byte-identical filename every time. A model that writes `ALL-DIVISIONS` one week and `ALLDIVISIONS` the next silently breaks the overwrite rule, and the folder starts accumulating with no error anywhere. The rules here are deterministic lookup tables with priority ordering, which is the one job a language model does worse than a `Filter array`.

**Where a model would genuinely earn its place**, and the obvious next thing to build if the unclassified pile ever becomes annoying: triaging `_Unclassified`. Reading an unmatched subject and proposing the mapping row that would fix it is fuzzy judgment, which deterministic rules cannot do. It is low volume, has no determinism requirement, and costs nothing across 10,400 messages a year because it only ever sees the handful that failed.

### C. Hybrid: Power Automate trigger and SharePoint write, one Azure Function for the parse

**Status:** rejected only because IT committed to owning a Function App. This was the recommendation until that point, and it is the right answer if that commitment ever lapses.

The appeal is that the Function is a pure function over three strings: subject, received date, attachment name. It never touches the mailbox or SharePoint, so it needs **no tenant permissions at all**. No app registration, no Exchange RBAC, no `Sites.Selected` grant. All of the identity work in deployment guide section 3 simply does not apply.

It cuts the flow from about 30 actions to 8 and deletes every unreadable expression, while keeping the one thing Power Automate is genuinely good at: watching a shared mailbox reliably with zero infrastructure. Calling it needs the HTTP action, which is premium, but the Premium licence is already budgeted for the flow owner.

### D. Azure Automation PowerShell runbook

**Status:** rejected, but a reasonable fallback for a PowerShell-shaped team.

Managed identity, built-in scheduling, and built-in job history that replaces Power Automate's run history without needing Application Insights wired up. Rejected because the work is string manipulation, which is cleaner in Python, and because the testing story is worse.

### E. GitHub Actions on a cron

**Status:** rejected for the standing job.

Tempting because the repository already exists and CI already runs there. Rejected because scheduled workflow runs are delayed or skipped under load, which is not acceptable for production data movement, and because secret handling is worse than a managed identity. Fine for a one-off backfill.

### F. A dedicated SharePoint library instead of a folder in Documents

**Status:** rejected in favour of the path Dave specified.

The original spec recommended a dedicated **SPS Analytics Reports** library so retention and permissions scope cleanly. Filing into `Documents/02 - Sales/05 - Published Reports` is more discoverable where the sales team already works, and the two real risks turned out to be manageable: retention is confirmed at three years, which suits a weekly reporting feed, and the 5,000-item view threshold is handled by indexing five columns on day one.

Worth revisiting only if a retention policy on `Documents` ever conflicts.

### G. Fiscal year in the folder path

**Status:** rejected, recorded because it is a fair argument.

Merchandising thinks in fiscal years, these are fiscal-period reports, and a fiscal year holds exactly 52 or 53 weeks by construction rather than by coincidence. Against that: FY2026 ends 2027-01-30, so five weeks of every fiscal year fall in the next calendar year, and a folder named `2026` would contain a file dated `2027-01-30`, which reads as wrong to anyone outside merchandising. The `By Fiscal Week` view serves that audience instead.

It is a one-expression change, documented in design guide 1.1, but only worth making before history is filed.
