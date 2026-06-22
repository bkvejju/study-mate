# Deploy StudyMate Explainers To S3

This guide explains how to publish the generated explainer site to Amazon S3 and when API calls will or will not work.

## Short answer: will API calling work from S3 website hosting?

Not as-is.

The frontend currently calls a relative endpoint:

- /api/study

That works when the FastAPI server is running on the same origin (local dev with study-mate serve), but an S3 static website has no backend route for /api/study.

So:

- Static browsing of generated explainers works from S3.
- AI actions (Summarise, Explain simply, Quiz me, Flashcards, Key terms) will fail unless you deploy the API separately and point the frontend to it.

## Recommended architecture for AI-enabled hosting

Use two components:

1. Static site on S3 (+ CloudFront preferred)
2. API service for /api/study (for example Lambda + API Gateway, ECS/Fargate, or EC2)

Then enable CORS on the API for your site origin.

## Prerequisites

1. AWS CLI installed and authenticated
2. A target AWS region
3. Generated files present locally in generated/explainers

Generate explainers first:

```bash
uv run study-mate explain
```

## Option A: quick S3 static website deployment (no AI API)

This is the fastest way to host explainers as static pages.

### 1. Set variables

```bash
export AWS_REGION=eu-west-1
export BUCKET_NAME=your-study-mate-site-bucket
```

### 2. Create bucket

If region is us-east-1:

```bash
aws s3api create-bucket --bucket "$BUCKET_NAME"
```

For other regions:

```bash
aws s3api create-bucket \
  --bucket "$BUCKET_NAME" \
  --region "$AWS_REGION" \
  --create-bucket-configuration LocationConstraint="$AWS_REGION"
```

### 3. Configure static website hosting

```bash
aws s3 website "s3://$BUCKET_NAME" \
  --index-document index.html \
  --error-document index.html
```

### 4. Allow public reads (website endpoint mode)

If your account policy allows public buckets, apply a read-only bucket policy:

```bash
cat > /tmp/studymate-s3-policy.json << 'JSON'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "PublicRead",
      "Effect": "Allow",
      "Principal": "*",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::BUCKET_NAME_PLACEHOLDER/*"
    }
  ]
}
JSON

sed -i '' "s/BUCKET_NAME_PLACEHOLDER/$BUCKET_NAME/g" /tmp/studymate-s3-policy.json

aws s3api put-bucket-policy \
  --bucket "$BUCKET_NAME" \
  --policy file:///tmp/studymate-s3-policy.json
```

### 5. Upload generated explainers

```bash
aws s3 sync generated/explainers/ "s3://$BUCKET_NAME/" --delete
```

### 6. Open the website

```text
http://<bucket-name>.s3-website-<region>.amazonaws.com
```

At this point, navigation and explainer pages work. AI panel calls do not.

## Option B: CloudFront + Origin Access Control (recommended)

Keeps the S3 bucket fully private (no public bucket policy, no website-hosting
endpoint needed) and serves it over HTTPS via CloudFront. This also avoids
AWS account-level "Block Public Access" entirely, since the bucket policy
below is scoped to one CloudFront distribution rather than `Principal: "*"`.

### 1. Set variables

```bash
export AWS_REGION=eu-west-1
export BUCKET_NAME=your-study-mate-site-bucket
export ACCOUNT_ID=your-aws-account-id
```

### 2. Create the bucket (private, default settings)

```bash
aws s3api create-bucket \
  --bucket "$BUCKET_NAME" \
  --region "$AWS_REGION" \
  --create-bucket-configuration LocationConstraint="$AWS_REGION"
```

### 3. Create an Origin Access Control (OAC)

```bash
aws cloudfront create-origin-access-control \
  --origin-access-control-config Name=studymate-oac,SigningProtocol=sigv4,SigningBehavior=always,OriginAccessControlOriginType=s3
```

Note the returned `Id` as `$OAC_ID`.

### 4. Create the CloudFront distribution

