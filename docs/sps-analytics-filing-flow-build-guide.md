# SPS Analytics Filing Flow: Build Guide

Power Automate cloud flow that files every report emailed to `sps-analytics@swimusa.com` into the Swim USA CompanyHub SharePoint library, organized and named so a business user can find any report in seconds.

**Destination:** `https://mainstreamswimsuits.sharepoint.com/sites/CompanyHub/Shared Documents/02 - Sales/05 - Published Reports`

**Status:** design complete, ready to build. Every expression below is paste-ready Power Automate workflow definition language (WDL).

---

## 0. Sources, and what I had to assume

### What I worked from

| Document | Status | Role |
| --- | --- | --- |
| `sps-filing-flow-spec_2.md` | Received | Primary design reference |
| `sps-filing-flow-spec_1.md` | **Same file**, confirmed 2026-09-14 | No separate content |
| Mailbox audit findings | **Embedded in the spec** | Section 1, "Observed reality" |

There is one source document, not three, and nothing to reconcile. `_1` and `_2` are the same file downloaded twice.

The mailbox audit is not separate either: section 1 of the spec ("Observed reality") **is** the audit. It states that it comes from "a full read of all 1,001 messages in the mailbox on 2026-09-14, covering receipts from 2026-08-11 forward," and it carries the sender breakdown, volumes, subject-line patterns, attachment names, retailer list, report families, brands and calendars. That is everything this build needs.

So this guide is built against a single, confirmed source of truth.

### Assumptions I made, flagged

| # | Assumption | Why | If wrong |
| --- | --- | --- | --- |
| A1 | *(resolved)* `_1` and `_2` are the same file | Confirmed 2026-09-14 | No longer an assumption |
| A2 | *(confirmed)* Retail week ends **Saturday** | NRF 4-5-4 weeks run Sunday to Saturday | No longer an assumption |
| A3 | Mailbox timezone reference is `America/New_York` | Stated in spec section 3 | Change the `convertTimeZone` argument |
| A4 | The destination is a folder inside the existing **Documents** library, not a new library | That is what the URL you gave resolves to | See section 2.1 for the trade-off |
| A5 | Exactly one report attachment per message, but the flow must tolerate N | Spec: "Exactly 1 in every message sampled" | Already handled, no change |
| A6 | The four SPS non-report senders are the complete admin set | Spec section 1 | Add rows to the map, no flow edit |

---

## 1. The six decisions that shape this build

Read this section first. Everything after it is mechanics.

### 1.1 Folder structure: keep four levels, not three

You asked for `year > retailer > report name`. The spec proposes `{YYYY}/{Retailer}/{NN Report Family}/{Brand}/`. **Use the spec's four levels.** Here is the arithmetic that settles it.

Your own requirement is the constraint: *a folder for a weekly report must contain no more than 53 files at the end of the year.*

| Structure | Example folder | Files per year |
| --- | --- | --- |
| Three levels (your ask) | `2026/Dillards/02 Weekly Trend/` | ~12 brands x 52 weeks = **~624** |
| Four levels (spec) | `2026/Dillards/02 Weekly Trend/Lauren/` | 1 per week = **52 or 53** |

These reports are issued per retailer **and** per brand. Dillards alone carries seven brands in Style Selling. Three levels breaks the ceiling by a factor of twelve; four levels hits it exactly.

**How to think about the merge, rather than as a compromise:** what a business user calls "the report name" is really the report *series* identity, and for this feed that identity is two things, the report family and the brand. Splitting it across two folder levels is not an extra layer of bureaucracy, it is the report name spelled out. "Dillards Weekly Trend for Lauren" reads straight off the path.

A maximum of 53 Saturdays can occur in a calendar year (2028 and 2033 are the next 53-week years), so the ceiling is met with zero margin to spare and no margin needed.

Two refinements on top of the spec:

- **Keep the brand level even when there is only one brand.** Returns and Division Rollups always resolve to `All Brands` or `All Divisions`, so that folder looks redundant. Keep it anyway: one code path in the flow, predictable paths for anyone writing a link or a Power BI source, and if a retailer ever starts splitting Returns by brand the structure absorbs it without stranding history.
- **Keep the `NN` numeric prefixes.** They mirror SPS's own subject numbering and sort the folders into the order an analyst reads them rather than alphabetically.

Final structure:

```
/02 - Sales/05 - Published Reports/
├── 2026/
│   ├── Dillards/
│   │   ├── 01 Style Selling/       {Brand}/
│   │   ├── 02 Weekly Trend/        {Brand}/
│   │   ├── 03 Period To-Date/      {Brand}/
│   │   ├── 04 Door Performance/    {Brand}/
│   │   ├── 06 Qlik Sell Thru/      {Brand Code}/
│   │   ├── 07 Returns/             All Brands/
│   │   └── 08 Division Rollups/    All Divisions/
│   ├── Kohls/  Macys/  Belk/  ... 11 more
│   └── _Cross-Retailer/            ALL RETAILERS, TOP 6 ACCTS
├── 2027/
├── _Unclassified/{YYYY-MM}/        parser could not route
└── _Admin/{YYYY}/                  non-report mail
```

Two deviations from the spec's tree, both deliberate:

- **`_Cross-Retailer` sits under the year.** The spec contradicts itself here: section 2's tree draws `_Cross-Retailer/` as a sibling of the retailers under `2026/`, but its folder rules say `_Cross-Retailer/{YYYY}/...`, which puts the year second. Year-first is consistent with every other path, so use `{YYYY}/_Cross-Retailer/{Family}/{Brand}/`.
- **`_Admin` is year-scoped.** The spec says not year-scoped. At roughly 40 admin messages a year that folder grows slowly but forever, and there is no reason for it to be the one folder in the library that behaves differently. Use `_Admin/{YYYY}/`.

**`{YYYY}` is the calendar year.** Decided. The confirmed fiscal calendar made this a real question, because the two no longer coincide.

Now that the 4-5-4 rule is pinned down (section 2.3), the two no longer line up. FY2026 runs 2026-02-01 to 2027-01-30, so its last five weeks fall in calendar 2027:

| Week ending | Fiscal week | Calendar-year folder | Fiscal-year folder |
| --- | --- | --- | --- |
| 2027-01-02 | 2026-W48 | `2027/` | `2026/` |
| 2027-01-09 | 2026-W49 | `2027/` | `2026/` |
| 2027-01-16 | 2026-W50 | `2027/` | `2026/` |
| 2027-01-23 | 2026-W51 | `2027/` | `2026/` |
| 2027-01-30 | 2026-W52 | `2027/` | `2026/` |

The folder path carries the **calendar year**, and `FiscalYear` and `FiscalWeek` answer the fiscal question as columns instead.

Three reasons. The filename already carries a calendar date, so folder and filename agree and a browsing user is never confronted with `2027-01-30_...xlsx` sitting in a folder called `2026`. It is unambiguous to everyone, including IT and anyone outside merchandising who has no reason to know when the fiscal year turns. And it is the same argument section 2.4 already makes: folders give a path to walk, views answer the cross-cutting questions, and "all of FY2026" is a cross-cutting question.

The counter-argument, recorded because it is a fair one: merchandising thinks in fiscal years, these are fiscal-period reports, and a fiscal year holds exactly 52 or 53 weeks by construction rather than by coincidence. The `By Fiscal Week` view in section 2.4 is what serves that audience.

If you ever revisit this, it is a one-expression change: move `Filter array Fiscal Week` (section 6.9) above `Compose Folder Path` and replace `Compose Filing Year` with:

```
first(split(coalesce(first(body('Filter_array_Fiscal_Week'))?['OutputCode'], concat(formatDateTime(outputs('Compose_Week_Ending'), 'yyyy'), '-W00')), '-'))
```

Revisit it **only before the backfill**. Once history is filed, changing it means moving files between year folders and rewriting every link anyone has saved.

### 1.2 Filename date: use the week-ending Saturday, not the received date

This is the most important change I am recommending, because it is what actually makes the 53-file ceiling hold.

The spec's filename grammar uses the **message received date**. That fails your resend requirement, and here is the concrete case, drawn from real dates in the audit:

> Macys all-divisions rollup arrives Sunday **2026-09-13**. SPS resends a corrected copy Monday **2026-09-14**. Both cover the retail week ending Saturday 2026-09-12.
>
> Under received-date naming you get `2026-09-13_MACYS_...xlsx` and `2026-09-14_MACYS_...xlsx`. **Two files, one reporting week.** Do that a dozen times a year and the folder is over the ceiling with duplicate data in it.

Anchoring the filename to the week-ending Saturday collapses both to `2026-09-12_MACYS_...xlsx`, which means the resend targets the same filename and the overwrite rule (section 1.4) handles it. One file per reporting week, by construction.

It also satisfies your stated preference directly. You asked for "report period date where derivable, falling back to email received date." The week-ending Saturday **is** the report period date, derived from the received date. It is more correct than the received date, not merely more convenient.

Validated arithmetic, using the audit's own receipt dates:

| Received | Weekday | Week ending | Filing year |
| --- | --- | --- | --- |
| 2026-09-07 | Mon | 2026-09-05 | 2026 |
| 2026-09-08 | Tue | 2026-09-05 | 2026 |
| 2026-09-13 | Sun | 2026-09-12 | 2026 |
| 2026-09-14 | Mon | 2026-09-12 | 2026 |
| 2026-01-01 | Thu | 2025-12-27 | **2025** |

That last row is the payoff at the year boundary: a report arriving New Year's Day covers a 2025 week and files under 2025, where an analyst would look for it.

**This also corrects the spec's `FiscalWeek` column.** The spec defines it as the ISO week of the received date. ISO weeks start Monday, so the Sunday and Monday deliveries above land in ISO weeks 37 and 38 respectively, splitting one reporting week across two. Retail weeks start Sunday. Section 2.3 covers what to use instead.

### 1.3 Filename grammar: keep the spec's, with the date redefined

```
{YYYY-MM-DD}_{RETAILER}_{BRAND}_{REPORT}[_{CALENDAR}].{ext}
```

Unchanged from the spec except that `{YYYY-MM-DD}` is now the week-ending Saturday. The optional `_{CALENDAR}` segment is not optional in spirit: Macys sends the same all-divisions numbers on three calendars, and dropping the segment collides two genuinely different reports onto one filename. Treat a missing calendar segment as a bug, not a cosmetic issue.

Monthly families use `{YYYY-MM}`, driven by a `Cadence` column in the mapping list. No family in the current feed is monthly, so this is inert today and exists so that adding one is a data change.

**One correction to the spec's extension rule.** The spec hardcodes `.xlsx` for every family except Qlik Sell Thru. Do not do this. Take the extension from the actual attachment. The spec is right that `attachment.name` is worthless for *identity* (it repeats the subject, carries no date, and loses the brand entirely on Qlik feeds), but the extension is the one part of it that is authoritative, because it describes the bytes you were actually sent. Hardcoding means the day SPS switches Qlik from `.txt` to `.csv` you silently write a mislabeled file.

### 1.4 Duplicates and resends: overwrite, with versioning on, and `SourceMessageId` demoted

**`SourceMessageId` is not sufficient to detect resends, and the spec's reliance on it is the second defect worth fixing.**

`internetMessageId` is unique per message. A resend is a *new message* with a *new* id. So an id-based check will never fire on a resend, which is precisely the case the 53-file ceiling is about. What the id check actually catches is the same message being processed twice, which happens during backfill overlap, a manual resubmit, or the trigger's documented tendency to re-fire on older mail that gets moved between folders. That is worth catching, it is just a different problem.

Use both, layered:

| Layer | Key | Catches | Action |
| --- | --- | --- | --- |
| 1 | Target filename already exists | **Resends and corrections** | Overwrite, new version |
| 2 | Existing file's `SourceMessageId` equals this message's | Replays, backfill overlap, resubmits | Skip, no write, no version |

**Recommendation: overwrite, not skip, not version-as-new-file.**

| Option | Verdict |
| --- | --- |
| **Overwrite** (recommended) | A resend is nearly always a correction. The corrected data wins. SharePoint versioning keeps the prior copy for audit, and **versions do not count as files in the folder**, so the ceiling is untouched. |
| Skip | Leaves known-bad data in place and silently discards the correction. Worst option. |
| Version as a new file (`_v2` suffix) | Breaks the ceiling, which is the requirement you started from. |

Turn on versioning with a **500-version limit** on the library (section 2.1). At one or two writes per file per year, 500 is effectively unlimited and costs nothing until used.

Note the mechanical detail that shapes the flow: the SharePoint **Create file** action does *not* overwrite. It fails with "a file with the name X already exists." There is a community trick involving disabling chunking to expose an Overwrite toggle, but it is undocumented and fragile. The documented, deterministic pattern is to branch: **Create file** when the path is free, **Update file** when it is taken. Update file replaces the content and creates a version. That is what section 6.9 builds.

### 1.5 Where the mapping lives: one SharePoint list, not four, and not inline

**Recommendation: a single SharePoint list named `SPS Filing Map` in the CompanyHub site, with a `MapType` column.**

On the three options you raised:

- **Microsoft List vs SharePoint list is not a real choice.** They are the same object. Microsoft Lists is a front end over SharePoint lists. A list created in either place is reachable by the SharePoint connector. So the question is really list versus inline, and the answer is list.
- **Inline (a Compose holding a JSON array)** is fastest at runtime and costs zero connector calls, but adding a retailer means editing and republishing production flow logic. That directly violates your requirement that new retailers be addable without touching the flow. Rejected.
- **Dataverse** would give better typing and proper choice columns, but it needs premium licensing for anyone who maintains it, and you do not need what it buys here. Rejected on cost.

**Why one list rather than four.** Two reasons, and the first is the one that matters:

