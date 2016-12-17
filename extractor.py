from argparse import ArgumentParser
import os
import subprocess
from tempfile import NamedTemporaryFile

import boto3

LAMBDA_TASK_ROOT = os.environ.get('LAMBDA_TASK_ROOT', os.path.dirname(os.path.abspath(__file__)))
BIN_DIR = os.path.join(LAMBDA_TASK_ROOT, 'bin-linux_x64')
LIB_DIR = os.path.join(LAMBDA_TASK_ROOT, 'lib-linux_x64')

s3_client = boto3.client('s3')


def pdf_to_text(event, context):
    # download file from s3_pdf
    bucket = event['bucket']
    doc_key = event['key']

    doc_id, doc_ext = os.path.splitext(doc_key)

    with NamedTemporaryFile(prefix='intelllex_', suffix='.pdf', delete=False) as f:
        doc_path = f.name
    #end with

    try: s3_client.download_file(bucket, doc_key, doc_path)
    except Exception as e: return dict(success=False, reason=u'Exception while getting document from S3: {}'.format(e))

    cmdline = [os.path.join(BIN_DIR, 'pdftotext'), '-nopgbrk', doc_path]
    try: subprocess.check_call(cmdline, shell=False)
    except subprocess.CalledProcessError as e: return dict(success=False, reason=u'Exception while executing {}: {}'.format(cmdline, e))

    text_path = os.path.splitext(doc_path)[0] + '.txt'

    try: s3_client.upload_file(text_path, bucket, doc_id + '.txt', ExtraArgs=dict(ContentType='text/plain', ContentEncoding='utf-8'))
    except Exception as e: return dict(success=False, reason=u'Exception while uploading document to S3: {}'.format(e))

    return dict(success=True, bucket=bucket, text_key=doc_id + '.txt', doc_id=doc_id, size=os.path.getsize(text_path))
#end def


def main():
    parser = ArgumentParser(description='Extract text from binary documents.')
    parser.parse_args()

    print pdf_to_text(dict(bucket='airpr-sentiment-analysis', key='text.pdf'), {})
#end def


if __name__ == '__main__': main()