```bash
cat > /tmp/studymate-cf-config.json << JSON
{
  "CallerReference": "studymate-$(date +%s)",
  "Comment": "StudyMate explainers static site",
  "Enabled": true,
  "DefaultRootObject": "index.html",
  "PriceClass": "PriceClass_100",
  "Origins": {
    "Quantity": 1,
    "Items": [
      {
        "Id": "studymate-s3-origin",
        "DomainName": "${BUCKET_NAME}.s3.${AWS_REGION}.amazonaws.com",
        "OriginAccessControlId": "${OAC_ID}",
        "S3OriginConfig": { "OriginAccessIdentity": "" }
      }
    ]
  },
  "DefaultCacheBehavior": {
    "TargetOriginId": "studymate-s3-origin",
    "ViewerProtocolPolicy": "redirect-to-https",
    "AllowedMethods": {
      "Quantity": 2,
      "Items": ["GET", "HEAD"],
      "CachedMethods": { "Quantity": 2, "Items": ["GET", "HEAD"] }
    },
    "CachePolicyId": "658327ea-f89d-4fab-a63d-7e88639e58f6",
    "Compress": true
  }
}
JSON

aws cloudfront create-distribution --distribution-config file:///tmp/studymate-cf-config.json
```

Note the returned `Id` (as `$DISTRIBUTION_ID`), `ARN` (as `$DISTRIBUTION_ARN`),
and `DomainName` (your `*.cloudfront.net` URL). Deployment takes 5-15 minutes
— poll with:

```bash
aws cloudfront get-distribution --id "$DISTRIBUTION_ID" --query 'Distribution.Status' --output text
```

### 5. Bucket policy scoped to this distribution only

```bash
cat > /tmp/studymate-cf-bucket-policy.json << JSON
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowCloudFrontServicePrincipal",
      "Effect": "Allow",
      "Principal": { "Service": "cloudfront.amazonaws.com" },
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::${BUCKET_NAME}/*",
      "Condition": {
        "StringEquals": { "AWS:SourceArn": "${DISTRIBUTION_ARN}" }
      }
    }
  ]
}
JSON

aws s3api put-bucket-policy --bucket "$BUCKET_NAME" --policy file:///tmp/studymate-cf-bucket-policy.json
```

### 6. Upload generated explainers and open the site

```bash
aws s3 sync generated/explainers/ "s3://$BUCKET_NAME/" --delete
```

```text
https://<distribution-domain>.cloudfront.net
```

### Adding an API origin later

To make the AI panel work, add a second CloudFront origin for the API (for
example API Gateway + Lambda) with a behavior such as `/api/*` routed to that
origin, so the frontend keeps calling the same-origin `/api/study` path. This
avoids CORS entirely, since static and API are under one CloudFront domain.

## If static and API are on different domains

Then CORS is required on API responses.

Set:

- Access-Control-Allow-Origin: https://your-static-site-domain
- Access-Control-Allow-Methods: POST, OPTIONS
- Access-Control-Allow-Headers: Content-Type

Also handle preflight OPTIONS requests.

## Deploy/update workflow

After regenerating explainers:

```bash
uv run study-mate explain
aws s3 sync generated/explainers/ "s3://$BUCKET_NAME/" --delete
```

If CloudFront is in front, invalidate cache:

```bash
aws cloudfront create-invalidation \
  --distribution-id YOUR_DISTRIBUTION_ID \
  --paths "/*"
```

## Troubleshooting: 403 Access Denied on the S3 website endpoint

If `put-bucket-policy` in Option A succeeds but the site still 403s (including
on the error document itself), check for an **account-level** S3 Block Public
Access setting, which overrides any individual bucket's settings:

```bash
aws s3control get-public-access-block --account-id "$ACCOUNT_ID"
```

If `BlockPublicPolicy` / `RestrictPublicBuckets` are `true` there, no bucket
in the account can have a public (`Principal: "*"`) policy until that account
setting is changed — which affects every bucket in the account, not just this
one. Prefer Option B (CloudFront + OAC) instead: its bucket policy is scoped
to a specific distribution ARN, not `Principal: "*"`, so AWS doesn't treat it
as "public" and it isn't blocked by this account setting.

## Operational notes

1. Never commit real API keys to git. Use secret management for the API runtime (Secrets Manager or SSM Parameter Store).
2. S3 website endpoints are HTTP only. For HTTPS, use CloudFront.
3. If your organization blocks public S3 buckets, use private S3 + CloudFront Origin Access Control.
4. Keep manifest.json and index.html in sync by deploying the full generated/explainers directory each time.