1. **Power Platform request budget.** Four `Get items` calls per run against roughly 10,400 messages a year is about 31,000 extra requests a year, and the peak matters more than the total: SPS delivers roughly 200 messages a week concentrated on Sunday through Tuesday. A Microsoft 365 licence grants **6,000 Power Platform requests per user per 24 hours** and the flow's consumption bills to the *owner*, not the connection. One `Get items` instead of four keeps a heavy delivery day comfortably inside budget. See section 3.2, this is the single most likely operational failure mode and it is worth engineering out up front.
2. One place for your team to look, one set of permissions, one version history.

The cost is a `MapType` column and slightly longer filter expressions. Worth it.

### 1.6 Subject wins over attachment filename, always

You asked what happens when subject keywords and attachment filename patterns disagree. For this feed the answer is unusually clear cut, and the audit proves it:

> Five separate Dillards Qlik feeds carry brand codes RL, LB PB, MG, MS and VA in the subject. Every one of them attaches a file named exactly `DILLARDS Qlik Sell Thru Sales Report.txt`. The brand exists nowhere in the attachment.

And:

> The Dillards style-selling file from 2026-09-14 and the one from 2026-09-07 are both named `1. SALES - CONTROL BRANDS DILLARDS STYLE SELLING To-Date Analysis.xlsx`. Zero of 1,001 attachments carry a date.

So the attachment filename is a lossy copy of the subject. The precedence rule:

| Field | Source of truth | Attachment's role |
| --- | --- | --- |
| Retailer | Subject | Fallback only if the subject yields no retailer |
| Report family | Subject | Fallback only if the subject yields no family |
| Brand | Subject | None. Never trust it. |
| Calendar | Subject | None |
| Date | Derived (section 1.2) | Used only if it carries a sortable date |
| **Extension** | **Attachment** | **Authoritative** |

When the fallback fires and the attachment disagrees with a subject value that *did* match, the subject wins and the flow writes `ParseConflict = true` on the file. That surfaces in the weekly control report so a human sees drift rather than the flow guessing silently. This is deliberately not an error: the file still lands in the right folder, it is just flagged for a look.

---

## 2. Step 1: Set up the destination

### 2.1 Confirm or swap the library, and where the path is configured

Your URL decomposes like this, and these three values are what you will type into the flow:

| Flow field | Value | Notes |
| --- | --- | --- |
| **Site Address** | `https://mainstreamswimsuits.sharepoint.com/sites/CompanyHub` | Site only. No library, no folder. |
| **Library (display name)** | `Documents` | What the picker shows |
| **Library (URL name)** | `Shared Documents` | What path strings must use |
| **Root folder path** | `/02 - Sales/05 - Published Reports` | Relative to the library root |

The display-name vs URL-name split is the single most common way this gets misconfigured, because the two SharePoint actions want different things:

| Action | Field | Value to enter |
| --- | --- | --- |
| **Create file** | Folder Path | `/Shared Documents/02 - Sales/05 - Published Reports/...` (**includes** the library) |
| **Create new folder** | List or Library | `Documents` (pick from dropdown) |
| **Create new folder** | Folder Path | `02 - Sales/05 - Published Reports/...` (**excludes** the library) |
| **Get file metadata using path** | File Path | `/Shared Documents/02 - Sales/05 - Published Reports/...` (**includes** the library) |

Microsoft's own parameter description for Create file is "Must start with an existing library," which is the rule to remember.

To swap the destination later, change the single Compose action `Compose Library Root` (section 6.6) and nothing else. Every path in the flow is built from it.

**The trade-off you are accepting (assumption A4).** The spec recommends a dedicated **SPS Analytics Reports** library rather than a folder inside Documents, so that retention and permissions scope cleanly. Your URL points at a folder inside the existing Documents library. Filing into an existing library is perfectly workable, and these are the three consequences:

1. **Retention and permissions are inherited** from Documents, which is confirmed to retain **3 years of history**. That is compatible with this design: reports age out on a rolling three-year window, which is what you want for a weekly reporting feed. No conflict, so the library choice stands.
2. **The 5,000-item list view threshold applies to the whole library**, not to your folder. Nested folders keep per-folder views fine, but any *flat* view or filter across the library needs indexed columns, and the three-year window makes this a certainty rather than a risk. See the volume table below.
3. Versioning settings are library-wide, so turning on the 500-version limit affects all of Documents.

**What three-year retention means in numbers.** At ~10,400 files a year, the report tree reaches a steady state of roughly **31,200 files**, plus whatever else already lives in Documents. The backfill (section 8.2) contributes 1,001 of those on day one.

| Milestone | Item count | Reached at roughly | Consequence |
| --- | --- | --- | --- |
| List view threshold | 5,000 | **month 5** | Unindexed flat views and OData filters start failing |
| Index-creation lockout | 20,000 | **month 22** | **An index can no longer be added by hand** |
| Steady state | ~31,200 | year 3 | Holds flat from here |

The second row is the one with a deadline attached, and section 2.3 acts on it.

**My recommendation:** go with your path as given. The reporting library is more discoverable where the sales team already works, retention is now confirmed compatible, and the view threshold is handled by indexing on day one.

### 2.2 Create the root folders and turn on versioning

Create by hand, once:

```
/02 - Sales/05 - Published Reports/_Unclassified
/02 - Sales/05 - Published Reports/_Admin
```

Everything else is created by the flow on demand. You are not pre-building the year, retailer, family or brand folders.

Then, on the **Documents** library: **Settings > Versioning settings**

| Setting | Value |
| --- | --- |
| Document Version History | Create major versions |
| Keep the following number of major versions | **500** |
| Require documents to be checked out | **No** (checkout breaks automated writes) |

### 2.3 Add the metadata columns

The spec's column set is sound and I am keeping it with three changes: `FiscalWeek` is redefined, and three columns are added.

Create these on the Documents library (**Settings > Create column**), or on a dedicated content type if you prefer to keep Documents clean:

| Column | Type | Indexed | Source | Change from spec |
| --- | --- | --- | --- | --- |
| `Retailer` | Choice | **Yes** | parsed | |
| `Brand` | Choice | **Yes** | parsed | |
| `ReportFamily` | Choice | **Yes** | parsed | |
| `Calendar` | Choice: NRF, SUPPLIER, 454, (none) | No | parsed | |
| `ReceivedDate` | Date and Time | No | message received, Eastern | |
| `WeekEnding` | Date and Time | **Yes** | derived Saturday | **New** |
| `FiscalWeek` | Single line, `2026-W37` | No | retail week, not ISO | **Redefined** |
| `SourceSubject` | Multiple lines | No | normalized subject | |
| `SourceMessageId` | Single line | **Yes** | `internetMessageId` | |
| `SourceAttachmentName` | Single line | No | original attachment name | **New** |
| `ParseConflict` | Yes/No | No | subject vs attachment disagreed | **New** |

**Indexing is not optional, and it has a deadline.** Once the library passes 5,000 items, any view or OData filter on a non-indexed column is refused outright by SharePoint. Worse, **adding an index by hand is blocked above 20,000 items**, and the modern experience only auto-indexes below that figure.

With three-year retention this library passes 5,000 items around **month 5** and reaches **20,000 in roughly 22 months**, both sooner once existing Documents content is counted. After 20,000 the indexes in the table above cannot be created through the UI at all, and the weekly control report in section 9 (which filters on `WeekEnding`) stops working with no way to fix it short of a support path or restructuring the library.

**Create all five indexes before the first backfill chunk runs.** It costs five minutes on an empty library and cannot be undone cheaply later. This is the single highest-consequence five minutes in the whole build.

**On `FiscalWeek`.** Confirmed rule, and it is now built rather than deferred:

> NRF 4-5-4 weeks run **Sunday through Saturday**. The fiscal year ends on the **Saturday closest to 31 January**, and week 1 starts the following Sunday. A 53rd week falls out every five or six years.

That rule is fully deterministic, so the calendar is generated rather than transcribed. **`docs/sps-fiscal-calendar-454.csv` in this repository holds 209 ready-to-import rows covering FY2025 through FY2028**, in the exact column shape of the mapping list. Import it into `SPS Filing Map` and the lookup in section 6.9 works with no further effort.

| Fiscal year | Starts | Ends | Weeks |
| --- | --- | --- | --- |
| FY2025 | 2025-02-02 | 2026-01-31 | 52 |
| FY2026 | 2026-02-01 | 2027-01-30 | 52 |
| FY2027 | 2027-01-31 | 2028-01-29 | 52 |
| FY2028 | 2028-01-30 | 2029-02-03 | **53** |

The generated calendar reproduces the every-five-or-six-years pattern exactly: 53-week years land on FY2023, FY2028 and FY2034. Regenerate the CSV before FY2029 using the same rule.

> **Watch this, because it looks like a bug and is not.** The spec's example `FiscalWeek` value of `2026-W37` was an **ISO** week. Under 4-5-4 the same receipt is **`2026-W32`**, five weeks earlier, because the fiscal year starts in February rather than January. Week ending 2026-09-12 is fiscal week 32, not 37. Anyone comparing the flow's output against the spec will see the gap and assume the flow is wrong; it is the spec's example that predates the 4-5-4 decision.

### 2.4 Build the business-facing views

Folders give the team a path to walk. Views answer the questions a path cannot. Create these on the library, each filtered to the report root so `_Admin` noise stays out:

| View | Group by | Sort | Answers |
| --- | --- | --- | --- |
| **By Week** | `WeekEnding` desc | Retailer | "What landed for week ending 9/12?" |
| **By Brand** | `Brand` | `WeekEnding` desc | "Every Lauren report, all retailers" |
| **By Retailer** | `Retailer` | `WeekEnding` desc | "Everything Dillards sent" |
| **By Fiscal Week** | `FiscalWeek` desc | Retailer | "Everything for fiscal week 2026-W32" |
| **Needs Attention** | none | `ReceivedDate` desc | Filter: `ParseConflict = Yes` |

Every one of these filters or sorts on an indexed column. That is not a coincidence, it is why section 2.3 indexes what it indexes.

---

## 3. Step 2: Prerequisites

Do these before you open the designer. Two of them have lead time.

### 3.1 Mailbox permission (has a two-hour lag)

The trigger reads a shared mailbox the flow owner does not own. Microsoft's documented requirement:

> "The trigger won't work in cases of user-to-user shared mailboxes unless one of the users has **full access** to the other mailbox."

Grant **Full Access** on `sps-analytics@swimusa.com` to the account that will own the flow. Exchange admin center > Recipients > Mailboxes > `sps-analytics` > Delegation > Read and manage (Full Access). Or:

```powershell
Add-MailboxPermission -Identity "sps-analytics@swimusa.com" `
  -User "svc-sps-filing@swimusa.com" `
  -AccessRights FullAccess -InheritanceCopy:$false
```

Three things to know:

- **Permissions take about two hours to replicate** to the Power Platform. Grant access, then go do something else. Building the flow immediately and watching the trigger fail is a well-worn way to waste an afternoon.
- **Send As / Send on Behalf are not needed.** The flow only reads. Alerts are sent from the owner's own mailbox.
- The shared mailbox itself **does not need a licence** unless it exceeds 50 GB or is placed on litigation hold. At ~10,000 messages a year with attachments, watch the 50 GB line. It is not close today.

### 3.2 Licensing, and the number that will actually bite you

This is the prerequisite most likely to cause a production incident three months in, so here is the arithmetic rather than a hand-wave.

| Licence held by the **flow owner** | Power Platform requests / 24h |
| --- | --- |
| Microsoft 365 (seeded Power Automate rights) | **6,000** |
| Power Automate Premium | 40,000 |

Every action execution counts, built-in Data Operations included, not just connector calls.

| | |
| --- | --- |
| Actions per run (typical classified report) | ~30 |
| Messages per week | ~200 |
| Delivery concentrated on | Sun, Mon, Tue |
| Peak-day messages (est.) | ~100 |
| **Peak-day requests** | **~3,000** |

That sits inside 6,000, with roughly a 2x margin. Comfortable but not generous: a backfill run, a catch-up delivery after an SPS outage, or any second flow owned by the same account eats the margin fast. And note that background flows bill to the **owner**, regardless of whose connection the actions use, so the owner account's other automations count against the same 6,000.

**Confirmed owner: `svc-sps-filing@swimusa.com`.** Build and own the flow from this account, not from a named user. It stops the flow breaking when a person leaves, which is a well-known way to lose an automation quietly, and it isolates this budget from anyone's other flows.

**One item to verify before go-live: that the account actually holds a Power Automate Premium licence.** Owning the flow from a service account with only seeded Microsoft 365 rights still caps it at 6,000 requests per 24 hours, and the peak-day estimate above is ~3,000. That works until it does not: a backfill run, a catch-up delivery after an SPS outage, or a second flow added to the same account each eat the margin. Premium moves it to 40,000, roughly 13x headroom.

If the licence is not in place on day one, that is a legitimate deferral rather than a blocker. Watch the Power Platform admin center capacity report (Licensing > Capacity add-ons > Download reports > "Microsoft Power Platform requests") for the first two months and move to Premium when peak days pass ~4,000. Note that Microsoft applies higher "transition period" limits today and has said official limits apply later, so budget to the documented 6,000 rather than to observed behaviour.

Standard connectors only (Office 365 Outlook, SharePoint, Teams), so nothing here requires premium *connector* rights. The licence is purely about request volume.

### 3.3 Environment and solution

| Decision | Recommendation |
| --- | --- |
| Environment | Your production environment, not Default. Default has no DLP boundary and no backup story. |
| Solution | Build **inside a solution** (`Swim USA - SPS Analytics Filing`). Solution-aware flows export, import and move between environments; non-solution flows do not. Retrofitting later is painful. |
| Connection references | Use them (automatic inside a solution). They let you repoint the mailbox connection without editing the flow. |

### 3.4 Trigger concurrency: leave it off

You will be tempted to set trigger concurrency to 1 to avoid two runs racing to create the same folder. **Don't.**

- **Turning concurrency on is irreversible.** Microsoft's guidance is explicit: to remove it you must delete and re-add the trigger.
- Turning it on drops the trigger's `Split on` debatching limit from 100,000 to **100 items**. SPS delivers in bursts, so that is a real risk of dropped messages.
- The folder race it protects against is already handled: the SharePoint action's default retry policy (4 exponential retries) absorbs a transient conflict, and both runs converge on the same folder.

