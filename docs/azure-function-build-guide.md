# SPS Analytics Filing: Azure Function Build and Deployment Guide

The filing job runs as an Azure Function App owned by IT. This guide covers the identity setup, deployment and operations. The **design** decisions it implements are unchanged and still documented in [`sps-analytics-filing-flow-build-guide.md`](sps-analytics-filing-flow-build-guide.md).

---

## 1. What changed, and what did not

Only the runtime changed. Every design decision carries over intact, and the reasoning behind each one, including the options rejected along the way, is recorded in [`architecture-decisions.md`](architecture-decisions.md).

| Decision | Status |
| --- | --- |
| Four-level folder structure, `{YYYY}/{Retailer}/{NN Family}/{Brand}/` | Unchanged |
| `{YYYY-MM-DD}_{RETAILER}_{BRAND}_{REPORT}[_{CALENDAR}].{ext}` | Unchanged |
| Week-ending Saturday anchor, not the received date | Unchanged |
| Overwrite on filename collision, `SourceMessageId` as replay guard | Unchanged |
| Mapping table in a SharePoint list, editable by the analytics team | Unchanged |
| `_Unclassified` / `_Admin` routing, nothing silently dropped | Unchanged |
| Metadata columns and indexing | Unchanged |
| Calendar year in the folder path, fiscal exposed as columns | Unchanged |

Three things got **better** by moving to code:

1. **The parser is unit-tested.** The nine-subject trace table is now `tests/test_trace_table.py`. It runs in 0.15 seconds instead of requiring nine test emails.
2. **Backfill cannot drift from production.** `backfill` and `file_reports` call the same `plan_filing`. The entire "child flow versus exported copy" question disappears.
3. **The fiscal calendar is computed, not transcribed.** `dates.py` derives it from the NRF rule, so `data/sps-fiscal-calendar-454.csv` and its 209 SharePoint rows are no longer needed.

One thing got worse and is worth knowing up front: **identity setup is real work**, and it needs a tenant admin rather than just the flow owner. That is section 3.

### What stays in Power Automate

**The weekly control report.** It reads a SharePoint view, formats a table and sends mail to `sps-hub-alerts@swimusa.com`. That is four trivial actions with no premium connector, and doing it in the Function would mean granting `Mail.Send`, which widens the app's permissions for no benefit. Keep it where it is.

---

## 2. Architecture

```
Timer (every 15 min)
   └─ file_reports ──► Graph: list inbox since now-24h
                         └─ per message
                              ├─ plan_filing()          pure, no I/O
                              ├─ Graph: does target path exist?
                              │     └─ yes + same SourceMessageId → skip
                              ├─ Graph: PUT file  (creates folders on the way)
                              └─ Graph: PATCH listItem fields

HTTP  backfill       same run() over an explicit date range
HTTP  parse          dry parse of one subject, no mailbox, no writes
```

**The 24-hour lookback is deliberate.** Rather than storing a watermark that can be corrupted or lost, each run re-examines the last day of mail and lets the `SourceMessageId` check discard anything already filed. An outage self-heals on the next run. Re-examining roughly 30 messages costs nothing.

### Repository layout

| Path | Purpose |
| --- | --- |
| `src/sps_filing/normalize.py` | The five normalization rules |
| `src/sps_filing/dates.py` | Week-ending anchor, NRF 4-5-4 fiscal calendar |
| `src/sps_filing/mapping.py` | Mapping table load and bounded-token matching |
| `src/sps_filing/parse.py` | Subject to retailer / family / brand / calendar |
| `src/sps_filing/plan.py` | Filenames, folder paths, metadata, attachment filter |
| `src/sps_filing/graph.py` | Microsoft Graph client |
| `src/sps_filing/filer.py` | Orchestration, the only module that does I/O |
| `function_app.py` | The three triggers |
| `data/sps_filing_map_seed.csv` | Import file for the SharePoint list, and the test fixture |
| `tools/generate_mapping_seed.py` | Regenerates the seed, keeping priorities consistent |
| `tests/` | 43 tests, including the trace table |

---

## 3. Identity setup

This is the part with sharp edges. Do it in this order.

