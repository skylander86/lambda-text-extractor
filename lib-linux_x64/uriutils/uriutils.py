"""
This module provides wrapper function for transparently handling files regardless of location (local, cloud, etc).
"""
__all__ = ['uri_open', 'uri_read', 'uri_dump', 'uri_exists', 'get_uri_metadata', 'uri_exists_wait', 'URIFileType', 'URIType', 'URIDirType', 'get_uri_obj']

# from contextlib import contextmanager
import atexit
import gzip
from io import BytesIO, TextIOWrapper, FileIO
import logging
import os
from tempfile import NamedTemporaryFile
import time

try: from urlparse import urlparse  # Python 2
except ImportError: from urllib.parse import urlparse  # Python 3

from .storages import STORAGES, URIBytesOutput, BaseURI

logger = logging.getLogger(__name__)


def get_uri_obj(uri, storage_args={}):
    if isinstance(uri, BaseURI): return uri
    uri_obj = None

    o = urlparse(uri)
    for storage in STORAGES:
        uri_obj = storage.parse_uri(o, storage_args=storage_args)
        if uri_obj is not None:
            break
    #end for
    if uri_obj is None:
        raise TypeError('<{}> is an unsupported URI.'.format(uri))

    return uri_obj
#end def


def uri_open(uri, mode='rb', auto_compress=True, in_memory=True, delete_tempfile=True, textio_args={}, storage_args={}):
    if isinstance(uri, BaseURI): uri = str(uri)
    uri_obj = get_uri_obj(uri, storage_args)

    if mode == 'rb': read_mode, binary_mode = True, True
    elif mode == 'r': read_mode, binary_mode = True, False
    elif mode == 'w': read_mode, binary_mode = False, False
    elif mode == 'wb': read_mode, binary_mode = False, True
    else: raise TypeError('`mode` cannot be "{}".'.format(mode))

    if read_mode:
        if in_memory:
            file_obj = BytesIO(uri_obj.get_content())
            setattr(file_obj, 'name', str(uri_obj))
        else:
            file_obj = _TemporaryURIFileIO(uri_obj=uri_obj, input_mode=True, delete_tempfile=delete_tempfile)
        #end if
    else:
        if in_memory: file_obj = URIBytesOutput(uri_obj)
        else:
            file_obj = _TemporaryURIFileIO(uri_obj=uri_obj, input_mode=False, pre_close_action=uri_obj.upload_file, delete_tempfile=delete_tempfile)
            setattr(file_obj, 'name', str(uri_obj))
        #end if
    #end if

    temp_name = getattr(file_obj, 'temp_name', None)

    if auto_compress:
        _, ext = os.path.splitext(uri)
        ext = ext.lower()
        if ext == '.gz': file_obj = gzip.GzipFile(fileobj=file_obj, mode='rb' if read_mode else 'wb')
    #end if

    if not binary_mode:
        textio_args.setdefault('encoding', 'utf-8')
        file_obj = TextIOWrapper(file_obj, **textio_args)
    #end if

    if not hasattr(file_obj, 'temp_name'): setattr(file_obj, 'temp_name', temp_name)

    return file_obj
#end def


def uri_read(*args, **kwargs):
    with uri_open(*args, **kwargs) as f:
        content = f.read()
    return content
#end def


def uri_dump(uri, content, mode='wb', **kwargs):
    with uri_open(uri, mode=mode, **kwargs) as f:
        f.write(content)
        f.flush()
    #end with
#end def


def get_uri_metadata(uri, storage_args={}):
    uri_obj = get_uri_obj(uri, storage_args)
    return uri_obj.get_metadata()
#end def


def uri_exists(uri, storage_args={}):
    uri_obj = get_uri_obj(uri, storage_args)
    return uri_obj.exists()
#end def


def uri_exists_wait(uri, timeout=300, interval=5, storage_args={}):
    uri_obj = get_uri_obj(uri, storage_args)
    start_time = time.time()
    while time.time() - start_time < timeout:
        if uri_obj.exists(): return True
        time.sleep(interval)
    #end while

    if uri_exists(uri): return True

    return False
#end def


class URIFileType(object):
    def __init__(self, mode='rb', **kwargs):
        self.kwargs = kwargs
        self.kwargs['mode'] = mode
    #end def

    def __call__(self, uri):
        f = uri_open(uri, **self.kwargs)
        atexit.register(lambda: f.close())
        return f
    #end def
#end class


class URIType(object):
    def __call__(self, uri):
        o = urlparse(uri)
        return o
    #end def
#end class


class URIDirType(object):
    def __init__(self, create=False, storage_args={}):
        self.create = create
        self.storage_args = storage_args
    #end def

    def __call__(self, uri):
        uri_obj = get_uri_obj(uri, self.storage_args)

        if not uri_obj.dir_exists():
            if self.create:
                uri_obj.make_dir()
                logger.info('Created directory <{}>.'.format(uri))
            else:
                raise OSError('<{}> is not a valid directory.'.format(uri))
        #end if

        return uri_obj
    #end def
#end class


class _TemporaryURIFileIO(FileIO):
    def __init__(self, uri_obj=None, input_mode=True, pre_close_action=None, delete_tempfile=True):
        with NamedTemporaryFile(delete=False) as f:
            temp_name = f.name

        if input_mode and uri_obj:
            uri_obj.download_file(temp_name)
        #end if

        self.uri_obj = uri_obj
        self.temp_name = temp_name
        self.pre_close_action = pre_close_action
        self.delete_tempfile = delete_tempfile

        super(_TemporaryURIFileIO, self).__init__(temp_name, 'rb' if input_mode else 'wb')

        self.name = str(self.uri_obj)  # must come after super __init__
    #end def

    def close(self):
        if not self.closed:
            super(_TemporaryURIFileIO, self).close()

            if self.pre_close_action: self.pre_close_action(self.temp_name)
            if self.delete_tempfile: os.remove(self.temp_name)
        #end if
    #end def
#end class