Leave it at the default. If you later see genuine collisions in run history, the fix is a retry policy adjustment, not concurrency.

### 3.5 Alert destinations

Both are confirmed. Everything downstream in this guide points at these two.

| Destination | Address | Carries |
| --- | --- | --- |
| **SPS Report Hub** (Teams group chat) | `19:7506e9ab0358413c9932c88c52d6cece@thread.v2` | Immediate alerts: run failures, link-only reports |
| **sps-hub-alerts@swimusa.com** | Mail-enabled group | Weekly control report, platform notices |

**Prerequisite, already satisfied:** the account holding the flow's Teams connection must be a member of the SPS Report Hub chat, because the connector can only see and post to chats its signed-in account participates in. `svc-sps-filing@swimusa.com` **has been added to the chat**, so section 7.4 will build cleanly. If the chat is ever absent from the picker, membership is the first thing to re-check.

Two operational notes on the chat, so nobody is surprised later:

- Teams lists only the **50 most recent named group chats** in the connector's picker. `SPS Report Hub` is named, so it will appear while it is active, but a quiet month can push it off the list. Section 7.4 therefore uses **Enter custom value** with the thread ID above, which does not depend on recency.
- Chat membership is not managed like channel membership. There is no owner, no membership sync from a group, and no way to hand it over cleanly when someone leaves. If this alerting outlives the build phase, moving it to a proper Teams channel is worth doing. It is a one-field change in section 7.4.

---

## 4. Step 3: Build the mapping list

This is the file your team edits to add a retailer. Nobody should ever need to open the flow.

### 4.1 Create the list

**CompanyHub site > New > List > Blank list**, named **`SPS Filing Map`**.

| Column | Type | Purpose |
| --- | --- | --- |
| `Title` | Single line | The **match token**, written in normalized form (section 5.1) |
| `MapType` | Choice: `Sender`, `Retailer`, `ReportFamily`, `Brand`, `Calendar`, `FiscalWeek` | Which scan this row belongs to |
| `MatchMode` | Choice: `Token`, `EndsWith` | `Token` = bounded whole-word match. `EndsWith` = subject must end with it. |
| `MatchToken2` | Single line | Optional second token that must **also** be present |
| `Priority` | Number | Higher wins. See 4.2. |
| `OutputCode` | Single line | Filename segment, e.g. `MACYS`, `STYLE-SELLING`, `SHAPE-SOLVER-SPORT` |
| `FolderName` | Single line | Folder segment, e.g. `Macys`, `01 Style Selling`, `Shape Solver Sport` |
| `DefaultBrand` | Single line | ReportFamily rows only. Brand to use when none matches. |
| `Cadence` | Choice: `Weekly`, `Monthly` | ReportFamily rows only. Drives `YYYY-MM-DD` vs `YYYY-MM`. |
| `QlikOnly` | Yes/No | Brand rows only. Restricts the code to Qlik subjects. |
| `Active` | Yes/No | Default Yes. Set No to retire a rule without deleting its history. |

Set the list's default view to group by `MapType` and sort by `Priority` descending. It then reads exactly the way the flow evaluates it, which makes it self-documenting.

**Permissions:** give the analytics team **Contribute** on this list and **Read** on nothing else in the flow. This is the whole point of the design: the people who know the reports can maintain the rules, and they cannot break the automation.

### 4.2 How Priority works

Higher number wins. Ties are resolved arbitrarily, so avoid them.

| MapType | Set Priority to | Why |
| --- | --- | --- |
| `Retailer` | **Character count of the token** | Longest-first: `JCPINTERNET` (11) beats `JCPENNEY` (8) beats `JCP` (3) |
| `Retailer` (cross-retailer rows) | **900** | Must beat every real retailer. The spec requires the retailer scan be skipped entirely when the subject is cross-retailer. |
| `Brand` | **Character count of the token** | `SHAPE SOLVER SPORT` (18) beats `SHAPE SOLVER` (12). `LB PB` (5) beats `PB` (2). |
| `ReportFamily` | **The explicit values in 4.4** | **Not** length. See the warning below. |
| `Calendar` | Multi-word 200, single-word 100 | Multi-word phrases must be tested before trailing single words |

> **Do not set ReportFamily priority by token length.** It produces a wrong answer on a real, weekly subject. `SPS RETURNS REPORT - DILLARDS Weekly Trend Analysis` contains both `SPS RETURNS REPORT` (18 chars) and `WEEKLY TREND ANALYSIS` (21 chars). Length ordering files every Returns report as a Weekly Trend. Family priority encodes **specificity**, which is a judgement, not a measurement.

Leave gaps of 10 between family priorities so a new rule can be slotted in without renumbering.

### 4.3 Seed rows: Sender

| Title | MapType | MatchMode | Priority | OutputCode | Active |
| --- | --- | --- | --- | --- | --- |
| `analytics@spscommerce.com` | Sender | Token | 100 | `REPORT` | Yes |
| `POSServices@spscommerce.com` | Sender | Token | 100 | `ADMIN` | Yes |
| `no-reply@spscommerce.com` | Sender | Token | 100 | `ADMIN` | Yes |
| `retailintelligence@spscommerce.com` | Sender | Token | 100 | `ADMIN` | Yes |

Any sender not listed is treated as `ADMIN` and filed to `_Admin/{YYYY}/`, never discarded. Adding a second report sender is one row.

### 4.4 Seed rows: ReportFamily

| Title (token) | MatchToken2 | Priority | OutputCode | FolderName | DefaultBrand | Cadence |
| --- | --- | --- | --- | --- | --- | --- |
| `QLIK SELL THRU` | | 180 | `QLIK-SELL-THRU` | `06 Qlik Sell Thru` | `ALL-BRANDS` | Weekly |
| `SPS RETURNS REPORT` | | 170 | `RETURNS` | `07 Returns` | `ALL-BRANDS` | Weekly |
| `ALL DIVISIONS` | | 160 | `ROLLUP` | `08 Division Rollups` | `ALL-DIVISIONS` | Weekly |
| `ALL BRANDS TOTAL` | | 160 | `ROLLUP` | `08 Division Rollups` | `ALL-BRANDS` | Weekly |
| `TOP 6 ACCTS` | | 160 | `ROLLUP` | `08 Division Rollups` | `ALL-BRANDS` | Weekly |
| `BY DOOR & STYLE PERFORMANCE` | | 150 | `DOOR-AND-STYLE` | `05 Door and Style` | | Weekly |
| `DOOR PERFORMANCE` | | 140 | `DOOR-PERFORMANCE` | `04 Door Performance` | | Weekly |
| `STYLE SELLING` | | 130 | `STYLE-SELLING` | `01 Style Selling` | | Weekly |
| `WEEKLY TREND ANALYSIS` | | 120 | `WEEKLY-TREND` | `02 Weekly Trend` | | Weekly |
| `WTD` | `STD` | 110 | `PERIOD-TO-DATE` | `03 Period To-Date` | | Weekly |

The spec splits `ALL DIVISIONS` / `ALL BRANDS TOTAL` / `TOP 6 ACCTS` into one rule. Splitting them into three rows costs nothing and lets each carry its own `DefaultBrand`, which resolves an ambiguity the spec leaves open (section 11, item 3).

### 4.5 Seed rows: Retailer

| Title (token) | Priority | OutputCode | FolderName |
| --- | --- | --- | --- |
| `ALL RETAILERS` | **900** | `CROSS-RETAILER` | `_Cross-Retailer` |
| `TOP 6 ACCTS` | **900** | `CROSS-RETAILER` | `_Cross-Retailer` |
| `BLOOMINGDALES` | 13 | `BLOOMINGDALES` | `Bloomingdales` |
| `JCPINTERNET` | 11 | `JCPINTERNET` | `JCP Internet` |
| `NORDSTROM` | 9 | `NORDSTROM` | `Nordstrom` |
| `JCPENNEY` | 8 | `JCPENNEY` | `JCPenney` |
| `VON MAUR` | 8 | `VON-MAUR` | `Von Maur` |
| `DILLARDS` | 8 | `DILLARDS` | `Dillards` |
| `ACADEMY` | 7 | `ACADEMY` | `Academy` |
| `NEIMANS` | 7 | `NEIMANS` | `Neimans` |
| `BEALLS` | 6 | `BEALLS` | `Bealls` |
| `MACYS` | 5 | `MACYS` | `Macys` |
| `MAYCS` | 5 | `MACYS` | `Macys` |
| `KOHLS` | 5 | `KOHLS` | `Kohls` |
| `BELK` | 4 | `BELK` | `Belk` |
| `SAKS` | 4 | `SAKS` | `Saks` |
| `JCP` | 3 | `JCPENNEY` | `JCPenney` |
| `EBW` | 3 | `EBW` | `EBW` |
| `HBC` | 3 | `EBW` | `EBW` |

Notes on two rows that look like mistakes but are not:

- **`MAYCS`** is a genuine SPS typo appearing in live weekly subjects (`2. SALES - MIMI SIGNATURE- MAYCS Weekly Trend Analysis`). Without this row, that report falls to `_Unclassified` every single week.
- **`HBC` maps to the `EBW` folder** because HBC was repurposed as EBW and both names appear in the history. Aliasing keeps the series continuous. The original spelling is preserved in `SourceSubject`, so nothing is lost.

The spec also lists `MACY'S` as a separate row. It is unnecessary: normalization strips apostrophes before matching, so `MACY'S` has already become `MACYS` by the time the scan runs. Harmless if you add it, just redundant.

### 4.6 Seed rows: Brand

Priority = character count. Copy the spec's longest-first list verbatim.

| Title | Pri | OutputCode | FolderName | QlikOnly |
| --- | --- | --- | --- | --- |
| `SHAPE SOLVER SPORT` | 18 | `SHAPE-SOLVER-SPORT` | `Shape Solver Sport` | No |
| `ALL BRANDS TOTAL` | 16 | `ALL-BRANDS` | `All Brands` | No |
| `AMERICAN BEACH` | 14 | `AMERICAN-BEACH` | `American Beach` | No |
| `MIMI SIGNATURE` | 14 | `MIMI-SIGNATURE` | `Mimi Signature` | No |
| `SWIM SOLUTIONS` | 14 | `SWIM-SOLUTIONS` | `Swim Solutions` | No |
| `CONTROL BRANDS` | 14 | `CONTROL-BRANDS` | `Control Brands` | No |
| `ORAGEOUS KIDS` | 13 | `ORAGEOUS-KIDS` | `Orageous Kids` | No |
| `GREAT LENGTHS` | 13 | `GREAT-LENGTHS` | `Great Lengths` | No |
| `ALL DIVISIONS` | 13 | `ALL-DIVISIONS` | `All Divisions` | No |
| `ORAGEOUS JRS` | 12 | `ORAGEOUS-JRS` | `Orageous Jrs` | No |
| `SHAPE SOLVER` | 12 | `SHAPE-SOLVER` | `Shape Solver` | No |
| `STEVE MADDEN` | 12 | `STEVE-MADDEN` | `Steve Madden` | No |
| `LAUREN MISSY` | 12 | `LAUREN-MISSY` | `Lauren Missy` | No |
| `LAUREN WOMAN` | 12 | `LAUREN-WOMAN` | `Lauren Woman` | No |
| `SALT & COVE` | 11 | `SALT-AND-COVE` | `Salt and Cove` | No |
| `BAL HARBOUR` | 11 | `BAL-HARBOUR` | `Bal Harbour` | No |
| `MIRACLESUIT` | 11 | `MIRACLESUIT` | `Miraclesuit` | No |
| `ALL BRANDS` | 10 | `ALL-BRANDS` | `All Brands` | No |
| `ECO BEACH` | 9 | `ECO-BEACH` | `Eco Beach` | No |
| `VITAMIN A` | 9 | `VITAMIN-A` | `Vitamin A` | No |
| `LONGITUDE` | 9 | `LONGITUDE` | `Longitude` | No |
| `FREELY` | 6 | `FREELY` | `Freely` | No |
| `LAUREN` | 6 | `LAUREN` | `Lauren` | No |
| `POLO` | 4 | `POLO` | `Polo` | No |
| `GLKO` | 4 | `GLKO` | `GLKO` | No |
| `JRS` | 3 | `JRS` | `Jrs` | No |
| `S3` | 2 | `S3` | `S3` | No |
| `TS` | 2 | `TS` | `TS` | No |
| `LB PB` | 5 | `LB-PB` | `LB PB` | **Yes** |
| `RL` | 2 | `RL` | `RL` | **Yes** |
| `MG` | 2 | `MG` | `MG` | **Yes** |
| `MS` | 2 | `MS` | `MS` | **Yes** |
| `VA` | 2 | `VA` | `VA` | **Yes** |
| `SS` | 2 | `SS` | `SS` | **Yes** |
| `BF` | 2 | `BF` | `BF` | **Yes** |
| `PB` | 2 | `PB` | `PB` | **Yes** |

`SALT & COVE` becomes `SALT-AND-COVE` in the filename per the spec, because `&` is legal in a SharePoint filename but needlessly awkward in URLs and downstream tooling.

### 4.7 Seed rows: Calendar

| Title (token) | MatchMode | Priority | OutputCode |
| --- | --- | --- | --- |
| `4 5 4 CALENDAR` | Token | 200 | `454` |
| `SUPPLIER FISCAL CALENDAR` | Token | 200 | `SUPPLIER` |
| `SUPPLIER` | **EndsWith** | 100 | `SUPPLIER` |
| `NRF` | **EndsWith** | 100 | `NRF` |

Note `4-5-4 Calendar` is written `4 5 4 CALENDAR`, and `Supplier (FISCAL) Calendar` is written `SUPPLIER FISCAL CALENDAR`. That is not a typo, it is the normalized form. Section 5.1 explains why.

---

## 5. Step 4: The normalization rules

