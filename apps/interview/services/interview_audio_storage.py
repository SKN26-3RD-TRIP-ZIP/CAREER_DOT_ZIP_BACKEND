import uuid

import boto3
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def _bucket_name():
    bucket = getattr(settings, 'INTERVIEW_AUDIO_S3_BUCKET', '')
    if not bucket:
        raise ImproperlyConfigured('INTERVIEW_AUDIO_S3_BUCKET is not configured.')
    return bucket


def _client():
    return boto3.client('s3', region_name=settings.AWS_S3_REGION_NAME)


def upload_interview_audio(uploaded_file, *, user_id, session_id):
    key = f'interview-audio/{user_id}/{session_id}/{uuid.uuid4()}.webm'
    uploaded_file.seek(0)
    _client().upload_fileobj(
        uploaded_file, _bucket_name(), key, ExtraArgs={'ContentType': 'audio/webm'}
    )
    return key


def create_interview_audio_presigned_url(audio_key):
    return _client().generate_presigned_url(
        'get_object',
        Params={'Bucket': _bucket_name(), 'Key': audio_key},
        ExpiresIn=settings.INTERVIEW_AUDIO_PRESIGNED_TTL_SECONDS,
    )
