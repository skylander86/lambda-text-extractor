# Extracting Text from Binary Document Formats

`text-extractor` is a Python app that works with the AWS Lambda architecture to extract text from common binary document formats.

Due to the size of code and dependencies (and AWS deployment limits), it is split into two functions.

[`pdf_extractor`](functions/pdf_extractor) supports extracting text from

- "Text" PDF files (using [pdftotext](http://www.foolabs.com/xpdf/download.html)),
- Images (TIFF, JPEG, PNG) and "image" PDF (using [Ghostscript](https://ghostscript.com/download/gsdnld.html) 9.20 for PDF manipulation, [ImageMagick](https://www.imagemagick.org/) 7.0.3-10 for image handling, and [Tesseract](https://github.com/tesseract-ocr/tesseract/) 3.05.00dev for OCR)

while [`office_extractor`](functions/office_extractor/) handles text extraction from

- Microsoft Word 2, 6, 7, 97, 2000, 2002 and 2003 (using [Antiword](http://www.winfield.demon.nl/)),
- Microsoft Word 2007 OpenXML files (using [python-docx](https://github.com/python-openxml/python-docx)),
- Microsoft PowerPoint 2007 OpenXML files (using [python-pptx](https://github.com/scanny/python-pptx)),
- Microsoft Excel 5.0, 97-2003, and 2007 OpenXML files (using [xlrd](http://xlrd.readthedocs.io/en/latest/)),
- HTML web pages (using [lxml](http://lxml.de/)),
- Rich Text Format (using [UnRTF](https://www.gnu.org/software/unrtf/) v0.21.9),
- CSV and Text files (duh)

The extracted text will always be encoded in UTF-8.

## Deploying on AWS Lambda

We use [apex](http://apex.run/) for our development toolchain to manage AWS lambda functions.

Configure `project.json` with the account specific settings (you will also need your AWS credentials somewhere), install apex, and run

    apex deploy

to deploy the lambda functions. :)

You need to make sure your IAM role has `lambda:InvokeFunction` permissions, and `s3:DeleteObject` permissions on the output bucket.

### Invoking the AWS Lambda

The `extract` method in both `pdf_extractor` and `office_extractor` expects an `event` with

- `doc_uri`: An S3 URI containing the document to extract text from, i.e., `s3://bucket/key.pdf`.
- `text_uri`: An S3 URI where the extracted text will be stored, i.e., `s3://bucket/key.txt`.

### PDF parsing with OCR

Due to the slow nature of OCR on images and AWS Lambda's 300 seconds execution limit, we used a hack (i.e., another lambda invocation) to OCR the pages of a PDF in parallel, while using S3 as our temporary store.
When we determine that a PDF needs to be processed using OCR (i.e., standard text extraction yield < 512 bytes), we invoke `pdf_extractor.extract` with a special `event`:
```json
{
  "doc_uri": "s3://docbot-test-lambda/image.pdf",
  "text_uri": "s3://docbot-test-lambda/image.txt-1",
  "page": 5,
  "force_ocr": true
}
```
where `page` refers to the page of the original PDF that we want to extract text from.
In the new lambda invocation, we use Ghostscript to convert that particular page to PNG and OCR using Tesseract to extract the text.

The original calling lambda function will wait and poll S3 at 1 second intervals for extracted text.
When all pages have been processed or when there is less than 5 seconds remaining on our clock, we will combine the pages' text that we have and return.
Missing pages will be logged as a warning to the default logger.
If anybody knows of a better pattern for processing PDFs, do feel free to submit a pull request.

Note that the `force_ocr` field can be used with any PDF to use OCR text extraction instead of `pdftotext`.

## Building executables and modules for the AWS Lambda execution environment

The executables, configs, and libraries in `bin-linux_x64` and `lib-linux_x64` has been compiled on an EC2 instance with a fresh install of `amzn-ami-hvm-2016.03.3.x86_64-gp2` AMI (this is AWS Lambda's execution AMI as of 12/17/2016).
Below are notes on how we obtained these binaries.

### Pre-requisites

You will need

- an EC2 instance with [AWS Lambda's execution environment](http://docs.aws.amazon.com/lambda/latest/dg/current-supported-versions.html), i.e., the same AMI.
- to do `sudo yum groupinstall "Development Tools"` for compiling some of the binaries from source

### pdftotext

We use `pdftotext` to extract text directly from PDF files. `pdftotext` is based on [Xpdf](http://www.foolabs.com/xpdf/download.html).

    curl http://mirrors.ctan.org/support/xpdf/xpdfbin-linux-3.04.tar.gz | tar xzv
    cp xpdfbin-linux-3.04/bin64/pdftotext text-extractor/bin-linux_x64/

### Ghostscript

[Ghostscript](https://ghostscript.com/download/gsdnld.html) is used for splitting PDF files into individual image pages.

    curl -L https://github.com/ArtifexSoftware/ghostpdl-downloads/releases/download/gs920/ghostscript-9.20-linux-x86_64.tgz | tar xzv
    cp ghostscript-9.20-linux-x86_64/gs-920-linux_x86_64 text-extractor/bin-linux_x64/

### Catdoc (DEPRECATED)

**catdoc requires charset files to be in `/usr/lib`.**

[catdoc](http://www.wagner.pp.ru/~vitus/software/catdoc/) is used for handling old format Word, Excel, and Powerpoint files.

    curl http://ftp.wagner.pp.ru/pub/catdoc/catdoc-0.95.tar.gz | tar xzv
    cd catdoc-0.95 && ./configure && make
    cd ..
    cp catdoc-0.95/src/{catdoc,catppt,xls2csv} text-extractor/bin-linux_x64/

### Antiword

[Antiword](http://www.winfield.demon.nl/) handles Office 97 formats.

    curl http://www.winfield.demon.nl/linux/antiword-0.37.tar.gz | tar xzv
    cd antiword-0.37 && make
    cd ..
    cp antiword-0.37/antiword text-extractor/bin-linux_x64/
    cp -r antiword-0.37/Resources text-extractor/lib-linux_x64/antiword

### Unrtf

[UnRTF](https://www.gnu.org/software/unrtf/) is a command-line program written in C which can convert documents in Rich Text Format (.rtf) to text.

    curl https://www.gnu.org/software/unrtf/unrtf-0.21.9.tar.gz | tar xzv
    cd unrtf-0.21.9 && ./configure && make
    cp unrtf-0.21.9/src/unrtf text-extractor/bin-linux_x64/
    cp -r unrtf-0.21.9/outputs text-extractor/lib-linux_x64/unrtf

### Tesseract

[Tesseract](https://github.com/tesseract-ocr/tesseract/) is an OCR tool for converting images to text.
We more or less followed instructions from [here](http://stackoverflow.com/questions/33588262/tesseract-ocr-on-aws-lambda-via-virtualenv).
We are using Tesseract 3.05.00dev.

    sudo yum install libtool
    sudo yum install libjpeg-devel libpng-devel libtiff-devel zlib-devel

    curl http://www.leptonica.com/source/leptonica-1.73.tar.gz | tar xzv
    cd leptonica-1.73 && ./configure && make && sudo make install && cd ..

    curl -L https://github.com/tesseract-ocr/tesseract/archive/3.05.tar.gz | tar xzv
    cd tesseract-3.05/ && ./autogen.sh && ./configure && make && sudo make install && cd ..


    mkdir text-extractor/lib-linux_x64/tesseract
    cp /usr/local/lib/{libtesseract.so.3,liblept.so.5} text-extractor/lib-linux_x64/tesseract/
    cp /lib64/{librt.so.1,libz.so.1,libpthread.so.0,libm.so.6,libgcc_s.so.1,libc.so.6,ld-linux-x86-64.so.2} text-extractor/lib-linux_x64/tesseract/
    cp /usr/lib64/{libpng12.so.0,libjpeg.so.62,libtiff.so.5,libstdc++.so.6,libjbig.so.2.0} text-extractor/lib-linux_x64/tesseract/
    cp /usr/local/share/tessdata/eng.traineddata text-extractor/lib-linux_x64/tesseract/
    cp /usr/local/bin/tesseract text-extractor/bin-linux_x64/

    mkdir text-extractor/lib-linux_x64/tesseract/tessdata
    curl -L https://github.com/tesseract-ocr/tessdata/archive/3.04.00.tar.gz | tar xzv
    cp tessdata-3.04.00/eng.* text-extractor/lib-linux_x64/tesseract/tessdata/

### ImageMagick

[ImageMagick](https://www.imagemagick.org/) is used to resample and convert between image types.
Many of the libraries needed here are similar to that for Tesseract.

    curl https://www.imagemagick.org/download/ImageMagick.tar.gz | tar xvz
    cd ImageMagick-7.0.3 && ./configure && make && cd ..

    cp ImageMagick-7.0.3/utilities/magick text-extractor/bin-linux_x64/magick

The shared libraries required are a subset of that for Tesseract, hence we will directly use `lib-linux_x64/tesseract` as the `LD_LIBRARY_PATH`.

### lxml

[lxml](http://lxml.de/) library is used for many of the XML formats.
We use the pre-compiled for AWS Lambda lxml package from [lambda-lxml-base](https://github.com/cjpetrus/lambda-lxml-base)

### Pillow

[Pillow]() library is used by python-pptx for parsing Microsoft Powerpoint files.
We use the pre-compiled PIL libraries from [aws-lambda-pillow](https://github.com/jDmacD/aws-lambda-pillow/).