Every match token in the list above is written in **normalized form**, and the flow normalizes each incoming subject the same way before matching. Both sides meet in the middle, which is what makes the punctuation chaos in the live feed stop mattering.

### 5.1 The five rules

Applied in this order:

| # | Rule | `1. SALES - SALT & COVE MACY'S STYLE SELLING` becomes |
| --- | --- | --- |
| 1 | Remove apostrophes (straight and curly) | `1. SALES - SALT & COVE MACYS STYLE SELLING` |
| 2 | Uppercase | (already) |
| 3 | Replace every character except `A-Z`, `0-9`, space and `&` with a space | `1  SALES   SALT & COVE MACYS STYLE SELLING` |
| 4 | Collapse runs of spaces to one, then trim | `1 SALES SALT & COVE MACYS STYLE SELLING` |
| 5 | Strip a leading sequence number | `SALES SALT & COVE MACYS STYLE SELLING` |

**When you add a row to the mapping list, write the token the way it looks after rule 5.** Uppercase, no punctuation except `&`, single spaces. That is the whole convention.

### 5.2 Why this replaces the spec's normalization, rule by rule

The spec's normalization section is right about the problems and wrong about one of the fixes.

| Spec rule | Verdict |
| --- | --- |
| Strip characters outside `\x20-\x7E` | **Superseded, and widened.** Rule 3 is stricter: it keeps an explicit allowlist rather than excluding a range. Same effect on the six corrupted subjects, and it also neutralizes commas, slashes, parentheses and colons in one pass. |
| Collapse doubled spaces | **Kept**, as rule 4. |
| Do not match on comma punctuation; test `WTD` and `STD` as separate tokens | **Kept.** Rule 3 turns `WTD,MTD,STD` and `WTD, MTD & STD` into the same shape, and the `WTD` + `STD` family row uses `MatchToken2`. |
| Strip apostrophes | **Kept**, as rule 1, and promoted to run first. It must precede rule 3, or `MACY'S` becomes `MACY S` and stops matching `MACYS`. |
| Strip leading `^\d+\.\s*` | **Kept**, as rule 5. |
| **Pad hyphens to ` - `** | **Rejected.** This one breaks live subjects. Padding turns `4-5-4 Calendar` into `4 - 5 - 4 Calendar`, so the `4-5-4 Calendar` calendar token stops matching and every Macys 4-5-4 rollup loses its calendar segment, which is exactly the collision the spec warns about in section 3. It also mangles `To-Date`. Rule 3 solves the underlying problem (`SIGNATURE- DILLARDS`) more simply by turning the hyphen into a space and letting rule 4 clean up. |

### 5.3 Bounded-token matching, and why it is not optional

All matching is **bounded**: the flow wraps the normalized subject in spaces and searches for the token wrapped in spaces. A naive `contains` produces a wrong answer on live data:

> The brand list contains `TS`. The subject `SALES TOP 6 ACCTS ...` contains the letters `TS` inside `ACCTS`. A naive contains-match files that cross-retailer rollup under brand **TS**, every week.

Bounded matching asks whether `' TS '` appears in `' SALES TOP 6 ACCTS '`. It does not. Correct.

Bounded matching plus priority also handles the overlapping-prefix cases the spec flags:

| Subject contains | Both match (bounded) | Priority picks |
| --- | --- | --- |
| `SHAPE SOLVER SPORT` | `SHAPE SOLVER SPORT` (18), `SHAPE SOLVER` (12) | **SHAPE SOLVER SPORT** |
| `... LB PB` | `LB PB` (5), `PB` (2) | **LB PB** |
| `SPS RETURNS REPORT ... WEEKLY TREND ANALYSIS` | both family tokens | **SPS RETURNS REPORT** (priority 170 > 120) |

One useful property of the platform: WDL's `contains`, `indexOf`, `startsWith` and `endsWith` are **case-insensitive**. The flow uppercases anyway, so behaviour is deterministic either way, but it means a lowercase token typed into the mapping list still works. Do not rely on it, do write tokens uppercase.

---

## 6. Step 5: Build the production flow

Flow name: **`SPS Analytics - File Reports to SharePoint`**

Build it in the order below. Every expression is paste-ready.

> **Two conventions before you start.**
>
> 1. In WDL, an action's name has its spaces converted to underscores. `Compose Subject Padded` is referenced as `outputs('Compose_Subject_Padded')`. If you rename an action after referencing it, the designer updates most references but not all. **Rename first, reference second.**
> 2. Where an expression reads `triggerOutputs()?['body/Subject']`, you can equally drag the **Subject** dynamic-content token. The written form is given so you can paste a whole expression in one go.

### 6.1 Trigger

**Display name: `When a new report arrives`**
Connector: **Office 365 Outlook** > **When a new email arrives in a shared mailbox (V2)**

| Field | Value |
| --- | --- |
| Original Mailbox Address | `sps-analytics@swimusa.com` |
| Folder | `Inbox` |
| Only with Attachments | **No** |
| Include Attachments | **Yes** |
| From | *(leave blank)* |
| Subject Filter | *(leave blank)* |

**Leave `From` blank on purpose.** It is tempting to filter the trigger to `analytics@spscommerce.com` and save the flow some work. Don't: the trigger would then never see the non-report mail, and the `_Admin` routing you asked for would silently do nothing. The sender guard belongs in the flow (section 6.5), where it is visible and where the sender list is data.

Settings to set on the trigger (three dots > Settings):

| Setting | Value | Why |
| --- | --- | --- |
| Concurrency Control | **Off** | Irreversible once on, and it caps debatching at 100. See 3.4. |
| Split On | `@triggerOutputs()?['body/value']` (default) | One run per message |

**Known trigger limits worth writing on the runbook:**

- Messages over **50 MB** (or your Exchange transport limit, whichever is lower) are skipped silently. No report in this feed is close, but a monthly rollup could grow into it.
- **`.eml`, `.msg` and `.ics` attachments are not returned** by this trigger unless they are inside a `.zip`. Item attachments (a forwarded email attached to an email) are not supported at all. If SPS ever forwards a report rather than attaching it, the flow sees a message with no usable attachment and routes it via section 6.10.
- The trigger keys off received date. Moving mail between folders can cause it to **re-fire on older messages**. This is documented behaviour, not a bug, and it is exactly why the `SourceMessageId` replay guard in section 6.9 exists.

### 6.2 Wrap everything in a Try scope

**Display name: `Scope Try`**
Action: **Control** > **Scope**

Every action from 6.3 through 6.10 goes inside this. Section 7 adds the Catch.

### 6.3 Normalize and derive (inside `Scope Try`)

All **Data Operations > Compose** unless noted.

**`Compose Library Root`** (plain text, no expression, this is your one swap point)
```
/Shared Documents/02 - Sales/05 - Published Reports
```

**`Compose Subject Uppercase`**
```
toUpper(replace(replace(coalesce(triggerOutputs()?['body/Subject'], ''), '''', ''), '’', ''))
```
The `''''` is a WDL-escaped single apostrophe. The second `replace` strips the curly apostrophe; if it will not paste cleanly into the designer, delete that inner `replace` and see section 11, item 8.

**`Select Subject Allowed Characters`** (Data Operations > **Select**)

| Field | Value |
| --- | --- |
| From | `range(0, length(outputs('Compose_Subject_Uppercase')))` |
| Map | *(switch the Map box to text mode using the icon on its right, then paste the single expression below)* |

```
if(greater(indexOf('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 &', substring(outputs('Compose_Subject_Uppercase'), item(), 1)), -1), substring(outputs('Compose_Subject_Uppercase'), item(), 1), ' ')
```

This is the character allowlist, and it is the reason the flow needs no regular expressions: **Power Automate has no regex function.** `Select` over `range()` walks the string one character at a time, which is the idiomatic substitute.

**`Compose Subject Collapsed`**
```
trim(replace(replace(replace(join(body('Select_Subject_Allowed_Characters'), ''), ' ', '<>'), '><', ''), '<>', ' '))
```
The `<>` / `><` dance collapses any run of spaces to one, in three `replace` calls and no loop. It is safe precisely because the allowlist above excludes `<` and `>`, so those characters cannot occur in the input.

**`Compose Subject Normalized`**
```
if(and(greater(length(outputs('Compose_Subject_Collapsed')), 2), greater(indexOf('0123456789', substring(outputs('Compose_Subject_Collapsed'), 0, 1)), -1), equals(substring(outputs('Compose_Subject_Collapsed'), 1, 1), ' ')), trim(substring(outputs('Compose_Subject_Collapsed'), 2, sub(length(outputs('Compose_Subject_Collapsed')), 2))), outputs('Compose_Subject_Collapsed'))
```
Strips the leading `1. ` / `2. ` sequence number (which by this point reads `1 `). Per the spec, the number must never be used to determine family: two different families both use `3.`.

**`Compose Subject Padded`**
```
concat(' ', outputs('Compose_Subject_Normalized'), ' ')
```
This is what every bounded-token match runs against.

**`Compose Received Local`**
```
convertTimeZone(triggerOutputs()?['body/DateTimeReceived'], 'UTC', 'Eastern Standard Time', 'yyyy-MM-ddTHH:mm:ss')
```

**`Compose Week Ending`**
```
formatDateTime(addDays(outputs('Compose_Received_Local'), mul(-1, mod(add(dayOfWeek(outputs('Compose_Received_Local')), 1), 7))), 'yyyy-MM-dd')
```
This is the single most important expression in the flow (section 1.2). `dayOfWeek()` returns 0 for Sunday through 6 for Saturday, so `mod(dayOfWeek + 1, 7)` is exactly the number of days back to the most recent Saturday: Sunday goes back 1, Monday 2, Tuesday 3, Saturday 0.

**`Compose Filing Year`**
```
formatDateTime(outputs('Compose_Week_Ending'), 'yyyy')
```
Deliberately the **week-ending** year, not the received year, so a report arriving 1 January files under the year whose week it reports on.

### 6.4 Load the mapping (one call, reused four times)

**`Get items Filing Map`**
Connector: **SharePoint** > **Get items**

| Field | Value |
| --- | --- |
| Site Address | `https://mainstreamswimsuits.sharepoint.com/sites/CompanyHub` |
| List Name | `SPS Filing Map` |
| Filter Query | `Active eq 1` |
| Order By | `Priority desc` |
| Top Count | `500` |

Settings (three dots > Settings): **Pagination On**, Threshold `2000`.

`Order By Priority desc` is what makes `first(...)` on every filter below mean "highest priority match". The ordering is done once, by SharePoint, not four times in the flow.

If `Active eq 1` is rejected by your tenant, use `Active eq true`. Both forms appear in the wild.

### 6.5 Sender guard

**`Filter array Sender Match`** (Data Operations > **Filter array**)

| Field | Value |
| --- | --- |
| From | `outputs('Get_items_Filing_Map')?['body/value']` |
| Condition (left, advanced mode) | *(expression below)* |
| Condition (operator / right) | `is equal to` / `true` |

```
and(equals(item()?['MapType/Value'], 'Sender'), equals(toLower(item()?['Title']), toLower(trim(coalesce(triggerOutputs()?['body/From'], '')))))
```

**`Compose Sender Disposition`**
```
if(empty(body('Filter_array_Sender_Match')), 'ADMIN', first(body('Filter_array_Sender_Match'))?['OutputCode'])
```
Unknown sender defaults to `ADMIN`, never to discard. Nothing is ever silently lost.

**`Condition Is Report Mail`** (Control > **Condition**)

| Left | Operator | Right |
| --- | --- | --- |
| `outputs('Compose_Sender_Disposition')` | is equal to | `REPORT` |

The **If no** branch handles admin mail; see section 7.3. Everything from 6.6 on goes in the **If yes** branch.

### 6.6 Parse retailer, family, calendar, brand

Four `Filter array` + `Compose` pairs. Each `Compose` holds the winning **row object**, so downstream expressions read fields off it without extra actions.

**`Filter array Retailer Match`** (From: `outputs('Get_items_Filing_Map')?['body/value']`, result `is equal to true`)
```
and(equals(item()?['MapType/Value'], 'Retailer'), or(and(equals(item()?['MatchMode/Value'], 'Token'), contains(outputs('Compose_Subject_Padded'), concat(' ', item()?['Title'], ' '))), and(equals(item()?['MatchMode/Value'], 'EndsWith'), endsWith(outputs('Compose_Subject_Normalized'), concat(' ', item()?['Title'])))))
```

**`Compose Retailer Row`**
```
first(body('Filter_array_Retailer_Match'))
```

**`Filter array Family Match`**
```
and(equals(item()?['MapType/Value'], 'ReportFamily'), contains(outputs('Compose_Subject_Padded'), concat(' ', item()?['Title'], ' ')), or(empty(coalesce(item()?['MatchToken2'], '')), contains(outputs('Compose_Subject_Padded'), concat(' ', item()?['MatchToken2'], ' '))))
```
The `MatchToken2` clause is what implements the spec's "test for `WTD` and `STD` as separate tokens" rule without matching on punctuation.

**`Compose Family Row`**
```
first(body('Filter_array_Family_Match'))
```

**`Filter array Calendar Match`**
```
and(equals(item()?['MapType/Value'], 'Calendar'), or(and(equals(item()?['MatchMode/Value'], 'Token'), contains(outputs('Compose_Subject_Padded'), concat(' ', item()?['Title'], ' '))), and(equals(item()?['MatchMode/Value'], 'EndsWith'), endsWith(outputs('Compose_Subject_Normalized'), concat(' ', item()?['Title'])))))
```

**`Compose Calendar Row`**
```
first(body('Filter_array_Calendar_Match'))
```

**`Compose Subject For Brand`**
```
replace(replace(outputs('Compose_Subject_Padded'), concat(' ', coalesce(outputs('Compose_Retailer_Row')?['Title'], '~NONE~'), ' '), ' '), concat(' ', coalesce(outputs('Compose_Family_Row')?['Title'], '~NONE~'), ' '), ' ')
```
Removes the retailer and family tokens before the brand scan, per the spec's order of operations. Without this, `ALL DIVISIONS` matches as both a family and a brand.

