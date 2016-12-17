# text-extractor

Python wrapper app to extract text from various binary formats.

## Obtaining binaries

### Pre-requisites

You will need

- an EC2 instance with [AWS Lambda's execution environment](http://docs.aws.amazon.com/lambda/latest/dg/current-supported-versions.html), i.e., the same AMI.
- `sudo yum groupinstall "Development Tools"` for compiling some of the binaries from source

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

[Antiword](http://www.winfield.demon.nl/#Programmer) handles Office 97 formats.

    curl http://www.winfield.demon.nl/linux/antiword-0.37.tar.gz | tar xzv
    cd antiword-0.37 && make
    cd ..
    cp antiword-0.37/antiword text-extractor/bin-linux_x64/
    cp -r antiword-0.37/Resources text-extractor/lib-linux_x64/antiword

### Unrtf

[Unrtf](https://www.gnu.org/software/unrtf/) is a command-line program written in C which can convert documents in Rich Text Format (.rtf) to text.

    curl https://www.gnu.org/software/unrtf/unrtf-0.21.9.tar.gz | tar xzv
    cd unrtf-0.21.9 && ./configure && make
    cp unrtf-0.21.9/src/unrtf text-extractor/bin-linux_x64/
    cp -r unrtf-0.21.9/outputs text-extractor/lib-linux_x64/unrtf

### Tesseract

[Tesseract](https://github.com/tesseract-ocr/tesseract/) is an OCR tool for converting images to text.
We more or less followed instructions from [here](http://stackoverflow.com/questions/33588262/tesseract-ocr-on-aws-lambda-via-virtualenv).

    sudo yum install libtool
    sudo yum install libjpeg-devel libpng-devel libtiff-devel zlib-devel

    curl http://www.leptonica.com/source/leptonica-1.73.tar.gz | tar xzv
    cd leptonica-1.73 && ./configure && make && sudo make install && cd ..

    curl -L https://github.com/tesseract-ocr/tesseract/archive/3.04-rc1.tar.gz | tar xzv
    cd tesseract-3.04-rc1/ && ./autogen.sh && ./configure && make && sudo make install && cd ..

    sudo curl -L https://github.com/tesseract-ocr/tessdata/raw/master/eng.traineddata -o /usr/local/share/tessdata/eng.traineddata

    mkdir text-extractor/lib-linux_x64/tesseract
    cp /usr/local/lib/{libtesseract.so.3,liblept.so.5} text-extractor/lib-linux_x64/tesseract/
    cp /lib64/{librt.so.1,libz.so.1,libpthread.so.0,libm.so.6,libgcc_s.so.1,libc.so.6,ld-linux-x86-64.so.2} text-extractor/lib-linux_x64/tesseract/
    cp /usr/lib64/{libpng12.so.0,libjpeg.so.62,libtiff.so.5,libstdc++.so.6,libjbig.so.2.0} text-extractor/lib-linux_x64/tesseract/
    cp /usr/local/share/tessdata/eng.traineddata text-extractor/lib-linux_x64/tesseract/
    cp /usr/local/bin/tesseract text-extractor/bin-linux_x64/

## Lambda-izing

We use [apex](http://apex.run/) as our development toolchain for managing AWS lambda deploys