### 3.1 Function App and managed identity

Create the Function App (Python 3.11, Linux, Consumption plan) and turn on the **system-assigned managed identity**. There is no app registration and no client secret to rotate.

Note both IDs from **Microsoft Entra ID > Enterprise applications > (your Function App)**:

- **Application ID** (`AppId`)
- **Object ID** (`ServiceId`)

> Take these from **Enterprise applications**, not App registrations. The two pages show different values and using the wrong one produces a confusing failure later.

### 3.2 SharePoint: `Sites.Selected`, scoped to one site

Assign the Graph app role to the managed identity. The portal cannot do this for managed identities, so use Graph PowerShell:

```powershell
Connect-MgGraph -Scopes AppRoleAssignment.ReadWrite.All,Application.Read.All
$mi    = Get-MgServicePrincipal -Filter "displayName eq 'func-sps-filing'"
$graph = Get-MgServicePrincipal -Filter "appId eq '00000003-0000-0000-c000-000000000000'"
$role  = $graph.AppRoles | Where-Object { $_.Value -eq 'Sites.Selected' }

New-MgServicePrincipalAppRoleAssignment -ServicePrincipalId $mi.Id `
  -PrincipalId $mi.Id -ResourceId $graph.Id -AppRoleId $role.Id
```

`Sites.Selected` grants nothing on its own. Grant the one site explicitly:

```powershell
Grant-PnPEntraIDAppSitePermission `
  -AppId "<Application ID>" `
  -DisplayName "func-sps-filing" `
  -Site "https://mainstreamswimsuits.sharepoint.com/sites/CompanyHub" `
  -Permissions Write
```

> **Do not also grant `Sites.ReadWrite.All` or `Files.ReadWrite.All`.** Graph permissions are a union and the most permissive wins, so adding either one silently defeats `Sites.Selected` entirely and the app regains access to every site in the tenant.

### 3.3 Exchange: `Mail.Read` scoped to one mailbox

**Do not grant `Mail.Read` in Entra ID at all.** App-only `Mail.Read` granted there reads *every mailbox in the organization*, and Microsoft is explicit that an Entra grant and an Exchange RBAC grant are additive: keeping both means the scope does nothing.

Grant it only through Exchange RBAC for Applications, which is what replaced the now-legacy Application Access Policies:

```powershell
Connect-ExchangeOnline   # requires the Organization Management role group

New-ServicePrincipal -AppId "<Application ID>" -ObjectId "<Object ID>" `
  -DisplayName "func-sps-filing"

New-ManagementScope -Name "SPS Analytics Mailbox" `
  -RecipientRestrictionFilter "PrimarySmtpAddress -eq 'sps-analytics@swimusa.com'"

New-ManagementRoleAssignment -App "<Object ID>" `
  -Role "Application Mail.Read" -CustomResourceScope "SPS Analytics Mailbox"
```

Verify, remembering that the test cmdlet deliberately bypasses the permission cache:

```powershell
Test-ServicePrincipalAuthorization -Identity "<Object ID>" `
  -Resource "sps-analytics@swimusa.com" | Format-Table
# expect: Application Mail.Read ... InScope True

Test-ServicePrincipalAuthorization -Identity "<Object ID>" `
  -Resource "<any other mailbox>" | Format-Table
# expect: InScope False
```

Run the second check. It is the one that proves the scoping works.

> **Permission changes take 30 minutes to 2 hours to reach the API**, longer for an app that has been active. `Test-ServicePrincipalAuthorization` bypasses that cache, so a green test plus a 403 from the app means you are waiting on the cache, not misconfigured.

### 3.4 The resulting blast radius

| Resource | Access |
| --- | --- |
| `sps-analytics@swimusa.com` | Read only |
| Every other mailbox | **None** |
| CompanyHub site | Write |
| Every other SharePoint site | **None** |
| Anything else | None |

That is a meaningfully smaller surface than the Power Automate design, where the connection account held Full Access to the mailbox and the user's own SharePoint permissions.

---

## 4. App settings