**`Filter array Brand Match`**
```
and(equals(item()?['MapType/Value'], 'Brand'), contains(outputs('Compose_Subject_For_Brand'), concat(' ', item()?['Title'], ' ')), or(equals(item()?['QlikOnly'], false), equals(coalesce(outputs('Compose_Family_Row')?['OutputCode'], ''), 'QLIK-SELL-THRU')))
```
The `QlikOnly` clause keeps two-letter codes like `RL` and `MG` from matching outside Qlik subjects.

**`Compose Brand Row`**
```
first(body('Filter_array_Brand_Match'))
```

**`Compose Brand Code`**
```
coalesce(outputs('Compose_Brand_Row')?['OutputCode'], outputs('Compose_Family_Row')?['DefaultBrand'])
```

**`Compose Brand Folder`**
```
coalesce(outputs('Compose_Brand_Row')?['FolderName'], if(equals(coalesce(outputs('Compose_Family_Row')?['DefaultBrand'], ''), 'ALL-DIVISIONS'), 'All Divisions', 'All Brands'))
```

### 6.7 Routability gate

**`Condition Is Routable`** (Control > **Condition**, left box in advanced mode, `is equal to` `true`)
```
and(not(empty(coalesce(outputs('Compose_Retailer_Row')?['OutputCode'], ''))), not(empty(coalesce(outputs('Compose_Family_Row')?['OutputCode'], ''))), not(empty(coalesce(outputs('Compose_Brand_Code'), ''))))
```

This is the spec's "do not guess" rule, made explicit. All three must resolve. The live case it catches is `3. SALES - DOOR PERFORMANCE`, which arrives with no retailer and no brand and is genuinely unroutable by any parser, human included.

The **If no** branch is `_Unclassified` routing; see section 7.2.

### 6.8 Select the real attachments

**`Filter array Report Attachments`**

| Field | Value |
| --- | --- |
| From | `triggerOutputs()?['body/Attachments']` |
| Condition | *(expression below)*, `is equal to` `true` |

```
and(equals(item()?['IsInline'], false), greater(item()?['Size'], 15000), greater(indexOf('|XLSX|XLS|CSV|TXT|PDF|ZIP|', concat('|', toUpper(last(split(item()?['Name'], '.'))), '|')), -1))
```

Three filters, each doing a specific job:

- **`IsInline = false`** drops embedded images in the message body. This is the property that exists precisely for this.
- **`Size > 15000`** drops signature logos and tracking pixels that are attached rather than inlined, which `IsInline` will not catch. 15 KB is comfortably below the smallest real report and above essentially every signature graphic. Tune it after the backfill if you see a real file near the line.
- **The pipe-delimited extension allowlist** is a bounded match, the same trick as section 5.3: `|XLSX|` cannot match inside another word.

**`Condition Has Report Attachment`**: `length(body('Filter_array_Report_Attachments'))` `is greater than` `0`. The **If no** branch is section 6.10.

### 6.9 File the attachment

**`Apply to each Report Attachment`** (Control > **Apply to each**)
From: `body('Filter_array_Report_Attachments')`

Everything below is inside this loop.

**`Compose Attachment Extension`**
```
toLower(last(split(items('Apply_to_each_Report_Attachment')?['Name'], '.')))
```

**`Compose Has Sortable Date`** (does the attachment name already start with `YYYY-MM-DD`?)
```
and(greater(length(items('Apply_to_each_Report_Attachment')?['Name']), 10), equals(substring(items('Apply_to_each_Report_Attachment')?['Name'], 4, 1), '-'), equals(substring(items('Apply_to_each_Report_Attachment')?['Name'], 7, 1), '-'), greater(indexOf('0123456789', substring(items('Apply_to_each_Report_Attachment')?['Name'], 0, 1)), -1), greater(indexOf('0123456789', substring(items('Apply_to_each_Report_Attachment')?['Name'], 1, 1)), -1), greater(indexOf('0123456789', substring(items('Apply_to_each_Report_Attachment')?['Name'], 2, 1)), -1), greater(indexOf('0123456789', substring(items('Apply_to_each_Report_Attachment')?['Name'], 3, 1)), -1), greater(indexOf('0123456789', substring(items('Apply_to_each_Report_Attachment')?['Name'], 5, 1)), -1), greater(indexOf('0123456789', substring(items('Apply_to_each_Report_Attachment')?['Name'], 6, 1)), -1), greater(indexOf('0123456789', substring(items('Apply_to_each_Report_Attachment')?['Name'], 8, 1)), -1), greater(indexOf('0123456789', substring(items('Apply_to_each_Report_Attachment')?['Name'], 9, 1)), -1))
```

**`Compose Date Stamp`** (the three-branch rule you asked for)
```
if(equals(outputs('Compose_Has_Sortable_Date'), true), substring(items('Apply_to_each_Report_Attachment')?['Name'], 0, 10), if(equals(coalesce(outputs('Compose_Family_Row')?['Cadence/Value'], 'Weekly'), 'Monthly'), formatDateTime(outputs('Compose_Week_Ending'), 'yyyy-MM'), outputs('Compose_Week_Ending')))
```

| Your rule | Branch | Status in the live feed |
| --- | --- | --- |
| Already sortable, preserve it | `Compose Has Sortable Date` = true | **Never fires today.** Zero of 1,001 attachments carry any date. Kept so a future sender works without a flow change. |
| Non-sortable, rewrite it | *(optional, below)* | Never fires today. **Recommend leaving disabled.** |
| No date, derive one | fallback | **This is the live path for 100% of current traffic.** |

**Optional non-sortable rewrite.** If a sender ever starts naming files `9-10-2026_...`, add two Composes before `Compose Date Stamp` and insert the middle branch. `Compose US Date Text` holds the candidate substring, and the conversion is:
```
formatDateTime(parseDateTime(outputs('Compose_US_Date_Text'), 'en-US'), 'yyyy-MM-dd')
```
Always pass the `'en-US'` locale. Without it, parsing follows the flow's regional settings and `03/04/2026` silently becomes 3 April instead of 4 March. Leave this branch disabled (set `Compose Has US Date` to the literal `false`) until a real sender needs it: a half-tested date parser that fires once a quarter is worse than no date parser, because the derived date is correct and the folder ceiling depends on it.

**`Compose File Name`**
```
concat(outputs('Compose_Date_Stamp'), '_', coalesce(outputs('Compose_Retailer_Row')?['OutputCode'], 'UNKNOWN'), '_', outputs('Compose_Brand_Code'), '_', coalesce(outputs('Compose_Family_Row')?['OutputCode'], 'UNKNOWN'), if(empty(coalesce(outputs('Compose_Calendar_Row')?['OutputCode'], '')), '', concat('_', outputs('Compose_Calendar_Row')?['OutputCode'])), '.', outputs('Compose_Attachment_Extension'))
```

**`Compose Folder Path`**
```
concat(outputs('Compose_Library_Root'), '/', outputs('Compose_Filing_Year'), '/', outputs('Compose_Retailer_Row')?['FolderName'], '/', outputs('Compose_Family_Row')?['FolderName'], '/', outputs('Compose_Brand_Folder'))
```

**`Compose Full File Path`**
```
concat(outputs('Compose_Folder_Path'), '/', outputs('Compose_File_Name'))
```

> **On folder creation.** You do not need a `Create new folder` action. The SharePoint **Create file** action creates missing intermediate folders on its way to the path you give it: Microsoft's parameter description is "Must start with an existing library. **Add folders if needed.**" So a new year, retailer, family or brand folder appears the first time a report needs it, in one action, with no race window.
>
> If you want the explicit version for legibility (the spec argues for it), the action is **SharePoint > Create new folder** with Site Address, **List or Library = `Documents`**, and Folder Path = the path **without** the library prefix. It does create a whole nested path in one call. The catch: it **fails if the folder already exists**, so it needs its own scope and run-after handling, and it fires on all ~10,400 runs to be useful on about 200 of them. I recommend relying on Create file.

**`Get file metadata using path Existing File`** (SharePoint)

| Field | Value |
| --- | --- |
| Site Address | `https://mainstreamswimsuits.sharepoint.com/sites/CompanyHub` |
| File Path | `outputs('Compose_Full_File_Path')` |

This action is **expected to fail with 404** most of the time. That is the design. On the *next* action set **Configure run after** to tick both **is successful** and **has failed**.

**`Condition File Exists`** (left box advanced, `is equal to` `true`)
```
equals(actions('Get_file_metadata_using_path_Existing_File')?['status'], 'Succeeded')
```

**If no (the common path) > `Create file New Report`** (SharePoint > Create file)

| Field | Value |
| --- | --- |
| Site Address | `https://mainstreamswimsuits.sharepoint.com/sites/CompanyHub` |
| Folder Path | `outputs('Compose_Folder_Path')` |
| File Name | `outputs('Compose_File_Name')` |
| File Content | `base64ToBinary(items('Apply_to_each_Report_Attachment')?['ContentBytes'])` |

**If yes > `Get file properties Existing`** (SharePoint > Get file properties)

| Field | Value |
| --- | --- |
| Site Address | as above |
| Library Name | `Documents` |
| Id | `outputs('Get_file_metadata_using_path_Existing_File')?['body/ItemId']` |

**then `Condition Same Message`** (`is equal to` `true`)
```
equals(coalesce(outputs('Get_file_properties_Existing')?['body/SourceMessageId'], ''), coalesce(triggerOutputs()?['body/InternetMessageId'], ''))
```

| Branch | Meaning | Action |
| --- | --- | --- |
| **If yes** | Same message, already filed. A replay, a resubmit, or backfill overlap. | **Do nothing.** Add a `Terminate` with status **Succeeded** so the run reads green. |
| **If no** | Different message, same reporting week. **This is a resend or a correction.** | **`Update file Existing Report`** |

**`Update file Existing Report`** (SharePoint > Update file)

| Field | Value |
| --- | --- |
| Site Address | as above |
| File Identifier | `outputs('Get_file_metadata_using_path_Existing_File')?['body/Id']` |
| File Content | `base64ToBinary(items('Apply_to_each_Report_Attachment')?['ContentBytes'])` |

Content is replaced, SharePoint writes a new version, the folder gains no file. The ceiling holds.

**`Compose Item Id`** (run after both branches)
```
if(equals(actions('Get_file_metadata_using_path_Existing_File')?['status'], 'Succeeded'), outputs('Get_file_metadata_using_path_Existing_File')?['body/ItemId'], outputs('Create_file_New_Report')?['body/ItemId'])
```

**`Update file properties Report Metadata`** (SharePoint > Update file properties)

| Field | Value |
| --- | --- |
| Site Address | as above |
| Library Name | `Documents` |
| Id | `outputs('Compose_Item_Id')` |

| Column | Value |
| --- | --- |
| `Retailer` | `outputs('Compose_Retailer_Row')?['OutputCode']` |
| `Brand` | `outputs('Compose_Brand_Code')` |
| `ReportFamily` | `outputs('Compose_Family_Row')?['OutputCode']` |
| `Calendar` | `coalesce(outputs('Compose_Calendar_Row')?['OutputCode'], '')` |
| `ReceivedDate` | `outputs('Compose_Received_Local')` |
| `WeekEnding` | `outputs('Compose_Week_Ending')` |
| `FiscalWeek` | `coalesce(first(body('Filter_array_Fiscal_Week'))?['OutputCode'], '')` *(or leave blank, see 2.3)* |
| `SourceSubject` | `outputs('Compose_Subject_Normalized')` |
| `SourceMessageId` | `triggerOutputs()?['body/InternetMessageId']` |
| `SourceAttachmentName` | `items('Apply_to_each_Report_Attachment')?['Name']` |
| `ParseConflict` | `false` |

If you are populating `FiscalWeek`, add one more `Filter array Fiscal Week` against the same cached map:
```
and(equals(item()?['MapType/Value'], 'FiscalWeek'), equals(item()?['Title'], outputs('Compose_Week_Ending')))
```

### 6.10 When the report is a link, not an attachment

The **If no** branch of `Condition Has Report Attachment`. This covers three real situations: a report delivered as a portal download link, a report pasted into the message body, and a message whose only attachments were signature images the filter stripped.

**Do not try to follow the link.** An SPS portal URL needs an authenticated session the flow does not have, and an unauthenticated `HTTP` action against it returns a login page that would be filed as if it were a report. That is worse than not filing it.

Instead, preserve the message itself:

**`Export email Link Report`** (Office 365 Outlook > **Export email (V2)**)

| Field | Value |
| --- | --- |
| Message Id | `triggerOutputs()?['body/Id']` |
| Original Mailbox Address | `sps-analytics@swimusa.com` |

**`Create file Link Report`** (SharePoint > Create file)

| Field | Value |
| --- | --- |
| Site Address | as above |
| Folder Path | `concat(outputs('Compose_Library_Root'), '/_Unclassified/', formatDateTime(outputs('Compose_Week_Ending'), 'yyyy-MM'), '/_Links')` |
| File Name | `concat(outputs('Compose_Week_Ending'), '_', replace(outputs('Compose_Subject_Normalized'), ' ', '-'), '.eml')` |
| File Content | `body('Export_email_Link_Report')` |

The `.eml` opens in Outlook with the link live and the full context intact, which is what someone chasing the report actually needs. Then notify, per section 7.4.

**The alternatives, and when they are worth it:**

| Approach | Use when | Trade-off |
| --- | --- | --- |
| **Export email (V2) to `.eml`** *(recommended)* | Always, as the safe default | A human still has to fetch the report. Nothing is lost, nothing is guessed. |
| `HTTP` action against the link | The link is a pre-authenticated, tokenized URL | **Premium connector.** Fails or files a login page if auth is needed. Do not use against an SPS portal. |
| **Power Automate Desktop** with an attended browser session | SPS never fixes the delivery and the volume becomes material | Needs a machine, a licence, and babysitting. Treat as a last resort, and raise it with SPS first (section 12). |

