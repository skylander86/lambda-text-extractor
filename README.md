# Extracting Text from Binary Document Formats using AWS Lambda

`lambda-text-extractor` is a Python 3.6 app that works with the AWS Lambda architecture to extract text from common binary document formats.

## Features

Some of its key features are:

- out of the box support for many common binary document formats (see section on [Supported Formats](#Supported-Formats)),
- scalable PDF parsing using OCR in parallel using AWS Lambda and [asyncio](https://docs.python.org/3/library/asyncio.html),
- creation of text searchable PDFs after OCR,
- serverless architecture makes deployment quick and easy,
- detailed instruction for preparing libraries and dependencies necessary for processing binary documents, and
- sensible unicode handling

### Supported Formats

`lambda-text-extractor` supports many common and legacy document formats:

- Portable Document Format (`.pdf`),
    * PDFs with a text layer using [Poppler utilities](https://poppler.freedesktop.org/),
    * PDFs with OCR using [Tesseract](https://github.com/tesseract-ocr/tesseract/) and [Ghostscript 9.21](https://ghostscript.com/download/gsdnld.html) for PDF manipulation,
- Microsoft Word 2, 6, 7, 97, 2000, 2002 and 2003 (`.doc`) using [Antiword](http://www.winfield.demon.nl/) with fallback to [Catdoc](http://www.wagner.pp.ru/~vitus/software/catdoc/),
- Microsoft Word 2007 OpenXML files (`.docx`) using [python-docx](https://github.com/python-openxml/python-docx),
- Microsoft PowerPoint 2007 OpenXML files (`.pptx`) using [python-pptx](https://github.com/scanny/python-pptx),
- Microsoft Excel 5.0, 97-2003, and 2007 OpenXML files (`.xls`, `.xlsx`) using [xlrd](http://xlrd.readthedocs.io/en/latest/),
- OpenDocument 1.2 (`.odm`, `.odp`, `.ods`, `.odt`, `.oth`, `.otm`, `.otp`, `.ots`, `.ott`) using [odfpy](https://github.com/eea/odfpy),
- Rich Text Format (`.rtf`) using [UnRTF v0.21.9](https://www.gnu.org/software/unrtf/),
- XML files and HTML web pages (`.html`, `.htm`, `.xml`) using [lxml](http://lxml.de/),
- CSV files (`.csv`) using [Python csv module](https://docs.python.org/3/library/csv.html),
- Images (`.tiff`, `.jpg`, `.jpeg`, `.png`) using [Tesseract](https://github.com/tesseract-ocr/tesseract/), and
- Plain text files (`.txt`)

## Setup

Due to the size of code and dependencies (and AWS Lambda's 50MB package limits), the extraction system is split into two Lambda functions: `simple` and `ocr`.
[`ocr`](functions/ocr) supports extracting text from images and "image" PDFs, while [`simple`](functions/simple) handles text extraction from the remaining formats.
The side benefit of splitting into two functions is that we can configure the memory requirements of the two functions independently.

We use [apex](http://apex.run/) for our development toolchain to deploy the AWS Lambda functions; the code for the two Lambda functions are found in the [functions](functions) directory.
To deploy to AWS (*Note* that the `-D` argument refers to dry run mode.)

    apex -D deploy

You need to ensure your IAM role has `lambda:InvokeAsync` permissions, and `s3:PutObject` permissions on the output bucket.
Generally, we would advice using a specific bucket with auto-delete lifecycle rules for the temporary storage.
You can set the IAM role and other configuration options in [project.json](project.json).

The speed of parsing depends on CPU and this is controlled by the amount of memory allocated to your Lambda functions.
For our needs, we find that 512MB for `simple` and 1024MB for `ocr` is a good balance between performance and cost.

## Usage

### Non OCR Text Extraction

The `simple` function expects an `event` with

- `document_uri`: A URI containing the document to extract text from, i.e., `s3://bucket/key.pdf`.
- `temp_uri_prefix` (optional): A URI prefix where temporary files can be stored. Defaults to `<document_uri>-temp` if not set.
- `text_uri` (optional): A URI where the extracted text will be stored, i.e., `s3://bucket/key.txt`. Defaults to `<document_uri>.txt` if not set.
- `disable_ocr` (optional): Whether to disable OCR feature. Defaults to `False`.

#### Example

    aws lambda invoke --function-name textractor_simple --payload '{"document_uri": "https://mozilla.github.io/pdf.js/web/compressed.tracemonkey-pldi-09.pdf", "temp_uri_prefix": "s3://bucket/", "text_uri": "s3://bucket/tracemonkey.txt"}' -

    aws s3 cp s3://bucket/tracemonkey.txt -

It automatically fallbacks to `ocr` function when it necesay

### OCR Text Extraction

The `ocr` expects the same `event` as `simple` with the following additional fields:

- `searchable_pdf_uri`: A URI where searchable version of the PDF file is stored. Defaults to `<document_uri>.searchable.pdf`
- `create_searchable_pdf`: Whether to create searchable PDFs. Defaults to `True`.
- `page`: Page number of perform PDF OCR extraction. Defaults to all pages.

Searchable PDF creation may take significantly longer than just text extraction.
As there are multiple steps in OCR PDF extraction, there are several additional variables (set through environment variables) to configure its behavior.

- `MERGE_SEARCHABLE_PDF_DURATION`: The maximum number of seconds to take for searchable PDF merging. Defaults to 90 seconds.
- `RETURN_RESULTS_DURATION`: The number of seconds to reserve at the end for compiling results and returning them. Defaults to 3 seconds.
- `TEXTRACT_OUTPUT_WAIT_BUFFER_TIME`: The number of seconds to reserve for the overhead in async wait of each page's OCR Lambda functions to return. Defaults to 5 seconds.

For more details about how PDF OCR extraction work here, see section on [PDF OCR Extraction](#pdf-ocr-extraction).

#### Example

    aws lambda invoke --function-name textractor_ocr --payload '{"document_uri": "https://mozilla.github.io/pdf.js/web/compressed.tracemonkey-pldi-09.pdf", "temp_uri_prefix": "s3://docbot-hippocrates-assets/", "text_uri": "s3://docbot-hippocrates-assets/tracemonkey.txt", "searchable_pdf_uri": "s3://docbot-hippocrates-assets/tracemonkey.searchable.pdf"}' -

    aws s3 cp s3://bucket/tracemonkey-5.txt -

## PDF OCR Extraction

Due to the slow nature of OCR on images and AWS Lambda's 300 seconds execution limit, we used a hack (i.e., another lambda invocation) to OCR the pages of a PDF in parallel, while using S3 as our temporary store.

When we determine that a PDF needs to be processed using OCR (i.e., `simple` text extraction yields < 512 bytes), we automatically invoke `ocr` and wait for the results asynchronously for each page of the PDF (we use [asyncio](https://docs.python.org/3/library/asyncio.html) and [aiobotocore](https://github.com/aio-libs/aiobotocore) to achieve this).
The `page` field in `event` determines which page we want to OCR for that function call.

Basically, the steps for OCR extraction are as follows:

1. Determine the number of pages in the PDF using `pdfinfo`. We find that this subprocess call is faster (and more robust) than using a Python PDF library like [PyPDF2](https://pypi.python.org/pypi/PyPDF2).
2. Invoke `ocr` on each page of the document by passing in the `page` field. We store the intermediate output (i.e., extracted text and searchable PDFs for each page) in the `temp_uri_prefix` folder. We wait for the Lambda function calls in step 2 to complete using `await`.
3. We download the intermediate outputs to the Lambda function's local filesystem.
4. We combine the intermediate text and searchable PDF, ignoring missing pages and files. The missing information will be stored in the metadata of the final `text_uri` and `searchable_pdf_uri` as `missing_text_pages` and `missing_searchable_pdf_pages` respectively.

For step 2 and 3, it is done concurrently and asynchronously and we set a timeout based on

    REMAINING_TIME - MERGE_SEARCHABLE_PDF_DURATION - RETURN_RESULTS_DURATION - TEXTRACT_OUTPUT_WAIT_BUFFER_TIME

where `REMAINING_TIME` is the amount of time remaining after step 1.

Based on our experience, merging searchable PDFs take quite a while (and depends on the number of pages you have).
On average, it can take about 60 seconds for merging 100 pages of searchable PDFs.
If this is an issue for you, you might want to modify the code to fix the path of the intermediate outputs and combine it yourself outside the Lambda infrastructure.
Currently, we use random UUIDs for the filenames of each intermediate output page.
The relevant part of the code is in the [`_invoke_textract_ocr_tasks` method](functions/ocr/main.py).

For OCR extractions on individual pages, we use Ghostscript to extract the page into an image with basic image processing and then use Tesseract to do text extraction.
If `create_searchable_pdf` is enabled, Tesseract is used to directly [create a searchable PDF](https://stackoverflow.com/questions/24848808/scanned-image-pdf-to-searchable-image-pdf).
After which, we use `pdftotext` for regular text extraction from the searchable PDF (instead of running Tesseract twice).

If anybody knows of a better pattern for processing PDFs, do feel free to submit a pull request!

## Building Binaries

For more information on how we prepped the Lambda execution environment to run all these external software and libraries, see [Building Binaries](BuildingBinaries.md).

