# -*- coding: utf-8 -*-

import os
import subprocess

from utils import download_file, upload_file

LAMBDA_TASK_ROOT = os.environ.get('LAMBDA_TASK_ROOT', os.path.dirname(os.path.abspath(__file__)))


def pdf_to_text(event, context):
    try: doc_path = download_file(event)
    except Exception as e: return dict(success=False, reason=u'Exception while downloading from <{}>: {}'.format(event['doc_uri'], e))

    cmdline = [os.path.join(LAMBDA_TASK_ROOT, 'pdftotext'), '-nopgbrk', doc_path]
    try:
        subprocess.check_call(cmdline, shell=False)
        text_path = os.path.splitext(doc_path)[0] + '.txt'
    except subprocess.CalledProcessError as e: return dict(success=False, reason=u'Exception while executing {}: {}'.format(cmdline, e))

    try: upload_file(event, text_path)
    except Exception as e: return dict(success=False, reason=u'Exception while uploading to <{}>: {}'.format(event['text_uri'], e))

    return dict(success=True, doc_uri=event['doc_uri'], text_uri=event['text_uri'], size=os.path.getsize(text_path))
#end def


def main():
    from argparse import ArgumentParser
    parser = ArgumentParser(description='Extract text from binary documents.')
    parser.parse_args()

    print pdf_to_text(dict(doc_uri='s3://docbot-test-lambda/text_pdf.pdf', text_uri='s3://docbot-test-lambda/text_pdf.txt'), None)
#end def


if __name__ == '__main__': main()
