# -*- coding: utf-8 -*-

import os
import subprocess
from tempfile import NamedTemporaryFile

from utils import download_file, upload_file

LAMBDA_TASK_ROOT = os.environ.get('LAMBDA_TASK_ROOT', os.path.dirname(os.path.abspath(__file__)))


def extract(event, context):
    try: doc_path = download_file(event)
    except Exception as e: return dict(success=False, reason=u'Exception while downloading from <{}>: {}'.format(event['doc_uri'], e))

    cmdline = [os.path.join(LAMBDA_TASK_ROOT, 'unrtf'), '-P', os.path.join(LAMBDA_TASK_ROOT, 'lib'), '--text', doc_path]
    try:
        text = subprocess.check_output(cmdline, shell=False, stderr=subprocess.STDOUT)

        new_lines = []
        in_header = True
        for line in text.split('\n'):
            if in_header and line.startswith('###'): continue
            else:
                new_lines.append(line)
                in_header = False
            #end if
        #end for
        text = '\n'.join(new_lines)

        with NamedTemporaryFile(prefix='intelllex_', suffix='.txt', delete=False) as f:
            text_path = f.name
            f.write(text)
        #end with
    except subprocess.CalledProcessError as e: return dict(success=False, reason=u'Exception while executing {}: {} (output={})'.format(cmdline, e, e.output))

    try: upload_file(event, text_path)
    except Exception as e: return dict(success=False, reason=u'Exception while uploading to <{}>: {}'.format(event['text_uri'], e))

    return dict(success=True, doc_uri=event['doc_uri'], text_uri=event['text_uri'], size=os.path.getsize(text_path))
#end def


def main():
    from argparse import ArgumentParser
    parser = ArgumentParser(description='Extract text from binary documents.')
    parser.parse_args()

    print extract(dict(doc_uri='s3://docbot-test-lambda/rtf.rtf', text_uri='s3://docbot-test-lambda/rtf.txt'), None)
#end def


if __name__ == '__main__': main()
