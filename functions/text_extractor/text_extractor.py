# -*- coding: utf-8 -*-

import codecs
import logging
import os
import subprocess
from tempfile import NamedTemporaryFile

from utils import download_file, upload_file

LAMBDA_TASK_ROOT = os.environ.get('LAMBDA_TASK_ROOT', os.path.dirname(os.path.abspath(__file__)))
BIN_DIR = os.path.join(LAMBDA_TASK_ROOT, 'bin')
LIB_DIR = os.path.join(LAMBDA_TASK_ROOT, 'lib')

logging.basicConfig(format=u'%(asctime)-15s [%(name)s] %(levelname)s: %(message)s', level=logging.INFO)
logger = logging.getLogger()


def extract(event, context):
    try: doc_path = download_file(event)
    except Exception as e: return dict(success=False, reason=u'Exception while downloading from <{}>: {}'.format(event['doc_uri'], e))

    _, ext = os.path.splitext(doc_path)  # get format from extension
    parse_func = PARSE_FUNCS.get(ext.lower())

    # todo text_encoding in event

    if parse_func is None:
        return dict(success=False, reason=u'Unknown file type <{}>'.format(event['doc_uri']))

    o = parse_func(doc_path)

    if not o['success']: return o

    text = o['text']

    with NamedTemporaryFile(prefix='text-extractor.', suffix='.txt', delete=False) as f:
        text_path = f.name
        if isinstance(text, unicode):
            f.write(text.encode('utf-8'))
        else:
            logger.warning(u'Text extracted from <{}> is not in unicode!'.format(event['doc_uri']))
            f.write(text)
        #end if
    #end with

    try: upload_file(event, text_path)
    except Exception as e: return dict(success=False, reason=u'Exception while uploading to <{}>: {}'.format(event['text_uri'], e))

    return dict(success=True, doc_uri=event['doc_uri'], text_uri=event['text_uri'], size=len(text), method=parse_func.__name__)
#end def


def pdf_to_text(doc_path):
    cmdline = [os.path.join(BIN_DIR, 'pdftotext'), '-nopgbrk', doc_path]
    try:
        subprocess.check_call(cmdline, shell=False, stderr=subprocess.STDOUT)
        text_path = os.path.splitext(doc_path)[0] + '.txt'
    except subprocess.CalledProcessError as e: return dict(success=False, reason=u'Exception while executing {}: {}'.format(cmdline, e, e.output))

    with codecs.open(text_path, 'r', 'utf-8', errors='ignore') as f:
        text = f.read()
    text = text.strip()

    return dict(success=True, text=text)
#end def


def doc_to_text(doc_path):
    cmdline = [os.path.join(BIN_DIR, 'antiword'), '-t', '-w', '0', '-m', 'UTF-8', doc_path]
    try:
        text = subprocess.check_output(cmdline, shell=False, stderr=subprocess.STDOUT, env=dict(ANTIWORDHOME=os.path.join(LIB_DIR, 'antiword')))
        text = text.decode('utf-8', errors='ignore')
    except subprocess.CalledProcessError as e: return dict(success=False, reason=u'Exception while executing {}: {} (output={})'.format(cmdline, e, e.output))

    return dict(success=True, text=text.strip())
#end def


def rtf_to_text(doc_path):
    cmdline = [os.path.join(BIN_DIR, 'unrtf'), '-P', os.path.join(LIB_DIR, 'unrtf'), '--text', doc_path]
    try:
        text = subprocess.check_output(cmdline, shell=False, stderr=subprocess.STDOUT)
        text = text.decode('utf-8', errors='ignore')

        new_lines = []
        in_header = True
        for line in text.split(u'\n'):
            if in_header and line.startswith('###'): continue
            else:
                new_lines.append(line)
                in_header = False
            #end if
        #end for
        text = u'\n'.join(new_lines)
    except subprocess.CalledProcessError as e: return dict(success=False, reason=u'Exception while executing {}: {} (output={})'.format(cmdline, e, e.output))

    return dict(success=True, text=text.strip())
#end def


PARSE_FUNCS = {
    '.pdf': pdf_to_text,
    '.rtf': rtf_to_text,
    '.doc': doc_to_text,
}
