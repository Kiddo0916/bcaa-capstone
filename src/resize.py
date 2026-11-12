import io
import logging
import os
from urllib.parse import unquote_plus

import boto3
from PIL import Image, ImageOps, UnidentifiedImageError

S3 = boto3.client("s3")
LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)
MAX_BYTES = 20 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 25_000_000
CONTENT_TYPES = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}


def resize_image(key):
    source = os.environ["ORIGINAL_BUCKET"]
    target = os.environ["RESIZED_BUCKET"]
    obj = S3.get_object(Bucket=source, Key=key)
    with obj["Body"] as body:
        if obj["ContentLength"] > MAX_BYTES:
            return {"success": False, "reason": "Image exceeds 20 MiB"}
        image_data = body.read()

    try:
        with Image.open(io.BytesIO(image_data), formats=list(CONTENT_TYPES)) as original:
            if original.width * original.height > Image.MAX_IMAGE_PIXELS:
                return {"success": False, "reason": "Image exceeds 25 megapixels"}
            image = ImageOps.exif_transpose(original)
            image.thumbnail((256, 256))
            output = io.BytesIO()
            image.save(output, format=original.format)
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError):
        return {"success": False, "reason": "Invalid or unsupported image"}

    S3.put_object(Bucket=target, Key=key, Body=output.getvalue(),
                  ContentType=CONTENT_TYPES[original.format])
    LOGGER.info("Created thumbnail %r (%d x %d)", key, image.width, image.height)
    return {"success": True, "bucket": target, "key": key,
            "width": image.width, "height": image.height}


def handler(event, context):
    if not isinstance(event, dict):
        return {"success": False, "reason": "Provide a JSON object with an S3 key"}

    if "Records" in event:
        results = []
        for record in event["Records"]:
            key = unquote_plus(record["s3"]["object"]["key"])
            result = resize_image(key)
            if not result["success"]:
                LOGGER.warning("Skipped %r: %s", key, result["reason"])
            results.append(result)
        return {"results": results}

    key = event.get("key")
    if not isinstance(key, str) or not key or len(key.encode("utf-8")) > 1024:
        return {"success": False, "reason": "Provide an S3 object key"}
    return resize_image(key)
