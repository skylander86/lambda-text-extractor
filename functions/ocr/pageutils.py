import concurrent.futures
import json
from tempfile import NamedTemporaryFile
import time
from urllib.parse import urlparse


async def invoke_textract_ocr(textractor_func, payload, session, logger):
    page = payload.get('page')
    uuid = payload['uuid']
    document_uri = payload['document_uri']

    try:
        lambda_response = None

        async with session.create_client('lambda') as client:
            lambda_textract_ocr_time = -time.time()

            lambda_response = await client.invoke(FunctionName=textractor_func, InvocationType='RequestResponse', LogType='None', Payload=json.dumps(payload))
            assert lambda_response['StatusCode'] == 200

            lambda_textract_ocr_time += time.time()

            async with lambda_response['Payload'] as stream:
                lambda_response_payload = await stream.read()
            lambda_response_payload = json.loads(lambda_response_payload.decode('ascii'))
            lambda_response['Payload'] = lambda_response_payload
        #end with

        page = lambda_response_payload['page']

        async with session.create_client('s3') as client:
            page_text_uri = lambda_response_payload.get('text_uri')
            page_text, page_text_download_time, page_text_length = None, None, None
            if page_text_uri:
                uri = urlparse(page_text_uri)
                page_text_bucket = uri.netloc
                page_text_key = uri.path.lstrip('/')

                page_text_download_time = -time.time()
                page_text_response = await client.get_object(Bucket=page_text_bucket, Key=page_text_key)
                metadata = page_text_response['Metadata']
                if 'Exception' in metadata:
                    logger.info('invoke_textract_ocr_page_text_exception', uuid=uuid, document_uri=document_uri, page=page, page_text_uri=page_text_uri, exception=metadata['Exception'])

                else:
                    async with page_text_response['Body'] as stream:
                        page_text = await stream.read()
                    page_text = page_text.decode('utf-8', errors='ignore').strip()
                    page_text_length = len(page_text)
                    page_text_download_time += time.time()
                #end if

            else:
                logger.warning('invoke_textract_ocr_page_text_bad_response', uuid=uuid, document_uri=document_uri, page=page, lambda_response=lambda_response)
            #end if

            page_searchable_pdf_uri = lambda_response_payload.get('searchable_pdf_uri')
            page_searchable_pdf_fname, page_searchable_pdf_download_time, page_searchable_pdf_length = None, None, None
            if page_searchable_pdf_uri:
                uri = urlparse(page_searchable_pdf_uri)
                page_searchable_pdf_bucket = uri.netloc
                page_searchable_pdf_key = uri.path.lstrip('/')

                page_searchable_pdf_download_time = -time.time()
                with NamedTemporaryFile(suffix='.pdf', prefix='{:04d}_'.format(page), delete=False, mode='wb') as f:
                    get_object_response = await client.get_object(Bucket=page_searchable_pdf_bucket, Key=page_searchable_pdf_key)
                    async with get_object_response['Body'] as stream:
                        content = await stream.read()
                    page_searchable_pdf_length = len(content)
                    f.write(content)
                    page_searchable_pdf_fname = f.name
                #end with
                page_searchable_pdf_download_time += time.time()

            else:
                logger.warning('invoke_textract_ocr_page_searchable_pdf_bad_response', uuid=uuid, document_uri=document_uri, page=page, lambda_response=lambda_response)
            #end if
        #end with

        logger.debug(
            'invoke_textract_ocr_page',
            uuid=uuid, document_uri=document_uri, page=page,
            lambda_response=lambda_response, payload=payload, lambda_textract_ocr_time=lambda_textract_ocr_time,
            page_text_uri=page_text_uri, page_text_download_time=page_text_download_time, page_text_length=page_text_length,
            page_searchable_pdf_uri=page_searchable_pdf_uri, page_searchable_pdf_download_time=page_searchable_pdf_download_time, page_searchable_pdf_length=page_searchable_pdf_length
        )

        return (page, page_text, page_searchable_pdf_fname)

    except concurrent.futures.CancelledError:
        logger.info('invoke_textract_ocr_page_cancelled', uuid=uuid, document_uri=document_uri, page=page, payload=payload)

    except Exception as e:
        logger.exception('invoke_textract_ocr_page_exception', uuid=uuid, document_uri=document_uri, page=page, lambda_response=lambda_response)

    return None
#end def
