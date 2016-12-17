# -*- coding: utf-8 -*-

import os
from tempfile import NamedTemporaryFile
from urlparse import urlparse

import boto3

s3_client = boto3.client('s3')


def download_file(event):
    o = urlparse(event['doc_uri'])

    if o.scheme == 's3':
        bucket, doc_key = o.netloc, o.path.lstrip('/')
    #end if

    doc_id, doc_ext = os.path.splitext(doc_key)

    with NamedTemporaryFile(prefix='intelllex_', suffix=doc_ext, delete=False) as f:
        doc_path = f.name
    #end with

    if o.scheme == 's3':
        s3_client.download_file(bucket, doc_key, doc_path)
    #end if

    return doc_path
#end def


def upload_file(event, text_path):
    o = urlparse(event['text_uri'])

    if o.scheme == 's3':
        bucket, doc_key = o.netloc, o.path.lstrip('/')
    #end if

    return s3_client.upload_file(text_path, bucket, doc_key, ExtraArgs=dict(ContentType='text/plain', ContentEncoding='utf-8'))
#end def
