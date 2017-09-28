# Building Binary Executables and Dependencies

The executables, configs, and libraries in `bin-linux_x64` and `lib-linux_x64` has been compiled on an EC2 with the `amzn-ami-hvm-2017.03.1.20170812-x86_64-gp2` AMI (this is AWS Lambda's execution AMI as of 2017/09/21).

Below are notes on how we obtained these binaries.

## Pre-requisites

You will need

- an EC2 instance with the latest [AWS Lambda's execution environment](http://docs.aws.amazon.com/lambda/latest/dg/current-supported-versions.html), i.e., the same AMI.
- to do `sudo yum -y groupinstall "Development Tools"` for compiling some of the binaries from source
- Python 3.6 is not yet available on the AWS Lambda AMI, so we need to install it from source: see [instructions](https://gist.github.com/niranjv/f80fc1f488afc49845e2ff3d5df7f83b) here.

## Python packages

We use pip to install Python packages in our virtual environment, then copy them to our lib:

    pip install --upgrade -r requirements.txt
    rm -rfv lib-linux_x64/{aiobotocore,aiohttp,async_timeout,certifi,chardet,docx,idna,multidict,odf,packaging,pptx,pyparsing.py,requests,urllib3,uriutils,wrapt,xlrd}
    cp -varu venv/lib/python3.6/site-packages/{aiobotocore,aiohttp,async_timeout,certifi,chardet,docx,idna,multidict,odf,packaging,pptx,pyparsing.py,requests,urllib3,uriutils,wrapt,xlrd} ./lib-linux_x64
    find lib-linux_x64/ -name \*.pyc -exec rm -v {} \;
    find lib-linux_x64/ -name __pycache__ -exec rmdir {} \;

## Poppler (`pdftotext`, `pdfinfo`)

We use `pdftotext` to extract text directly from PDF files, specifically, we use the variant provided by [Poppler](https://poppler.freedesktop.org/).
The poppler variant is still being developed and it does not respect DRMs.

    sudo yum -y install openjpeg-devel libjpeg-devel fontconfig-devel libtiff-devel libpng-devel

    curl https://poppler.freedesktop.org/poppler-0.59.0.tar.xz | tar xJv
    cd poppler-0.59.0/ && ./configure --enable-static --enable-build-type=release && make && cd ..

    rm -rfv text-extractor/lib-linux_x64/pdftotext
    mkdir text-extractor/lib-linux_x64/pdftotext
    cp /usr/lib64/{libopenjpeg.so.2,libtiff.so.5,libjpeg.so.62,libpng12.so.0,libfreetype.so.6,libfontconfig.so.1,libjbig.so.2.0} text-extractor/lib-linux_x64/pdftotext/
    cp /lib64/{libz.so.1,libexpat.so.1} text-extractor/lib-linux_x64/pdftotext/
    cp poppler-0.59.0/poppler/.libs/libpoppler.so.70 text-extractor/lib-linux_x64/pdftotext/
    cp poppler-0.59.0/utils/.libs/{pdftotext,pdfinfo,pdfseparate} text-extractor/bin-linux_x64/

`pdfinfo` is used to get the number of pages of the PDF file.

`pdfseparate` is used to get the individual pages in PDF format.

**(DEPRECATED)** This version is the original Xpdf one which respects DRM permissions. Tsk.
We use `pdftotext` to extract text directly from PDF files. `pdftotext` is based on [Xpdf](http://www.foolabs.com/xpdf/download.html).

    curl http://mirrors.ctan.org/support/xpdf/xpdfbin-linux-3.04.tar.gz | tar xzv
    cp xpdfbin-linux-3.04/bin64/pdftotext text-extractor/bin-linux_x64/

## Ghostscript

[Ghostscript](https://ghostscript.com/download/gsdnld.html) is used for splitting PDF files into individual image pages.

    curl -L https://github.com/ArtifexSoftware/ghostpdl-downloads/releases/download/gs921/ghostscript-9.21-linux-x86_64.tgz | tar xzv
    cp ghostscript-9.21-linux-x86_64/gs-921-linux-x86_64 text-extractor/bin-linux_x64/gs

## Antiword

[Antiword](http://www.winfield.demon.nl/) handles Office 97 formats.

    curl http://www.winfield.demon.nl/linux/antiword-0.37.tar.gz | tar xzv
    cd antiword-0.37 && make
    cd ..
    cp antiword-0.37/antiword text-extractor/bin-linux_x64/
    cp -r antiword-0.37/Resources text-extractor/lib-linux_x64/antiword

## Catdoc

[catdoc](http://www.wagner.pp.ru/~vitus/software/catdoc/) is used for handling old format Word, Excel, and Powerpoint files.
It seems to be more robust than antiword and will be used as a fallback option.

    curl http://ftp.wagner.pp.ru/pub/catdoc/catdoc-0.95.tar.gz | tar xzv
    patch catdoc-0.95/src/catdoc.c < text-extractor/lib-linux_x64/catdoc_customrc.patch
    patch catdoc-0.95/src/catppt.c < text-extractor/lib-linux_x64/catppt_customrc.patch
    cd catdoc-0.95 && ./configure && make && cd ..
    cp catdoc-0.95/src/{catdoc,catppt} text-extractor/bin-linux_x64/

We patched the source code to read catdoc rc file from an environment variable instead of from fixed paths in the system.

*Note*: `catppt` doesnt seem to work as of 2017/08/10.

## Unrtf

[UnRTF](https://www.gnu.org/software/unrtf/) is a command-line program written in C which can convert documents in Rich Text Format (.rtf) to text.

    curl https://www.gnu.org/software/unrtf/unrtf-0.21.9.tar.gz | tar xzv
    cd unrtf-0.21.9 && ./configure && make
    cp unrtf-0.21.9/src/unrtf text-extractor/bin-linux_x64/
    cp -r unrtf-0.21.9/outputs text-extractor/lib-linux_x64/unrtf

## Tesseract

[Tesseract](https://github.com/tesseract-ocr/tesseract/) is an OCR tool for converting images to text.
We more or less followed instructions from [here](http://stackoverflow.com/questions/33588262/tesseract-ocr-on-aws-lambda-via-virtualenv).
We are using Tesseract 3.05.

    sudo yum -y install libtool
    sudo yum -y install libjpeg-devel libpng-devel libtiff-devel zlib-devel

    curl http://www.leptonica.com/source/leptonica-1.74.4.tar.gz | tar xzv
    cd leptonica-1.74.4 && ./configure && make && sudo make -j 4 install && cd ..

    curl -L https://github.com/tesseract-ocr/tesseract/archive/3.05.tar.gz | tar xzv
    export PKG_CONFIG_PATH=/usr/local/lib/pkgconfig
    cd tesseract-3.05/ && ./autogen.sh && ./configure && make && sudo make -j 4 install && cd ..

    mkdir text-extractor/lib-linux_x64/tesseract
    cp /usr/local/lib/{libtesseract.so.3,liblept.so.5} text-extractor/lib-linux_x64/tesseract/
    cp /lib64/libz.so.1 text-extractor/lib-linux_x64/tesseract/
    cp /usr/lib64/{libpng12.so.0,libjpeg.so.62,libtiff.so.5,libjbig.so.2.0} text-extractor/lib-linux_x64/tesseract/
    cp /usr/local/bin/tesseract text-extractor/bin-linux_x64/

    mkdir text-extractor/lib-linux_x64/tesseract/tessdata
    curl -L https://github.com/tesseract-ocr/tessdata/archive/3.04.00.tar.gz | tar xzv
    cp tessdata-3.04.00/{eng.*,osd.traineddata} text-extractor/lib-linux_x64/tesseract/tessdata/
    cp tesseract-3.05/tessdata/eng.* text-extractor/lib-linux_x64/tesseract/tessdata/
    cp tesseract-3.05/tessdata/pdf.ttf text-extractor/lib-linux_x64/tesseract/tessdata/
    mkdir text-extractor/lib-linux_x64/tesseract/tessdata/configs
    cp tesseract-3.05/tessdata/configs/pdf text-extractor/lib-linux_x64/tesseract/tessdata/configs

## lxml

[lxml](http://lxml.de/) library is used for many of the XML formats.
We use pip to setup the lxml module and then copy the relevant files into our lib:

    sudo yum install libxml2 libxml2-devel libxslt libxslt-devel
    pip install --upgrade lxml
    rm -rfv lib-linux_x64/lxml
    cp -vr venv/lib/python3.6/site-packages/lxml lib-linux_x64/
    find lib-linux_x64/lxml -name \*.pyc -exec rm -v {} \;

The current version of lxml is 4.0.0.

## Pillow

[Pillow](https://python-pillow.org/) library is used by python-pptx for parsing Microsoft Powerpoint files.

    pip install --upgrade pillow
    rm -rfv lib-linux_x64/PIL
    cp -var venv/lib/python3.6/site-packages/PIL lib-linux_x64/
    find lib-linux_x64/PIL -name \*.pyc -exec rm -v {} \;

The current version of pillow is 4.2.1.

### Storing PIL on S3 (Not used)

*Note*: This is currently not implemented.

Because PIL is quite huge and we cannot upload large code sizes to Lambda, we store PIL on S3 to be downloaded on use.

    tar -cv -C lib-linux_x64/ PIL -O > test.tar | aws s3 cp - s3://assets-bucket/textractor/PIL.tar

## PyPDF2 (DEPRECATED)

[PyPDF2](https://github.com/mstamy2/PyPDF2) is a Python module which we use for basic manipulations of PDF files.

    curl https://github.com/mstamy2/PyPDF2/archive/master.zip
    unzip PyPDF2-master.zip 'PyPDF2-master/PyPDF2/*' -d .
    mv PyPDF2-master/PyPDF2 lib-linux_x64/
