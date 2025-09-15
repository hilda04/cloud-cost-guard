import os, json, boto3, datetime, decimal
from collections import defaultdict

ce = boto3.client('ce')
s3 = boto3.client('s3')
sns = boto3.client('sns')

ENV_TAG_KEY = os.getenv('ENV_TAG_KEY', 'Environment')
ENV_TAG_VALUE = os.getenv('ENV_TAG_VALUE', 'nonprod')
SPIKE_PCT = float(os.getenv('SPIKE_PCT_THRESHOLD', '30'))
SPIKE_MIN = float(os.getenv('SPIKE_MIN_DOLLARS', '20'))
BUCKET = os.getenv('REPORTS_BUCKET')
ALERTS_TOPIC = os.getenv('AlertsTopicArn')  # optional via env; else inject below

# Helper for Cost Explorer date strings

def dstr(d):
    return d.strftime('%Y-%m-%d')

class Enc(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, decimal.Decimal):
            return float(o)
        return super().default(o)


def get_daily_costs(start, end, group_by_service=True):
    kwargs = {
        'TimePeriod': {'Start': dstr(start), 'End': dstr(end)},
        'Granularity': 'DAILY',
        'Metrics': ['UnblendedCost'],
        'Filter': {
            'Tags': {
                'Key': ENV_TAG_KEY,
                'Values': [ENV_TAG_VALUE],
                'MatchOptions': ['EQUALS']
            }
        }
    }
    if group_by_service:
        kwargs['GroupBy'] = [{'Type':'DIMENSION','Key':'SERVICE'}]

    results = []
    token = None
    while True:
        if token:
            kwargs['NextPageToken'] = token
        resp = ce.get_cost_and_usage(**kwargs)
        results.extend(resp['ResultsByTime'])
        token = resp.get('NextPageToken')
        if not token:
            break
    return results


def compute_spike(timeseries):
    # timeseries: list of days, each with groups by service
    day_costs = []
    per_service = defaultdict(list)
    for day in timeseries:
        total = 0.0
        if 'Groups' in day:
            for g in day['Groups']:
                amt = float(g['Metrics']['UnblendedCost']['Amount'])
                svc = g['Keys'][0]
                per_service[svc].append(amt)
                total += amt
        else:
            total = float(day['Total']['UnblendedCost']['Amount'])
        day_costs.append(total)

    if len(day_costs) < 8:
        return None

    yesterday = day_costs[-1]
    trailing = sum(day_costs[-8:-1]) / 7.0
    diff = yesterday - trailing
    pct = (diff / trailing * 100.0) if trailing > 0 else 0.0
    top = sorted(((svc, vals[-1]) for svc, vals in per_service.items() if vals), key=lambda x: x[1], reverse=True)[:5]
    return {
        'yesterday': yesterday,
        'trailing7': trailing,
        'diff': diff,
        'pct': pct,
        'top_services': [{'service': s, 'yesterday_cost': c} for s, c in top]
    }


def push_report(report):
    key = 'reports/summary.json'
    s3.put_object(Bucket=BUCKET, Key=key, Body=json.dumps(report, cls=Enc).encode('utf-8'), ContentType='application/json')
    # also write a dated snapshot
    date_key = f"timeseries/{report['as_of']}.json"
    s3.put_object(Bucket=BUCKET, Key=date_key, Body=json.dumps(report, cls=Enc).encode('utf-8'), ContentType='application/json')
    return f's3://{BUCKET}/{key}'


def maybe_alert(spike, topic_arn):
    if not topic_arn:
        return
    if spike['pct'] >= SPIKE_PCT and spike['diff'] >= SPIKE_MIN:
        msg = (
            f"Non‑prod cost spike detected for {ENV_TAG_VALUE}:\n"
            f"Yesterday: ${spike['yesterday']:.2f}\n"
            f"Trailing 7‑day avg: ${spike['trailing7']:.2f}\n"
            f"Change: +${spike['diff']:.2f} ({spike['pct']:.1f}%)\n\n"
            f"Top services: " + ", ".join([f"{t['service']} ${t['yesterday_cost']:.2f}" for t in spike['top_services']])
        )
        sns.publish(TopicArn=topic_arn, Subject='Cloud Cost Guard: non‑prod spike', Message=msg)


def handler(event, context):
    today = datetime.date.today()
    start = today - datetime.timedelta(days=14)
    timeseries = get_daily_costs(start, today, group_by_service=True)
    spike = compute_spike(timeseries)
    report = {
        'as_of': dstr(today),
        'env_tag_key': ENV_TAG_KEY,
        'env_tag_value': ENV_TAG_VALUE,
        'spike': spike,
        'timeseries': [
            {
                'date': d['TimePeriod']['Start'],
                'total': float(d['Total']['UnblendedCost']['Amount']) if 'Total' in d else sum(float(g['Metrics']['UnblendedCost']['Amount']) for g in d['Groups']),
                'by_service': [
                    {'service': g['Keys'][0], 'cost': float(g['Metrics']['UnblendedCost']['Amount'])}
                    for g in d.get('Groups', [])
                ]
            } for d in timeseries
        ]
    }

    push_report(report)

    # Pull topic from env or stack parameter injected via Lambda env override
    topic_arn = os.getenv('ALERTS_TOPIC_ARN', None)
    maybe_alert(spike, topic_arn)

    return {'ok': True, 'spike': spike}
