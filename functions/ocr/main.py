import asyncio
from contextlib import closing
import concurrent.futures
import io
import json
import logging
import os
import re
import subprocess
from tempfile import NamedTemporaryFile
import time
from uuid import uuid4
from urllib.parse import urlparse

import aiobotocore

import boto3

from uriutils import uri_read, uri_exists, uri_dump

from pageutils import invoke_textract_ocr
from utils import get_subprocess_output

LAMBDA_TASK_ROOT = os.environ.get('LAMBDA_TASK_ROOT', os.path.dirname(os.path.abspath(__file__)))
LAMBDA_FUNCTION_NAME = os.environ['LAMBDA_FUNCTION_NAME']
BIN_DIR = os.path.join(LAMBDA_TASK_ROOT, 'bin')
LIB_DIR = os.path.join(LAMBDA_TASK_ROOT, 'lib')

MERGE_SEARCHABLE_PDF_DURATION = float(os.environ.get('MERGE_SEARCHABLE_PDF_DURATION', 90))
RETURN_RESULTS_DURATION = float(os.environ.get('RETURN_RESULTS_DURATION', 3.0))
TEXTRACT_OUTPUT_WAIT_BUFFER_TIME = float(os.environ.get('TEXTRACT_OUTPUT_WAIT_BUFFER_TIME', 5.0))

lambda_client = boto3.client('lambda')