---

## 7. Step 6: Error handling and exception routing

The governing rule: **no report is ever silently lost.** Every path ends in a file somewhere and, where a human needs to know, a notification.

There are four exception routes. Three are expected business outcomes, not errors. One is a genuine failure.

| Route | Trigger | Destination | Run status | Notify |
| --- | --- | --- | --- | --- |
| `_Admin` | Sender is not a report sender | `_Admin/{YYYY}/` | Succeeded | No |
| `_Unclassified` | Parser could not resolve retailer, family or brand | `_Unclassified/{YYYY-MM}/` | **Succeeded** | Weekly digest |
| `_Unclassified/_Links` | Report arrived as a link or body text | `_Unclassified/{YYYY-MM}/_Links/` | Succeeded | Immediate |
| **Catch** | An action actually failed | `_Unclassified/{YYYY-MM}/_Failed/` | **Failed** | Immediate |

### 7.1 Why the first three end in Succeeded

A run that files a message correctly into `_Unclassified` did its job. Marking it Failed floods run history with red, trains the team to ignore red, and hides the genuine failures. The signal that unclassified mail needs attention is the **weekly control report** (section 9), which is a business signal on a business cadence, not an alert per message.

The Catch route is the opposite: something broke, the run should read Failed, and **Resubmit** should be a safe thing for someone to click. It is safe, because the `SourceMessageId` guard in 6.9 makes a resubmit idempotent.

### 7.2 `_Unclassified` routing

In the **If no** branch of `Condition Is Routable`:

**`Apply to each Unclassified Attachment`** > From `triggerOutputs()?['body/Attachments']`, containing **`Create file Unclassified`**:

| Field | Value |
| --- | --- |
| Site Address | `https://mainstreamswimsuits.sharepoint.com/sites/CompanyHub` |
| Folder Path | `concat(outputs('Compose_Library_Root'), '/_Unclassified/', formatDateTime(outputs('Compose_Week_Ending'), 'yyyy-MM'))` |
| File Name | `concat(outputs('Compose_Week_Ending'), '_', substring(replace(outputs('Compose_Subject_Normalized'), ' ', '-'), 0, min(length(outputs('Compose_Subject_Normalized')), 80)), '_', items('Apply_to_each_Unclassified_Attachment')?['Name'])` |
| File Content | `base64ToBinary(items('Apply_to_each_Unclassified_Attachment')?['ContentBytes'])` |

Note the `min(..., 80)` guard. Filenames come from subject text here rather than from the controlled mapping list, and SharePoint enforces a **400-character total URL limit**. Truncating the subject fragment at 80 characters keeps the longest possible unclassified path well inside it. For comparison, the longest normal path in this design measures 247 characters URL-encoded, leaving 153 to spare:

```
https://mainstreamswimsuits.sharepoint.com/sites/CompanyHub/Shared%20Documents/02%20-%20Sales/
05%20-%20Published%20Reports/2026/Dillards/01%20Style%20Selling/Shape%20Solver%20Sport/
2026-09-12_DILLARDS_SHAPE-SOLVER-SPORT_STYLE-SELLING_SUPPLIER.xlsx
```

Then **`Update file properties Unclassified`** setting `SourceSubject`, `SourceMessageId`, `ReceivedDate`, `WeekEnding` and `ParseConflict = true`, followed by **`Terminate Unclassified`** (Control > Terminate, Status **Succeeded**).

Populating `SourceSubject` here is what makes the weekly digest useful: it tells whoever reads it exactly which token to add to the mapping list.

### 7.3 `_Admin` routing

In the **If no** branch of `Condition Is Report Mail`, the same shape: `Create file Admin` into
```
concat(outputs('Compose_Library_Root'), '/_Admin/', outputs('Compose_Filing_Year'))
```
then `Terminate Admin` with status **Succeeded**. Expect roughly 40 messages a year here: SPS account notices, the Retail Intelligence newsletter, and the Retailer Data Availability Report.

### 7.4 The Catch scope

**`Scope Catch`** (Control > Scope), placed after `Scope Try`.

**Configure run after** on `Scope Catch`: untick **is successful**, tick **has failed**, **is skipped**, **has timed out**.

Inside it:

**`Filter array Failed Actions`**

| Field | Value |
| --- | --- |
| From | `result('Scope_Try')` |
| Condition | `item()?['status']` `is equal to` `Failed` |

**`Compose Error Summary`**
```
concat('Action: ', coalesce(first(body('Filter_array_Failed_Actions'))?['name'], 'unknown'), ' | Code: ', coalesce(first(body('Filter_array_Failed_Actions'))?['error']?['code'], 'none'), ' | Message: ', coalesce(first(body('Filter_array_Failed_Actions'))?['error']?['message'], 'none'))
```

**`Compose Run Link`**
```
concat('https://make.powerautomate.com/environments/', workflow()?['tags']?['environmentName'], '/flows/', workflow()?['name'], '/runs/', workflow()?['run']?['name'])
```

**`Export email Failed Report`** then **`Create file Failed Report`** into
```
concat('/Shared Documents/02 - Sales/05 - Published Reports/_Unclassified/', formatDateTime(utcNow(), 'yyyy-MM'), '/_Failed')
```
Build this folder path from `utcNow()` rather than from `Compose Week Ending`, because the failure may have occurred before that Compose ran.

**`Post message in a chat or channel Failure Alert`** (Microsoft Teams)

| Field | Value |
| --- | --- |
| Post as | **Flow bot** |
| Post in | **Group chat** |
| Group chat | Scroll to the bottom of the dropdown, choose **Enter custom value**, and paste `19:7506e9ab0358413c9932c88c52d6cece@thread.v2` |
| Message | *(below)* |

Use the custom value rather than picking `SPS Report Hub` from the list. The picker shows only the 50 most recent named group chats, so a selection made today can silently stop resolving after a quiet stretch; the thread ID always resolves. See section 3.5 for the membership prerequisite.

```
concat('**SPS filing flow failed**', '<br>Subject: ', coalesce(triggerOutputs()?['body/Subject'], '(none)'), '<br>From: ', coalesce(triggerOutputs()?['body/From'], '(none)'), '<br>Received: ', coalesce(triggerOutputs()?['body/DateTimeReceived'], '(none)'), '<br>', outputs('Compose_Error_Summary'), '<br>[Open run](', outputs('Compose_Run_Link'), ')')
```

**`Terminate Failed`** (Control > Terminate)

| Field | Value |
| --- | --- |
| Status | `Failed` |
| Code | `SPSFilingError` |
| Message | `outputs('Compose_Error_Summary')` |

This is what makes **Resubmit** work properly: the run shows Failed, someone fixes the cause, clicks Resubmit, and the message is reprocessed against the same trigger payload.

### 7.5 Retry policy

On the three SharePoint write actions (`Create file New Report`, `Update file Existing Report`, `Update file properties Report Metadata`), set **Settings > Retry Policy** to **Exponential Interval**, count `4`, interval `PT10S`. This absorbs SharePoint throttling (429) and the transient folder-creation conflict described in section 3.4, without any concurrency setting.

Leave `Get file metadata using path Existing File` on the **default** retry policy. Retrying an expected 404 four times wastes four requests on every single new file, which at ~10,000 files a year is 40,000 wasted requests against the budget in section 3.2.

---

## 8. Step 7: Backfill and test harness

The backfill is the parser's acceptance test as much as it is a data-loading job. The spec is right that it should share the production parse logic rather than be a separate script, because two implementations drift and the day they drift is the day the library stops being trustworthy.

### 8.1 Structure: decided

Drift needs two *live* copies, so the structural decision reduced to one operational question:

> **After go-live, will anything other than the email trigger need to run the parser on an ongoing basis?**

**Answered: no.**

**So: export a copy of the production flow, swap the trigger, run the backfill, delete the copy.** There is then no second implementation to drift, because it stops existing. If another backfill is ever needed, export a fresh copy from the then-current production flow. That is zero-drift by construction and costs nothing to build. Section 8.1.2 records the child-flow alternative in case the answer ever changes.

### 8.1.1 What covers re-filing instead

The scenario that would otherwise justify keeping a permanent second copy is re-filing: a report lands in `_Unclassified`, someone adds the missing mapping row, and now the original message needs re-processing. That sounds like a recurring backfill. It is not, because of two properties this design already has:

- **The mapping list is read at run time.** Adding a retailer changes behaviour with no flow edit at all, so the flow definition is byte-identical before and after the fix.
- **Power Automate keeps 28 days of run history**, and a run can be resubmitted from it. Resubmitting replays the original trigger payload through the current flow, which now reads the corrected mapping list.

So the remediation loop is: add the mapping row, open run history, resubmit. No backfill flow involved. The weekly control report (section 9) surfaces `_Unclassified` every Monday, which keeps stragglers comfortably inside the 28-day window.

Two limits worth knowing before you rely on it. Resubmission is capped at **20 runs at a time**, and the default 28-day retention is an environment setting that an administrator can lower. Confirm nobody has reduced it below 28 days.

The case that genuinely needs a backfill is re-parsing mail **older than 28 days**: a parser bug found late, or a retailer added retroactively. That is real but rare, and an export made at that moment is exactly as correct as a permanent child flow would have been. Note also that re-parsing old mail only *adds* the file in the right place; it does not remove the wrongly-filed copy, so a late fix needs manual cleanup either way.

### 8.1.2 The child flow, recorded in case the answer ever changes

If something else ever does need to call the parser on an ongoing basis, an on-demand re-file button or a Power Apps front end, this is the structure:

1. **`SPS Analytics - Parse and File (child)`**: the logic from 6.3 to 6.10, with a **Manually trigger a flow** trigger taking Subject, From, DateTimeReceived, InternetMessageId, MessageId and the attachments array as inputs.
2. **`SPS Analytics - File Reports to SharePoint`**: the production flow. Trigger, then **Run a Child Flow**.
3. **`SPS Analytics - Backfill`**: manual trigger, reads the mailbox with pagination, calls the same child.

Three constraints that are easy to discover too late:

- **You cannot refactor into this later without risk.** Microsoft's documented known issue: create the parent and all child flows **directly in the same solution**, because importing a flow into a solution "might get unexpected results". So this is a day-one commitment, not a later cleanup.
- **Child flows only support embedded connections.** Anything beyond built-in actions and Dataverse, which here means both Office 365 Outlook and SharePoint, must be switched to **Use this connection** rather than **Provided by run-only user**, on the child flow's Run only users tile. Connections cannot be passed from parent to child. In practice that hard-binds the child to `svc-sps-filing@swimusa.com`, which is the intended identity anyway.
- **Run history splits in two.** A parse failure shows as a generic failure on the parent plus a separate child run to go and find. That is real friction for anyone who is not already comfortable in Power Automate, and it works against the "make failures legible" goal the rest of this design aims at.

An earlier draft of this guide recommended the child flow. Three things changed the balance: the mapping list being read at run time means retailer changes need no flow edit, resubmit covers the 28-day remediation window for free, and the child-flow path turns out to be a day-one architectural commitment rather than a refactor that can be deferred. Because it cannot be retrofitted safely, revisiting this means rebuilding both flows in a fresh solution.

If a second copy ever does live alongside production, write **"any parser change must be applied to both flows"** at the top of both flow descriptions.

### 8.2 The backfill window

**Confirmed: the mailbox was created on 2026-08-11**, so the window is `2026-08-11` through today and there is nothing older to find.

| | |
| --- | --- |
| Window | 2026-08-11 to 2026-09-14, **35 days, 5.0 weeks** |
| Fiscal weeks | **FY2026 W28 to W32** |
| Messages | **1,001**, the full Inbox |
| Rate | ~200 messages/week |

**The library's history therefore begins at FY2026 week 28.** This is a permanent property of the archive, not a gap to be closed later, and it is worth recording somewhere a business user will find it. Put a short `_README.txt` in `/02 - Sales/05 - Published Reports/` saying so, or someone will eventually spend an afternoon hunting for February.

Going back to FY2026 week 1 would mean asking SPS to re-send W01 to W27. That has been considered and declined; note it here only so the decision is on the record rather than rediscovered.

### 8.3 The backfill reader

**`Get emails Backfill`** (Office 365 Outlook > **Get emails (V3)**)

| Field | Value |
| --- | --- |
| Original Mailbox Address | `sps-analytics@swimusa.com` |
| Folder | `Inbox` (repeat per folder if 8.2 finds mail elsewhere) |
| Include Attachments | **Yes** |
| Top | `1000` (the maximum) |
| Search Query | `received:2026-08-11..2026-08-31` (chunk 1 of 2; see below) |

Settings: **Pagination On**, Threshold `5000`.

**Two chunks, oldest first: August then September.** This is not optional tidiness. `Top` caps at **1,000** and the Inbox holds **1,001** messages, so a single pass silently drops one. Splitting at the month boundary puts roughly 600 in the first chunk and 400 in the second, both comfortably inside the cap.

Three documented gotchas, each of which will cost you a morning if you hit it blind:

- **The To / From / Subject Filter fields only examine the first 250 messages** in the folder, so they return silently incomplete results at this volume. Use **Search Query**, which searches the whole folder.
- **`Top` is capped at 1,000**, which is why the window is chunked rather than paged in one pass.
- **Run history is 28 days.** If you want a record of what the backfill did, capture the run outputs as you go rather than relying on history being there next month.

Process oldest first, and put a **Delay** of 2 seconds inside the loop.

**Budget the request cost before you start:**

| | |
| --- | --- |
| 1,001 messages at ~30 actions each | **~30,000 Power Platform requests** |
| Days of full budget on M365 seeded (6,000/day) | **5 days** |
| Days of full budget on Power Automate Premium (40,000/day) | **under 1 day** |

This is the clearest practical argument for the Premium licence in section 3.2: with it the backfill is an afternoon, without it the same work has to be rationed across a working week. Either way, remember the production trigger draws on the same owner's budget at the same time.

