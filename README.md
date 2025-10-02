# AWS Fin Ops --> cloud-cost-guard
A solution to provide a tracking dashboard with email alerts to monitor cost spikes and propper tagging for AWS resources; targeting non prod / dev resources;
Cloud Cost Guard Dashboard and alerts for non‑prod AWS cost spikes and mis‑tagged resources;
Services used: S3, SNS, Lambda, EventBridge, CloudFront, CloudFormation, Amplify, WAF etc.


## What it does

* Monitors daily non‑prod spend via **Cost Explorer** and compares yesterday vs a 7‑day average.
* Sends **SNS email alerts** when a spike exceeds your thresholds.
* Audits resource **tags** using the **Resource Groups Tagging API** and lists non‑compliant items.
* Writes JSON reports to **S3** that power a simple **HTML dashboard** (Chart.js).

**Stack:** AWS Lambda, EventBridge (CloudWatch Events), SNS, S3, Cost Explorer, Resource Groups Tagging API.

---

## Architecture (at a glance)

```
EventBridge (daily) ─▶ Lambda: CostSpikeChecker ─▶ Cost Explorer ─┐
                                                          │       │
                                                          ├───────┼─▶ S3 (reports/summary.json)
                                                          │       │
EventBridge (daily) ─▶ Lambda: TagAuditChecker ─▶ Tagging API ────┘

SNS (email alerts)
Dashboard (HTML/JS) ◀── fetch() JSON from S3
```

---

## Prerequisites

* An AWS account with permissions to deploy CloudFormation/SAM stacks (Admin or equivalent for first run).
* A valid email address for SNS alert subscription.

> **Non‑prod filter:** By default, the app filters costs by tag `Environment = nonprod` and validates `Environment ∈ {nonprod, dev, qa, stage}`. You can change these via parameters during deployment.

---

## Option A — One‑click deploy from the AWS Serverless Application Repository (SAR)

**Recommended for most users.**

1. Open **Serverless Application Repository** in your AWS console.
2. Search for **Cloud Cost Guard** (Author: *Hilda Machando*).
3. Click **Deploy**.
4. Fill parameters:

   * `EnvironmentTagKey` → `Environment`
   * `EnvironmentTagValue` → `nonprod` (or your value)
   * `RequiredTags` → `Environment,Owner,CostCenter`
   * `AllowedEnvironmentValues` → `nonprod,dev,qa,stage`
   * `AlertEmail` → your email (confirm the SNS email after deploy)
   * `SpikePctThreshold` → `30`
   * `SpikeMinDollars` → `20`
   * `MakeReportsPublic` → `true` *(lets the dashboard read the JSON directly)*
5. Click **Deploy**. When complete, go to the stack **Outputs** and copy:

   * `ReportsSummaryUrl`
   * `ReportsTagAuditUrl`

### First run

* In the stack **Resources**, open each Lambda and click **Test** once so you don’t wait for the daily schedule.
* Confirm the SNS subscription email in your inbox.

### View the dashboard

* Use the included `web/dashboard.html` (in this repo) and replace the two URLs at the top with your **Outputs** URLs.
* Host `dashboard.html` on S3/CloudFront, GitHub Pages, or any static host.

---

## Option B — Deploy from source (no local installs; **CloudShell** in browser)

Use this if you prefer to deploy directly from source code.

1. In AWS Console, open **CloudShell** (top toolbar icon).
2. Create or pick an **S3 bucket** for build artifacts (unique name, same region). Example: `my-ccg-artifacts-1234`.
3. Clone the repo and build:

   ```bash
   git clone https://github.com/<your-username>/cloud-cost-guard.git
   cd cloud-cost-guard
   sam build
   sam package --s3-bucket my-ccg-artifacts-1234 --output-template-file packaged.yaml
   sam deploy --guided --template-file packaged.yaml --stack-name cloud-cost-guard
   ```
4. When prompted, provide the same parameters as in Option A.
5. Confirm the SNS email and perform the **First run** steps above.

> **Note:** If `sam build` complains about Python version, change `Runtime` in `template.yaml` from `python3.12` to `python3.9` for easier CloudShell builds.

---

## Parameters (summary)

* `EnvironmentTagKey` (default `Environment`)
* `EnvironmentTagValue` (default `nonprod`)
* `RequiredTags` (default `Environment,Owner,CostCenter`)
* `AllowedEnvironmentValues` (default `nonprod,dev,qa,stage`)
* `AlertEmail` (email for SNS alerts)
* `SpikePctThreshold` (percent over 7‑day average to alert; default `30`)
* `SpikeMinDollars` (minimum dollar increase to alert; default `20`)
* `MakeReportsPublic` (`true|false`) Enables a public S3 policy for JSON reads.

---

## Expected behaviour

* Lambdas run daily ~05:00 UTC, updating **summary.json** and **tag_audit.json** in S3.
* SNS email is sent if a spike exceeds thresholds.
* The dashboard renders KPIs, cost trend, top services, and a searchable, exportable tag audit.

---

## Fixing tag findings (remediation)

1. Open the resource in AWS Console → **Tags**.
2. Add required tags: `Environment`, `Owner`, `CostCenter`.
3. Ensure `Environment` is one of: `nonprod`, `dev`, `qa`, `stage`.
4. Save and wait for the next run (or re‑run the TagAuditChecker Lambda).

**Compliant resources** (all required tags present and valid) won’t appear in the findings list.

---

## Troubleshooting

* **403 or “AccessControlListNotSupported”**: Don’t set object ACLs. This template uses a **bucket policy** when `MakeReportsPublic=true`—the Lambdas should call `PutObject` **without** `ACL`.
* **Tag audit AccessDenied**: Ensure the Lambda role has `tag:GetResources`. This template uses the correct action. If customized, add `tag:GetResources`, `tag:GetTagKeys`, `tag:GetTagValues`.
* **No alerts**: Confirm the SNS email subscription.
* **No data**: Manually run both Lambdas once, then refresh the dashboard.

---

## Costs

Under light use, this is typically within the free/low tier: Lambda invocations, Cost Explorer queries (free), SNS, and minimal S3 storage.

---

## Cleanup

Delete the CloudFormation stack; it removes all created resources (except any data you added externally).

---

## License

MIT. See `LICENSE`.