logging.basicConfig(format='%(asctime)-15s [%(name)s-%(process)d] %(levelname)s: %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)


def handle(event, context):
    global logger

    document_uri = event['document_uri']
    temp_uri_prefix = event.get('temp_uri_prefix', event['document_uri'] + '-temp')
    text_uri = event.get('text_uri', document_uri + '.txt')
    searchable_pdf_uri = event.get('searchable_pdf_uri', document_uri + '.searchable.pdf')
    create_searchable_pdf = event.get('create_searchable_pdf', True)
    page = event.get('page')

    event['temp_uri_prefix'] = temp_uri_prefix

    # AWS Lambda auto-retries errors for 3x. This should make it disable retrying...kinda. See https://stackoverflow.com/questions/32064038/aws-lambda-function-triggering-multiple-times-for-a-single-event
    aws_context_retry_uri = os.path.join(temp_uri_prefix, 'aws_lambda_request_ids', context.aws_request_id)
    if uri_exists(aws_context_retry_uri):
        return
    uri_dump(aws_context_retry_uri, '', mode='w')

    start_time = time.time()

    logger.info('{} invoked with event {}.'.format(os.environ['AWS_LAMBDA_FUNCTION_NAME'], json.dumps(event)))

    o = urlparse(document_uri)
    _, ext = os.path.splitext(o.path)  # get format from extension
    ext = ext.lower()

    extract_func = PARSE_FUNCS.get(ext)
    if extract_func is None:
        raise ValueError('<{}> has unsupported extension "{}".'.format(document_uri, ext))

    with NamedTemporaryFile(mode='wb', suffix=ext, delete=False) as f:
        document_path = f.name
        f.write(uri_read(document_uri, mode='rb'))
        logger.debug('Downloaded <{}> to <{}>.'.format(document_uri, document_path))
    #end with

    textractor_results = {}
    searchable_pdf_path = None

    try:
        textractor_results = extract_func(document_path, event, context, create_searchable_pdf=create_searchable_pdf)

        meta = textractor_results.pop('meta', {})
        meta['method'] = textractor_results['method']

        text = textractor_results.pop('text', '')
        textractor_results['size'] = len(text)

        uri_dump(text_uri, text, mode='w', textio_args={'errors': 'ignore'}, storage_args=dict(ContentType='text/plain', Metadata=meta))
        if len(text) == 0: logger.warning('<{}> does not contain any content.'.format(document_uri))

        searchable_pdf_path = textractor_results.pop('searchable_pdf_path', None)
        if searchable_pdf_path:
            assert os.path.isfile(searchable_pdf_path)

            with open(searchable_pdf_path, 'rb') as f:
                contents = f.read()
                uri_dump(searchable_pdf_uri, contents, mode='wb', storage_args=dict(ContentType='application/pdf', Metadata=meta))
                logger.debug('Searchable PDF version of <{}> saved to <{}>.'.format(document_uri, searchable_pdf_uri))
            #end with

            textractor_results['searchable_pdf_uri'] = searchable_pdf_uri
        #end if

        textractor_results['success'] = True
        textractor_results.update(meta)

        if page: logger.debug('Extracted page {} of <{}> to <{}> (took {:.3f} seconds).'.format(page, document_uri, text_uri, time.time() - start_time))
        else: logger.debug('Extracted pages of <{}> to <{}> (took {:.3f} seconds).'.format(document_uri, text_uri, time.time() - start_time))

    except Exception as e:
        logger.exception('Extraction exception for <{}>'.format(document_uri))
        textractor_results = dict(success=False, reason=str(e))
        uri_dump(text_uri, '', mode='w', textio_args={'errors': 'ignore'}, storage_args=dict(ContentType='text/plain', Metadata=dict(Exception=str(e))))

    finally:
        os.remove(document_path)
        if searchable_pdf_path: os.remove(searchable_pdf_path)
    #end try

    payload = event.copy()
    payload['text_uri'] = text_uri
    if create_searchable_pdf:
        payload['searchable_pdf_uri'] = textractor_results.get('searchable_pdf_uri')

    for cb in event.get('callbacks', []):
        if cb['step'] == 'textractor':
            try:
                uri_dump(cb['uri'], json.dumps(payload), mode='w')
                logger.info('Called callback {} with payload {}.'.format(json.dumps(cb), json.dumps(payload)))
            except Exception as e: logger.exception('Callback exception for {} with payload {}.'.format(json.dumps(cb), json.dumps(payload)))
        #end if
    #end for

    payload.setdefault('results', {})
    payload['results']['textractor'] = textractor_results
    logger.debug('Textraction complete.')

    return payload
#end def


def _pdf_to_text(document_path):
    text_path = document_path + '.txt'
    _get_subprocess_output([os.path.join(BIN_DIR, 'pdftotext'), '-layout', '-nopgbrk', '-eol', 'unix', document_path, text_path], shell=False, env=dict(LD_LIBRARY_PATH=os.path.join(LIB_DIR, 'pdftotext')))

    with io.open(text_path, mode='r', encoding='utf-8', errors='ignore') as f:
        text = f.read().strip()
    os.remove(text_path)

    return text
#end def


def _get_subprocess_output(*args, **kwargs):
    global logger

    return get_subprocess_output(*args, logger=logger, **kwargs)
#end def


def pdf_to_text_with_ocr(document_path, event, context, create_searchable_pdf=True):
    global logger

    document_uri = event['document_uri']
    page = event.get('page')
    temp_uri_prefix = event['temp_uri_prefix']

    if page is not None:
        return pdf_to_text_with_ocr_single_page(document_path, event, context, create_searchable_pdf=create_searchable_pdf)

    # This is more reliable than using PyPDF2
    pdfinfo_output = _get_subprocess_output([os.path.join(BIN_DIR, 'pdfinfo'), document_path], shell=False, env=dict(LD_LIBRARY_PATH=os.path.join(LIB_DIR, 'pdftotext')))
    pdfinfo_output = pdfinfo_output.decode('ascii', errors='ignore')
    m = re.search(r'^Pages\:(.+)$', pdfinfo_output, flags=re.M | re.U)
    if not m: raise Exception('Unable to get page count from pdfinfo:\n{}'.format(pdfinfo_output))
    num_pages = int(m.group(1))

    with closing(asyncio.new_event_loop()) as event_loop:
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)  # Fix runtime error with "Event loop is closed" (see https://stackoverflow.com/questions/32598231/asyncio-runtimeerror-event-loop-is-closed/32615276#32615276)
        event_loop.set_default_executor(executor)

        session = aiobotocore.get_session(loop=event_loop)

        async def _invoke_textract_ocr_tasks(_completed_text_contents, _completed_searchable_pdf_fnames, timeout):
            tasks = []
            cur_uuid = str(uuid4())
            for page in range(1, num_pages + 1):
                page_uuid = '{}_{:04d}'.format(cur_uuid, page)  # base name for each page's intermediate output
                page_text_uri = os.path.join(temp_uri_prefix, '{}.txt'.format(page_uuid))

                payload = dict(document_uri=document_uri, text_uri=page_text_uri, temp_uri_prefix=temp_uri_prefix, page=page)

                if create_searchable_pdf:
                    page_searchable_pdf_uri = os.path.join(temp_uri_prefix, '{}.pdf'.format(page_uuid))
                    payload['searchable_pdf_uri'] = page_searchable_pdf_uri
                #end if

                tasks.append(invoke_textract_ocr(LAMBDA_FUNCTION_NAME, payload, session, logger))
            #end for

            completed, pending = await asyncio.wait(tasks, timeout=timeout, loop=event_loop)  # this is where the magic happens

            for task in pending:
                task.cancel()

            for task in completed:
                try: (page, page_text, page_searchable_pdf_fname) = task.result()
                except TypeError: continue

                _completed_text_contents[page] = page_text
                _completed_searchable_pdf_fnames[page] = page_searchable_pdf_fname
            #end for
        #end def

        textract_output_wait_timeout = (context.get_remaining_time_in_millis() / 1000.0) - MERGE_SEARCHABLE_PDF_DURATION - RETURN_RESULTS_DURATION - TEXTRACT_OUTPUT_WAIT_BUFFER_TIME  # asyncio.wait seems to overshoot around 7 seconds everytime
        completed_text_contents, completed_searchable_pdf_fnames = {}, {}

        if textract_output_wait_timeout <= 0:
            logger.warning('Wait timeout for OCR output is < 0!')
        else:
            event_loop.run_until_complete(_invoke_textract_ocr_tasks(completed_text_contents, completed_searchable_pdf_fnames, textract_output_wait_timeout))
        #end if

        executor.shutdown(wait=False)
    #end with

    missing_text_pages, empty_content_pages, page_contents = [], [], []
    for page in range(1, num_pages + 1):
        content = completed_text_contents.get(page)
        if content is None: missing_text_pages.append(page)
        elif content: page_contents.append(content)
        else: empty_content_pages.append(page)
    #end for
    text = '\n\n'.join(page_contents).strip()

    searchable_pdf_path = None
    missing_searchable_pdf_pages, pdf_pages_filenames = [], []

    if create_searchable_pdf:
        try:
            # Extract pages from the original file if we are unable to textract / get searchable versions of the page
            for page in range(1, num_pages + 1):
                searchable_pdf_fname = completed_searchable_pdf_fnames.get(page)
                if searchable_pdf_fname is None:
                    missing_searchable_pdf_pages.append(page)

                    with NamedTemporaryFile(suffix='.pdf', delete=False) as f:
                        original_pdf_page_fname = f.name
                    _get_subprocess_output([os.path.join(BIN_DIR, 'pdfseparate'), '-f', str(page), '-l', str(page), document_path, original_pdf_page_fname], shell=False, env=dict(LD_LIBRARY_PATH=os.path.join(LIB_DIR, 'pdftotext')))
                    pdf_pages_filenames.append(original_pdf_page_fname)

                else:
                    pdf_pages_filenames.append(searchable_pdf_fname)
            #end for
            assert len(pdf_pages_filenames) == num_pages

            # Merge the individual pages of searchable PDFs together
            merge_searchable_pdf_timeout = (context.get_remaining_time_in_millis() / 1000.0) - RETURN_RESULTS_DURATION
            with NamedTemporaryFile(suffix='.pdf', delete=False) as f:
                searchable_pdf_path = f.name
            _get_subprocess_output([os.path.join(BIN_DIR, 'gs'), '-sDEVICE=pdfwrite', '-dBATCH', '-dNOPAUSE', '-q', '-dPDFSETTINGS=/ebook', '-sOutputFile={}'.format(searchable_pdf_path)] + pdf_pages_filenames, shell=False, timeout=merge_searchable_pdf_timeout)  # merge and compress pdf

        except subprocess.TimeoutExpired:
            searchable_pdf_path = None
            logger.warning('Timeout while merging searchable PDF for <{}>.'.format(document_uri))

        except Exception as e:
            logger.exception('Exception while merging searchable PDF for <{}>.'.format(document_uri))

        finally:
            for fname in pdf_pages_filenames:
                try: os.remove(fname)
                except Exception as e: logger.exception('searchable_pdf_remove_exception', filename=fname, document_uri=document_uri)
            #end for
        #end try
    #end if

    meta = dict(num_pages=str(num_pages))

    if missing_text_pages:
        logger.info('Missing pages {} in <{}>.'.format(missing_text_pages, document_uri))
        meta['missing_text_pages'] = ','.join(str(p) for p in missing_text_pages)
    #end if

    if empty_content_pages:
        logger.info('Empty content pages {} in <{}>.'.format(empty_content_pages, document_uri))
        meta['empty_content_pages'] = ','.join(str(p) for p in empty_content_pages)
    #end if

    if missing_searchable_pdf_pages:
        logger.info('Missing searchable PDF pages {} in <{}>.'.format(missing_searchable_pdf_pages, document_uri))
        meta['missing_searchable_pdf_pages'] = ','.join(str(p) for p in missing_searchable_pdf_pages)
    #end if

    return dict(success=True, text=text, searchable_pdf_path=searchable_pdf_path, method='pdf_to_text_with_ocr', meta=meta)
