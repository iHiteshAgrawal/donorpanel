"""The landing page on S3 behind CloudFront.

The bucket stays private: CloudFront reaches it through an Origin Access Control, and
the bucket policy trusts only that one distribution.
"""
import json
import mimetypes
import pathlib
import time

import boto3
from botocore.exceptions import ClientError

from deploy.settings import ACCOUNT, REGION, SITE_BUCKET

s3 = boto3.client("s3", region_name=REGION)
cf = boto3.client("cloudfront")

DIST = pathlib.Path("web/dist")
OAC_NAME = "donorpanel-site"
COMMENT = "donorpanel landing page"


def ensure_bucket() -> None:
    try:
        s3.create_bucket(Bucket=SITE_BUCKET,
                         CreateBucketConfiguration={"LocationConstraint": REGION})
        print(f"  created bucket {SITE_BUCKET}")
    except ClientError as exc:
        if exc.response["Error"]["Code"] not in ("BucketAlreadyOwnedByYou",
                                                 "BucketAlreadyExists"):
            raise
        print(f"  bucket {SITE_BUCKET} exists")
    s3.put_public_access_block(
        Bucket=SITE_BUCKET,
        PublicAccessBlockConfiguration={"BlockPublicAcls": True,
                                        "IgnorePublicAcls": True,
                                        "BlockPublicPolicy": True,
                                        "RestrictPublicBuckets": True})


def ensure_oac() -> str:
    for item in cf.list_origin_access_controls().get("OriginAccessControlList", {}).get("Items", []):
        if item["Name"] == OAC_NAME:
            return item["Id"]
    made = cf.create_origin_access_control(OriginAccessControlConfig={
        "Name": OAC_NAME, "Description": COMMENT, "SigningProtocol": "sigv4",
        "SigningBehavior": "always", "OriginAccessControlOriginType": "s3"})
    print("  created origin access control")
    return made["OriginAccessControl"]["Id"]


def find_distribution() -> dict | None:
    items = cf.list_distributions().get("DistributionList", {}).get("Items", [])
    return next((d for d in items if d.get("Comment") == COMMENT), None)


def ensure_distribution(oac_id: str) -> dict:
    existing = find_distribution()
    if existing:
        print(f"  distribution {existing['Id']} exists")
        return existing
    origin = f"{SITE_BUCKET}.s3.{REGION}.amazonaws.com"
    made = cf.create_distribution(DistributionConfig={
        "CallerReference": f"donorpanel-{int(time.time())}",
        "Comment": COMMENT,
        "Enabled": True,
        "DefaultRootObject": "index.html",
        "Origins": {"Quantity": 1, "Items": [{
            "Id": "site", "DomainName": origin, "OriginAccessControlId": oac_id,
            "S3OriginConfig": {"OriginAccessIdentity": ""}}]},
        "DefaultCacheBehavior": {
            "TargetOriginId": "site",
            "ViewerProtocolPolicy": "redirect-to-https",
            "AllowedMethods": {"Quantity": 2, "Items": ["GET", "HEAD"]},
            "Compress": True,
            # CachingOptimized, an AWS managed policy.
            "CachePolicyId": "658327ea-f89d-4fab-a63d-7e88639e58f6"},
        # A single page app has no server side routes, so anything unknown is the page.
        "CustomErrorResponses": {"Quantity": 2, "Items": [
            {"ErrorCode": code, "ResponsePagePath": "/index.html",
             "ResponseCode": "200", "ErrorCachingMinTTL": 10} for code in (403, 404)]},
    })
    print(f"  created distribution {made['Distribution']['Id']}")
    return made["Distribution"]


def allow_only_cloudfront(distribution_id: str) -> None:
    s3.put_bucket_policy(Bucket=SITE_BUCKET, Policy=json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Sid": "OnlyThroughCloudFront", "Effect": "Allow",
            "Principal": {"Service": "cloudfront.amazonaws.com"},
            "Action": "s3:GetObject",
            "Resource": f"arn:aws:s3:::{SITE_BUCKET}/*",
            "Condition": {"StringEquals": {
                "AWS:SourceArn":
                    f"arn:aws:cloudfront::{ACCOUNT}:distribution/{distribution_id}"}},
        }]}))
    print("  bucket readable only through the distribution")


def upload() -> int:
    if not DIST.is_dir():
        raise SystemExit("web/dist is missing, run npm run build first")
    count = 0
    for path in DIST.rglob("*"):
        if path.is_dir():
            continue
        key = str(path.relative_to(DIST))
        kind = mimetypes.guess_type(key)[0] or "application/octet-stream"
        # index.html must never be cached or a deploy is invisible until the TTL expires.
        cache = "no-cache" if key == "index.html" else "public, max-age=31536000, immutable"
        s3.upload_file(str(path), SITE_BUCKET, key,
                       ExtraArgs={"ContentType": kind, "CacheControl": cache})
        count += 1
    return count


def main() -> None:
    ensure_bucket()
    oac = ensure_oac()
    distribution = ensure_distribution(oac)
    allow_only_cloudfront(distribution["Id"])
    print(f"  uploaded {upload()} files")
    cf.create_invalidation(DistributionId=distribution["Id"], InvalidationBatch={
        "Paths": {"Quantity": 1, "Items": ["/*"]},
        "CallerReference": f"deploy-{int(time.time())}"})
    domain = distribution.get("DomainName") or cf.get_distribution(
        Id=distribution["Id"])["Distribution"]["DomainName"]
    print(f"\n  https://{domain}")
    print("  CloudFront takes a few minutes to finish deploying the first time.")


if __name__ == "__main__":
    main()