| Setting | Value |
| --- | --- |
| `SPS_SCHEDULE` | `0 */15 * * * *` |
| `SPS_MAILBOX` | `sps-analytics@swimusa.com` |
| `SPS_SP_HOSTNAME` | `mainstreamswimsuits.sharepoint.com` |
| `SPS_SP_SITE_PATH` | `/sites/CompanyHub` |
| `SPS_SP_LIBRARY` | `Documents` |
| `SPS_LIBRARY_ROOT` | `/02 - Sales/05 - Published Reports` |
| `SPS_MAPPING_LIST` | `SPS Filing Map` |
| `SPS_LOOKBACK_HOURS` | `24` |
| `SPS_DRY_RUN` | `false` (set `true` to log intended writes without making them) |

> **`SPS_LIBRARY_ROOT` has no `Shared Documents` prefix.** The Graph drive API addresses paths relative to the drive root, and the drive *is* the library. This differs from the Power Automate SharePoint connector, which wants the library name in the path. Getting this wrong creates a `Shared Documents` folder *inside* the library.

---

## 5. Local development

```bash
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
pytest                       # 43 tests, no tenant required

cp local.settings.json.example local.settings.json   # SPS_DRY_RUN is true
az login                     # DefaultAzureCredential picks this up locally
func start
```

The parser has no Azure dependency, so the whole trace table runs offline. That is the point of keeping `plan_filing` pure.

To regenerate the mapping seed after editing `tools/generate_mapping_seed.py`:

```bash
python tools/generate_mapping_seed.py
```

## 6. Deployment

```bash
func azure functionapp publish func-sps-filing --python
```

Or wire up GitHub Actions from this repo with `Azure/functions-action@v1` and an OIDC federated credential, which avoids storing a publish profile as a secret.

---

## 7. Go-live sequence

1. `pytest` green.
2. Create the SharePoint list `SPS Filing Map` and import `data/sps_filing_map_seed.csv` (73 rows).
3. Create all five indexed columns. **Before any file is written**: above 20,000 items SharePoint will not let an index be added at all.
4. Identity setup, section 3, including the negative test.
5. Deploy with `SPS_DRY_RUN=true`. Watch one timer run and read the intended paths in the logs.
6. Set `SPS_DRY_RUN=false`. The timer now files live mail; nothing new is missed from this point.
7. Backfill August, then **stop and check** against 997 / 4 / a handful:
   ```bash
   curl -X POST "https://func-sps-filing.azurewebsites.net/api/backfill?code=<key>" \
        -H "Content-Type: application/json" \
        -d '{"since":"2026-08-11","until":"2026-08-31"}'
   ```
8. Backfill September: `{"since":"2026-09-01"}`.
9. Leaf-folder check: no folder over 5 files for a five-week backfill.
10. Add `_README.txt` to the report root noting that history begins 2026-08-11.

---

## 8. Operations

### Monitoring

`file_reports` raises if any message failed, so the run shows as failed in Application Insights. Create one alert rule:

- Signal: `requests | where success == false and name == "file_reports"`
- Threshold: 1 in 15 minutes
- Action group: email `sps-hub-alerts@swimusa.com`

A single failing message does not stop the run. It stays in the mailbox, and the 24-hour lookback retries it automatically on the next pass, so an alert usually means something structural rather than a single bad email.

### Adding a retailer, report type or brand

Unchanged, and still no code:

1. Add a row to the **SPS Filing Map** list (see section 13.2 of the Power Automate guide for the field-by-field walkthrough).
2. Confirm it resolves, without sending an email:
   ```bash
   curl -X POST ".../api/parse?code=<key>" -H "Content-Type: application/json" \
     -d '{"subject":"1. SALES - NEW BRAND KOHLS STYLE SELLING To-Date Analysis"}'
   ```
3. If a real message was already misfiled, it will be re-processed by the next run only if it arrived inside the lookback window. Older than that, use `backfill` for that day.

The mapping list is read fresh on every run, so a new row takes effect within 15 minutes with no deployment.

### Changing parser behaviour

That *is* a code change, and it should be: a pull request, a test, a review. Add a case to `tests/test_trace_table.py` first, watch it fail, then make it pass.
