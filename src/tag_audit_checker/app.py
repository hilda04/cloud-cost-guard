import os, json, boto3

rg = boto3.client('resourcegroupstaggingapi')
s3 = boto3.client('s3')
sns = boto3.client('sns')

BUCKET = os.getenv('REPORTS_BUCKET')
ENV_KEY = os.getenv('ENV_TAG_KEY', 'Environment')
REQUIRED = [t.strip() for t in os.getenv('REQUIRED_TAGS','Environment,Owner,CostCenter').split(',') if t.strip()]
ALLOWED_ENV = [t.strip() for t in os.getenv('ALLOWED_ENV_VALUES','nonprod,dev,qa,stage').split(',') if t.strip()]
TOPIC = os.getenv('ALERTS_TOPIC_ARN', None)


def list_all_resources():
    token = None
    resources = []
    while True:
        kwargs = {'ResourcesPerPage': 100}
        if token:
            kwargs['PaginationToken'] = token
        resp = rg.get_resources(**kwargs)
        resources.extend(resp.get('ResourceTagMappingList', []))
        token = resp.get('PaginationToken')
        if not token:
            break
    return resources


def evaluate(resources):
    findings = []
    for item in resources:
        arn = item['ResourceARN']
        tags = {t['Key']: t['Value'] for t in item.get('Tags', [])}
        missing = [k for k in REQUIRED if k not in tags or not str(tags[k]).strip()]
        bad_env = (ENV_KEY in tags) and (tags[ENV_KEY] not in ALLOWED_ENV)
        if missing or bad_env:
            findings.append({
                'arn': arn,
                'tags': tags,
                'missing': missing,
                'invalid_environment': tags.get(ENV_KEY) if bad_env else None
            })
    return findings


def handler(event, context):
    resources = list_all_resources()
    findings = evaluate(resources)
    summary = {
        'total_resources': len(resources),
        'noncompliant': len(findings),
        'findings': findings[:200]  # cap for report size; full list can be paged if needed
    }
    s3.put_object(Bucket=BUCKET, Key='reports/tag_audit.json', Body=json.dumps(summary).encode('utf-8'), ContentType='application/json')

    if TOPIC and findings:
        msg = (f"Tag audit found {len(findings)} non‑compliant resources out of {len(resources)}. "
               f"Top 10 examples:\n" + "\n".join(f["arn"] for f in findings[:10]))
        sns.publish(TopicArn=TOPIC, Subject='Cloud Cost Guard: tag audit', Message=msg)

    return {'ok': True, 'noncompliant': len(findings)}