### 8.4 Sequence: mind the gap between backfill and trigger

The trigger does not retroactively collect mail that arrived while it was off. It starts from the moment you enable it. So "backfill, then enable" opens a gap exactly as wide as the backfill takes, and mail arriving in that gap is filed by neither.

At 1,001 messages the backfill is an afternoon on a Premium licence, so the gap is hours rather than days, and SPS delivers in Sunday-to-Tuesday bursts. Run it on a Thursday and the gap may well contain nothing at all. It is still free to avoid.

**Recommended order:**

1. Validate the parser against `_Test` (section 10).
2. Point `Compose Library Root` at the production path.
3. **Enable the production trigger.** From this moment nothing new is missed.
4. Run the backfill, August chunk then September.
5. Reconcile counts (8.5) and run the folder check (8.6).

The overlap between the September chunk and live traffic is safe by design: the `SourceMessageId` guard skips anything already filed, and the week-anchored filename means a message caught by both resolves to the same target. That guard is doing real work here, not just catching replays.

**If you would rather see the backfill verified before anything goes live**, that is a legitimate preference at this size. Run the backfill first, then immediately before enabling the trigger, run one more small chunk covering the hours the backfill itself took. Just do not skip that last chunk, because it is the whole gap.

### 8.5 Expected outcome, and the pass/fail line

The audit read all 1,001 messages, so this is a known quantity rather than an estimate:

| Destination | Expected count |
| --- | --- |
| `2026/` (routed reports) | **997** |
| `_Admin/2026/` | **4** (two SPS account notices, one Retail Intelligence newsletter, one Retailer Data Availability Report) |
| `_Unclassified/` | Only the `3. SALES - DOOR PERFORMANCE` instances |

**The pass/fail line: run the August chunk, then stop and look.** If more than a handful of it landed in `_Unclassified`, fix the mapping list before running September. Checking between the two chunks turns a bad parse into a twenty-minute problem.

These three numbers are the parser's acceptance test. The audit covered exactly this mail, so any material deviation from 997 / 4 / a handful means the flow is not doing what the spec's own analysis says it should, and that is worth understanding before the library is trusted.

### 8.6 The check the backfill gives you for free

After the backfill, run this against the library. It is the direct proof of the 53-file requirement:

> Group the **By Week** view by folder, and sort descending by item count. **No leaf folder should hold more than 5 files.**

The window is five reporting weeks (W28 to W32) and the design allows one file per folder per week, so five is the ceiling. Any folder holding six or more means two messages in one reporting week resolved to different filenames, which is either a resend the week-anchor failed to collapse or a parse producing two different brands for the same series. Both are worth chasing before the library is trusted, and both are invisible unless you look at it this way.

---

## 9. Step 8: The weekly control report

A second, scheduled flow. The spec is right that this is what makes the whole thing trustworthy, and it is worth being specific about why: **an empty `_Unclassified` folder is the weekly proof that the parser still matches what SPS is sending.** Without it, parser drift is invisible until someone cannot find a report at month end.

**Flow name: `SPS Analytics - Weekly Control Report`**

| Component | Configuration |
| --- | --- |
| Trigger | **Recurrence**, Weekly, Monday, 07:00, Time zone `Eastern Standard Time` |
| Action 1 | SharePoint **Get files (properties only)**, Library `Documents`, Filter Query `WeekEnding eq '@{formatDateTime(addDays(utcNow(), -2), ''yyyy-MM-dd'')}'` |
| Action 2 | SharePoint **Get files (properties only)**, Limit Entries to Folder `/02 - Sales/05 - Published Reports/_Unclassified`, Include Nested Items **Yes** |
| Action 3 | **Select** + **Create HTML table**, grouped by `Retailer` |
| Action 4 | Office 365 Outlook **Send an email (V2)**, To `sps-hub-alerts@swimusa.com` |

The filter in Action 1 works only because `WeekEnding` is an **indexed** column (section 2.3). On a library past 5,000 items an unindexed filter is refused outright, and this flow would start failing roughly six months after go-live, which is exactly when you have stopped watching it.

What the email must contain, in priority order:

1. **Files written this week, by retailer**, next to the same count from the prior week. A variance is the signal. If Dillards normally lands 49 files and lands 31, somebody should know on Monday, not at month end.
2. **Everything sitting in `_Unclassified`**, with `SourceSubject` shown in full so the fix is obvious.
3. **Anything with `ParseConflict = true`** from the past week.
4. **Failed runs** in the past seven days.

---

## 10. Step 9: Test plan

### 10.1 Before you send a single test

- Point the flow at a **test folder** first. Change `Compose Library Root` to `/Shared Documents/02 - Sales/05 - Published Reports/_Test`, run the whole plan, then change it back. That one Compose is the only thing that needs changing, which is why it exists.
- Confirm the flow's Teams connection account is a member of **SPS Report Hub** (section 3.5), then post one test message to the chat before wiring section 7.4. A membership problem surfaces here in one minute or in section 7.4 as a confusing empty picker.

### 10.2 Parser trace table

These nine subjects are taken from the spec's live examples and cover every rule in the mapping list. **Verify these against the trace before you send anything**, because you can check all nine in ten minutes on paper and each one costs twenty minutes to test by email.

| # | Subject (as sent) | Received | Expected path (under the year) | Expected filename |
| --- | --- | --- | --- | --- |
| 1 | `1. SALES - CONTROL BRANDS DILLARDS STYLE SELLING To-Date Analysis SUPPLIER` | Mon 2026-09-14 | `Dillards/01 Style Selling/Control Brands/` | `2026-09-12_DILLARDS_CONTROL-BRANDS_STYLE-SELLING_SUPPLIER.xlsx` |
| 2 | `DILLARDS Qlik Sell Thru Sales Report RL` | Mon 2026-09-14 | `Dillards/06 Qlik Sell Thru/RL/` | `2026-09-12_DILLARDS_RL_QLIK-SELL-THRU.txt` |
| 3 | `4. SALES - MIRACLESUIT MACYS by Door & Style Performance to Date` | Sun 2026-09-13 | `Macys/05 Door and Style/Miraclesuit/` | `2026-09-12_MACYS_MIRACLESUIT_DOOR-AND-STYLE.xlsx` |
| 4 | `SALES - ALL DIVISIONS - MACYS WTD MTD STD & YTD 4-5-4 Calendar To-Date Analysis` | Sun 2026-09-13 | `Macys/08 Division Rollups/All Divisions/` | `2026-09-12_MACYS_ALL-DIVISIONS_ROLLUP_454.xlsx` |
| 5 | `SPS RETURNS REPORT - DILLARDS Weekly Trend Analysis` | Mon 2026-09-14 | `Dillards/07 Returns/All Brands/` | `2026-09-12_DILLARDS_ALL-BRANDS_RETURNS.xlsx` |
| 6 | `2. SALES - MIMI SIGNATURE- MAYCS Weekly Trend Analysis` | Mon 2026-09-14 | `Macys/02 Weekly Trend/Mimi Signature/` | `2026-09-12_MACYS_MIMI-SIGNATURE_WEEKLY-TREND.xlsx` |
| 7 | `3. SALES -� S3 KOHLS WTD, MTD & STD To-Date Analysis` | Mon 2026-09-14 | `Kohls/03 Period To-Date/S3/` | `2026-09-12_KOHLS_S3_PERIOD-TO-DATE.xlsx` |
| 8 | `SALES - CONTROL BRANDS - DILLARDS WTD MTD STD & YTD To-Date Analysis NRF` | Tue 2026-09-08 | `Dillards/03 Period To-Date/Control Brands/` | `2026-09-05_DILLARDS_CONTROL-BRANDS_PERIOD-TO-DATE_NRF.xlsx` |
| 9 | `3. SALES - LAUREN MISSY DILLARDS  WTD,MTD,STD To-Date Analysis` | Mon 2026-09-14 | `Dillards/03 Period To-Date/Lauren Missy/` | `2026-09-12_DILLARDS_LAUREN-MISSY_PERIOD-TO-DATE.xlsx` |

Each row exercises something specific: 1 the trailing-calendar rule, 2 Qlik brand codes the attachment does not carry, 3 a multi-word family token, 4 family specificity beating `WTD`/`STD`, **5 the priority rule that stops Returns filing as Weekly Trend**, 6 the `MAYCS` typo alias, 7 non-ASCII corruption plus the two-character brand `S3`, 8 the trailing `NRF` calendar, 9 doubled spaces plus `LAUREN MISSY` beating `LAUREN`.

### 10.3 Behaviour tests

| # | Test | Send | Expect | Check |
| --- | --- | --- | --- | --- |
| T1 | **Resend collapses** | Test 4's subject again, 24 hours later, different body | **No new file.** `2026-09-12_MACYS_ALL-DIVISIONS_ROLLUP_454.xlsx` gains **version 2** | Folder count unchanged; Version History shows 2 |
| T2 | **Replay is a no-op** | Resubmit the T1 run from run history | No new file, **no new version** | Version still 2 |
| T3 | **Week boundary** | Test 3's subject received Sun **2026-09-13** and again Mon **2026-09-14** | Both resolve to `2026-09-12`, one file | This is the case ISO weeks get wrong |
| T4 | **Year boundary** | Any valid subject received Thu **2026-01-01** | Files under **`2025/`**, week ending `2025-12-27` | Not `2026/` |
| T5 | **Unroutable** | `3. SALES - DOOR PERFORMANCE` | `_Unclassified/2026-09/`, run **Succeeded**, `SourceSubject` populated | Run is green, not red |
| T6 | **Non-report sender** | Anything from `no-reply@spscommerce.com` | `_Admin/2026/`, Succeeded | |
| T7 | **Unknown sender** | Anything from your own address | `_Admin/2026/`, Succeeded, **not discarded** | |
| T8 | **Signature only** | Valid subject, body with an inline logo, no report attached | `_Unclassified/2026-09/_Links/` + `.eml` + Teams alert | Logo is **not** filed as a report |
| T9 | **Link report** | Valid subject, body with a download URL, no attachment | Same as T8 | `.eml` opens with link intact |
| T10 | **Cross-retailer** | A subject containing `TOP 6 ACCTS` | `2026/_Cross-Retailer/08 Division Rollups/All Brands/` | Brand is **not** `TS` |
| T11 | **Two attachments** | Valid subject, two valid `.xlsx` | Two files, both named from the same subject | Second overwrites the first, and the filename grammar cannot distinguish them. See section 11, item 9. |
| T12 | **Genuine failure** | Rename the destination folder mid-run, or revoke list access | Run **Failed**, `.eml` in `_Failed/`, Teams alert with a working run link | Then Resubmit and confirm it succeeds |
| T13 | **New retailer** | Add a `Retailer` row, send a matching subject | Files correctly with **no flow edit** | This is the maintainability requirement, tested |

T10 is worth running even though it looks obscure: it is the bounded-matching case from section 5.3, and a naive parser fails it silently and weekly.

### 10.4 Go-live sequence

Note that the trigger goes on **before** the backfill, not after. Section 8.4 explains why: a multi-day backfill would otherwise leave a gap of live mail that neither the trigger nor the backfill collects.

1. Parser trace table (10.2) verified on paper.
2. Behaviour tests T1 to T13 pass against `_Test`.
3. All five indexed columns created (section 2.3). Before any file is written.
4. `Compose Library Root` switched to the production path.
5. **Trigger enabled.** Nothing new is missed from this point.
6. Backfill August chunk run, then **stop and inspect** against section 8.5.
7. September chunk run.
8. Counts reconciled against 997 / 4 / a handful (8.5), leaf-folder check passed (8.6).
9. `_README.txt` added to the report root noting that history begins 2026-08-11 (section 8.2).
10. First Monday control report reviewed by a human before anyone relies on the library.

---

## 11. Ambiguities in the source documents, and how the flow resolves each

You asked me to flag these explicitly. Each row is a real ambiguity or inconsistency, followed by the resolution built into this guide.

| # | Issue | Resolution |
| --- | --- | --- |
| 1 | **`_Cross-Retailer` path contradicts itself.** Spec section 2's tree draws it under `2026/`; its folder rules say `_Cross-Retailer/{YYYY}/`. | Year first: `{YYYY}/_Cross-Retailer/{Family}/{Brand}/`. Consistent with every other path. |
| 2 | **`TOP 6 ACCTS` is both a cross-retailer marker and a family trigger.** | Both, by design. The retailer scan resolves `_Cross-Retailer` (priority 900) and the family scan independently resolves `08 Division Rollups`. Separate `MapType` rows make this explicit rather than accidental. |
| 3 | **`ALL BRANDS TOTAL` is both a family trigger and a brand.** Spec section 4.3 rule 3 and section 4.6 both claim it. | Split into its own family row with `DefaultBrand = ALL-BRANDS`. The brand scan runs on the subject with the family token removed, so it cannot double-count, and the default is the sensible one rather than `ALL-DIVISIONS`. |
| 4 | **Matching case is never specified.** The spec mixes `Qlik Sell Thru`, `STYLE SELLING` and `by Door & Style Performance`. | Everything is uppercased before matching, and all tokens are stored uppercase. WDL's string functions are case-insensitive anyway, so this is belt and braces, but it makes behaviour deterministic. |
| 5 | **"Pad hyphens to ` - `" breaks live subjects.** It converts `4-5-4 Calendar` to `4 - 5 - 4 Calendar`, so the calendar token stops matching and every Macys 4-5-4 rollup loses its calendar segment. | Rejected. Replaced by the allowlist rule, which turns hyphens into spaces and lets space-collapsing handle it. See section 5.2. |
| 6 | **Two-character brand codes have no boundary rule.** `TS` matches inside `ACCTS`; `PB` matches inside `LB PB`. | All matching is bounded-token. `PB` versus `LB PB` is additionally resolved by length priority. See section 5.3. |
| 7 | **`FiscalWeek` is defined as the ISO week.** ISO weeks start Monday; retail weeks start Sunday. The audit's own dates split one reporting week across ISO 37 and 38. | Replaced by `WeekEnding` (a real date column) plus an optional 4-5-4 lookup. See sections 1.2 and 2.3. |
| 8 | **Apostrophe handling is under-specified.** Stripping `'` is stated; the curly `’` is not, and it is the form Outlook autocorrect produces. | Both are stripped before the allowlist runs. If the curly character will not paste into the designer, the subject degrades to `MACY S`, which fails to match and routes to `_Unclassified` rather than misfiling. Safe failure, visible in the weekly digest. |
| 9 | **The filename grammar cannot distinguish two attachments on one message.** The spec observes one attachment per message but never states it as a constraint. | The flow processes all attachments; if two resolve to the same name the second overwrites the first and creates a version. **This is a real gap**, mitigated rather than solved: T11 tests it, and the weekly `ParseConflict` review surfaces it. If SPS ever starts sending two reports per message, add an ordinal suffix. Not worth building on speculation today. |
| 10 | **Extension is hardcoded per family** (`.xlsx` everywhere except Qlik `.txt`). | Taken from the actual attachment instead. The spec is right that `attachment.name` is worthless for identity, but the extension describes the bytes you were sent. See section 1.3. |
| 11 | **`_Admin` is not year-scoped**, unlike everything else. | Year-scoped, for consistency and bounded growth. |
| 12 | **`SourceMessageId` is called "the dedupe key"** but cannot detect a resend. | Demoted to a replay guard, with filename collision promoted to the resend rule. See section 1.4. This is the change that actually enforces your 53-file ceiling. |
| 13 | **`MACY'S` appears as its own retailer row** after apostrophe stripping has already produced `MACYS`. | Redundant. Harmless if kept, omitted here. |
| 14 | **Volume is stated two ways**, "approximately 200 weekly" and "~10,000 annually". | Consistent: 1,001 messages over 34 days is 204/week, 10,600/year. Used as the basis for the licensing arithmetic in section 3.2. |