#end def


def pdf_to_text_with_ocr_single_page(document_path, event, context, create_searchable_pdf=True):
    page = event['page']

    with NamedTemporaryFile(suffix='.png', delete=False) as f:
        image_page_path = f.name

    try:
        cmdline = [os.path.join(BIN_DIR, 'gs'), '-sDEVICE=png16m', '-dFirstPage={}'.format(page), '-dLastPage={}'.format(page), '-dINTERPOLATE', '-r300', '-o', image_page_path, '-dNOPAUSE', '-dSAFER', '-c', '67108864', 'setvmthreshold', '-dGraphicsAlphaBits=4', '-dTextAlphaBits=4', '-f', document_path]  # extract the page as an image
        output = _get_subprocess_output(cmdline, shell=False)
        output = output.decode('ascii', errors='ignore')

        if os.path.getsize(image_page_path) == 0:
            raise Exception('Ghostscript image extraction failed with output:\n{}'.format(output))

        results = image_to_text(image_page_path, event, context, create_searchable_pdf=create_searchable_pdf)

    finally:
        os.remove(image_page_path)

    results['page'] = page

    return results
#end def


def image_to_text(document_path, event, context, create_searchable_pdf=True):
    _, ext = os.path.splitext(document_path)
    ext = ext.lower()

    cmdline = [os.path.join(BIN_DIR, 'tesseract'), document_path, document_path, '-l', 'eng', '-psm', '1', '--tessdata-dir', os.path.join(LIB_DIR, 'tesseract')]
    if create_searchable_pdf:
        cmdline += ['pdf']

    _get_subprocess_output(cmdline, shell=False, env=dict(LD_LIBRARY_PATH=os.path.join(LIB_DIR, 'tesseract')))

    if create_searchable_pdf:
        searchable_pdf_path = document_path + '.pdf'
        text = _pdf_to_text(searchable_pdf_path)
    else:
        searchable_pdf_path = None
        with io.open(document_path + '.txt', mode='r', encoding='utf-8', errors='ignore') as f:
            text = f.read().strip()
    #end def

    return dict(success=True, text=text, method='image_to_text', searchable_pdf_path=searchable_pdf_path)
#end def


PARSE_FUNCS = {
    '.pdf': pdf_to_text_with_ocr,
    '.png': image_to_text,
    '.tiff': image_to_text,
    '.tif': image_to_text,
    '.jpg': image_to_text,
    '.jpeg': image_to_text,
}
