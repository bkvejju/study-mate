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

## Option B: production-style hosting (recommended)

Use CloudFront in front of S3 and a dedicated API origin.

1. Put static files in S3 (private bucket recommended)
2. Create CloudFront distribution for static site
3. Deploy API (for example API Gateway + Lambda)
4. Add a second CloudFront origin for the API
5. Add a behavior such as /api/* routed to API origin
6. Keep frontend calling /api/study (same origin via CloudFront)
7. Enable HTTPS and custom domain

This avoids CORS complexity when both static and API are under one domain.

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

## Operational notes

1. Never commit real API keys to git. Use secret management for the API runtime (Secrets Manager or SSM Parameter Store).
2. S3 website endpoints are HTTP only. For HTTPS, use CloudFront.
3. If your organization blocks public S3 buckets, use private S3 + CloudFront Origin Access Control.
4. Keep manifest.json and index.html in sync by deploying the full generated/explainers directory each time.
