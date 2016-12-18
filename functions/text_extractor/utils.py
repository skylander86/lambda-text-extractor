# -*- coding: utf-8 -*-

import os
from tempfile import NamedTemporaryFile
from urlparse import urlparse

import boto3

s3_client = boto3.client('s3')


def download_file(uri):
    o = urlparse(uri)

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


def get_file_content(uri):
    o = urlparse(uri)

    if o.scheme == 's3':
        bucket, doc_key = o.netloc, o.path.lstrip('/')
    #end if

    if o.scheme == 's3':
        response = s3_client.get_object(Bucket=bucket, Key=doc_key)
        body = response['Body'].read()
        if response.get('ContentEncoding'):
            body = body.decode(response['ContentEncoding'])

        return body
    #end if

    return None
#end def


def delete_objects(uris):
    s3_keys = []
    s3_bucket = None
    for uri in uris:
        o = urlparse(uri)
        if o.scheme == 's3':
            bucket, key = o.netloc, o.path.lstrip('/')
            s3_keys.append(key)
            if s3_bucket is None: s3_bucket = bucket
            else: assert s3_bucket == bucket
        #end if
    #end def

    def _chunks(l, n):  # Yield successive n-sized chunks from l.
        for i in xrange(0, len(l), n):
            yield l[i:i + n]
    #end def

    for chunk in _chunks(s3_keys, 1000):
        s3_client.delete_objects(Bucket=s3_bucket, Delete=dict(Objects=[dict(Key=k) for k in chunk]), Quiet=True)
#end def


def upload_file(uri, text_path):
    o = urlparse(uri)

    if o.scheme == 's3':
        bucket, doc_key = o.netloc, o.path.lstrip('/')
    #end if

    return s3_client.upload_file(text_path, bucket, doc_key, ExtraArgs=dict(ContentType='text/plain', ContentEncoding='utf-8'))
#end def