---

## 12. Vendor-side defects to raise with SPS

Four things in the current feed are SPS defects that this flow works around. The workarounds are solid, but they are workarounds, and they are worth a note to your SPS rep rather than carrying forever.

| # | Defect | What it costs you |
| --- | --- | --- |
| 1 | **Retailer missing from the subject.** `3. SALES - DOOR PERFORMANCE` carries no retailer and no brand. | Unroutable by any parser, human included. Every instance lands in `_Unclassified` and needs a person. This is the only defect that causes an actual work item every week. |
| 2 | **Character-encoding corruption** in at least six recurring subject lines. | Forces the allowlist normalization step. Currently tolerated, but a corruption landing *inside* a retailer or brand token rather than beside it would misroute rather than fail visibly. |
| 3 | **Brand identity absent from Qlik attachment filenames.** Five different Dillards brand feeds all attach `DILLARDS Qlik Sell Thru Sales Report.txt`. | The brand exists only in the subject. If the subject format ever changes, that information is gone from the library permanently, with no way to recover it from the file. |
| 4 | **Inconsistent spacing and punctuation** across otherwise identical recurring subjects. | The entire normalization layer exists because of this. |

**The ask to put to SPS, in one sentence:** *can the reports be delivered with the reporting period date and the brand code in the attachment filename?*

If they can, several sections of this design become unnecessary: the week-anchoring in 1.2 becomes a preserved date rather than a derived one, the Qlik brand codes stop depending on subject parsing, and defect 3 stops being a single point of failure. Worth asking before you consider this design finished. It is a small request that removes the most fragile assumption in the build.

Defect 1 is worth raising separately and with more force, because it is the only one generating recurring manual work.

---

## 13. Step 10: Running it

### 13.1 Monitoring, and who gets told

| Signal | Where | Cadence | Audience |
| --- | --- | --- | --- |
| A run failed | **SPS Report Hub** chat, section 7.4 | Immediate | IT / flow owner |
| A report arrived as a link | **SPS Report Hub** chat | Immediate | Analytics team |
| Something is unclassified | Weekly control report, `sps-hub-alerts@swimusa.com` | Monday 07:00 ET | Analytics team |
| Volume variance by retailer | Weekly control report, `sps-hub-alerts@swimusa.com` | Monday 07:00 ET | Analytics team |
| Flow disabled by the platform | Power Automate email to the owner | Automatic | Flow owner |
| Request budget approaching the cap | Power Platform admin center capacity report | Monthly | IT |

Two platform behaviours to put on the runbook, because both are quiet:

- **Power Automate disables a flow that fails continuously** and emails the owner. If the owner is a service account nobody reads, that email goes nowhere. Set the service account mailbox to forward to `sps-hub-alerts@swimusa.com`. This is the single most common way an automation dies unnoticed.
- **Connection expiry.** The Office 365 Outlook connection needs periodic reauthentication. Inside a solution, connection references make this a one-place fix. Check connection health monthly.

### 13.2 Adding a new retailer, report type or brand

This is the procedure for someone on your team, and it requires no Power Automate access at all.

1. Open **CompanyHub > SPS Filing Map**.
2. Look at a real subject line from the new report. Write down the piece that identifies what you are adding.
3. **Normalize it**: uppercase, drop apostrophes, replace every character that is not a letter, number or `&` with a space, collapse double spaces. `Macy's Off 5th` becomes `MACYS OFF 5TH`.
4. **New item**, and fill in:

| Column | What to enter |
| --- | --- |
| Title | The normalized token from step 3 |
| MapType | `Retailer`, `ReportFamily`, `Brand` or `Calendar` |
| MatchMode | `Token` (almost always) |
| Priority | **Retailer or Brand:** count the characters in the token. **ReportFamily:** see step 5. |
| OutputCode | Filename segment. Uppercase, hyphens for spaces: `MACYS-OFF-5TH` |
| FolderName | Folder segment, written how a human would: `Macys Off 5th` |
| DefaultBrand | ReportFamily only, and only if the family never carries a brand |
| Active | Yes |

5. **If you added a ReportFamily**, check whether its token could appear in a subject that another family also matches. If so, give it a **higher** Priority than that other family. Sort the list by Priority descending and read down: the first row that could match a given subject is the one that wins.
6. **Test it.** Send yourself a message with that subject to `sps-analytics@swimusa.com` from an address in the Sender rows, and confirm the file lands where you expect. Delete the test file afterwards.
7. If it landed in `_Unclassified`, the token does not match. Open the unclassified file's **SourceSubject** column: that is the exact normalized string the flow saw, and your token has to appear inside it as whole words.

**Never edit the flow to add a retailer.** If a change seems to need a flow edit, it is a new *kind* of rule, not a new value, and it should come to IT.

### 13.3 Things that will break it, and what to do

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Everything suddenly unclassified | Someone edited the mapping list and broke normalization on a token (added punctuation, lowercase) | Check recent list version history |
| One report unclassified every week | SPS changed that subject line | Compare `SourceSubject` against the token, update the row |
| Runs failing with 403 | Full Access on the shared mailbox revoked, or the connection expired | Re-grant, wait two hours (section 3.1), reauthenticate |
| Runs failing with 429 | Request budget exhausted | Section 3.2. Check whether a backfill is running. |
| Weekly report action fails after ~6 months | Library passed 5,000 items and `WeekEnding` is not indexed | Section 2.3 |
| A folder holds more than 53 files | Two messages in one reporting week produced different filenames | Check `SourceSubject` on both; usually a brand parsed two ways |
| Flow silently stopped | Platform disabled it after repeated failures | Owner's mailbox, section 13.1 |

---

## 14. Decisions

### 14.1 Confirmed

| # | Decision | Answer | Built into |
| --- | --- | --- | --- |
| 1 | Flow owner | `svc-sps-filing@swimusa.com` | 3.2, 3.5 |
| 2 | Library | Folder inside `Documents`, as given | 2.1 |
| 3 | Retention | **3 years**, always retained | 2.1, 2.3 |
| 4 | Week-ending day | **Saturday.** NRF 4-5-4 weeks run Sunday to Saturday; the fiscal year ends on the Saturday closest to 31 January | 1.2, 6.3 |
| 5 | `FiscalWeek` | Build it. Calendar generated to `docs/sps-fiscal-calendar-454.csv`, FY2025 to FY2028 | 2.3, 6.9 |
| 6 | Backfill parity | Nothing but the trigger runs the parser ongoing, so: **export a copy, run it, delete it** | 8.1 |
| 7 | Alert destinations | SPS Report Hub chat and `sps-hub-alerts@swimusa.com`; service account already in the chat | 3.5, 7.4, 9 |
| 8 | Non-sortable date rewriting | Leave disabled. Zero of 1,001 attachments carry a date | 6.9 |
| 9 | Year in the folder path | **Calendar year**, with `FiscalYear` and `FiscalWeek` as columns | 1.1, 2.3, 2.4 |
| 10 | Backfill window | **2026-08-11 to today**, the whole Inbox. 5 weeks, 1,001 messages, FY2026 W28 to W32 | 8.2 to 8.6 |
| 11 | Pre-August history | Mailbox was created 2026-08-11, so none exists. Library history begins at **FY2026 W28**; SPS re-send considered and declined | 8.2 |

### 14.2 Still open

**Nothing.** Every design decision is settled. What remains is the verification list below and the build itself.

### 14.3 Verify before go-live

These are not decisions, they are checks that something confirmed is actually in place.

| Check | Why it matters |
| --- | --- |
| `svc-sps-filing@swimusa.com` holds a **Power Automate Premium** licence | Without it the account is capped at 6,000 requests per 24 hours against a ~3,000 peak-day estimate. Section 3.2. |
| Full Access on `sps-analytics@swimusa.com` granted to that account, **at least two hours before** you build the trigger | Permission replication lag. Section 3.1. |
| All five indexed columns created **before the first backfill chunk** | Indexes cannot be added by hand above 20,000 items, which this library reaches at roughly month 22. Section 2.3. |
| Nobody has lowered the environment's 28-day run history retention | The re-filing loop in 8.1.1 depends on resubmit being available for 28 days. |

---

## Appendix A: Expression quick reference

Every WDL function this build uses, and why. Power Automate has **no regular expression function**, which is the constraint that shapes most of these choices.

| Function | Used for |
| --- | --- |
| `toUpper` | Deterministic matching (5.1) |
| `replace` | Apostrophe stripping, space collapsing, token removal |
| `trim` | Cleanup after normalization |
| `substring`, `length` | Character walking, sequence-number stripping |
| `indexOf` | Character allowlist, digit tests. **Case-insensitive.** |
| `lastIndexOf` | Splitting an extension off a name containing dots |
| `split`, `join`, `last`, `first` | Extension extraction, reassembling the filtered subject |
| `range` | Driving the `Select` that walks a string one character at a time |
| `contains`, `startsWith`, `endsWith` | Bounded-token matching. **All case-insensitive.** |
| `concat` | Path and filename assembly |
| `coalesce` | Null-safe defaults throughout |
| `if`, `and`, `or`, `not`, `equals`, `greater`, `empty` | Branching |
| `add`, `sub`, `mul`, `mod`, `min` | Week-ending arithmetic, filename truncation |
| `convertTimeZone` | UTC to Eastern |
| `dayOfWeek` | Week anchoring. **Returns 0 for Sunday through 6 for Saturday.** |
| `addDays`, `formatDateTime` | Week-ending date, `yyyy-MM-dd` and `yyyy-MM` output |
| `parseDateTime` | Optional non-sortable date rewrite. **Always pass `'en-US'`.** |
| `base64ToBinary` | Attachment content to file content |
| `utcNow` | Catch-scope paths that must not depend on earlier actions |
| `result` | Reading failed-action detail out of a scope |
| `workflow`, `actions`, `outputs`, `body`, `triggerOutputs`, `items`, `item` | Referencing runtime state |

Two syntax notes that cause most paste errors:

- A literal apostrophe inside a WDL string is written as **two** apostrophes. A string containing one apostrophe is therefore `''''`.
- An action name's spaces become underscores in expressions. `Compose Week Ending` is `outputs('Compose_Week_Ending')`.

## Appendix B: Reference documentation

| Topic | Source |
| --- | --- |
| Office 365 Outlook connector, triggers, limits | [learn.microsoft.com/connectors/office365](https://learn.microsoft.com/en-us/connectors/office365/) |
| SharePoint connector actions | [learn.microsoft.com/connectors/sharepointonline](https://learn.microsoft.com/en-us/connectors/sharepointonline/) |
| WDL expression function reference | [Workflow definition language functions](https://learn.microsoft.com/en-us/azure/logic-apps/workflow-definition-language-functions-reference) |
| Power Platform request limits | [Requests limits and allocations](https://learn.microsoft.com/en-us/power-platform/admin/api-request-limits-allocations) |
| Flow limits, concurrency, debatching | [Limits of automated, scheduled, and instant flows](https://learn.microsoft.com/en-us/power-automate/limits-and-config) |
| Trigger concurrency guidance | [Optimize Power Automate triggers](https://learn.microsoft.com/en-us/power-automate/guidance/coding-guidelines/optimize-power-automate-triggers) |
| List view threshold and indexing | [Manage large lists and libraries in SharePoint](https://learn.microsoft.com/en-us/troubleshoot/sharepoint/lists-and-libraries/items-exceeds-list-view-threshold) |
| Shared mailbox configuration | [Configure shared mailbox settings](https://learn.microsoft.com/en-us/microsoft-365/admin/email/configure-a-shared-mailbox) |
| Teams group chat from a flow | [Send a message in Teams using Power Automate](https://learn.microsoft.com/en-us/power-automate/teams/send-a-message-in-teams) |

## Appendix C: Files in this repository

| File | Purpose |
| --- | --- |
| `docs/sps-analytics-filing-flow-build-guide.md` | This guide |
| `docs/sps-fiscal-calendar-454.csv` | 209 NRF 4-5-4 fiscal week rows, FY2025 to FY2028, in `SPS Filing Map` column shape. Import directly; see section 2.3. |
