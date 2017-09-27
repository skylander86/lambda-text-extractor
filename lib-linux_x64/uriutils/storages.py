__all__ = ['STORAGES', 'URIBytesOutput', 'BaseURI']

from io import BytesIO
import os
import shutil

try: from urlparse import urlparse  # Python 2
except ImportError: from urllib.parse import urlparse  # Python 3

try:
    import boto3
    import botocore.exceptions
except ImportError: boto3 = None

try:
    from google.cloud import storage as gcloud_storage
    import google.cloud.exceptions
except ImportError: gcloud_storage = None

try: import requests
except ImportError: requests = None


class URIBytesOutput(BytesIO):
    """A BytesIO object that flushes content to the remote object on close."""

    def __init__(self, uri_obj):
        super(URIBytesOutput, self).__init__()
        self.uri_obj = uri_obj
    #end def

    def close(self):
        if not self.closed:
            self.uri_obj.put_content(self.getvalue())
            super(URIBytesOutput, self).close()
        #end if
    #end def

    @property
    def name(self):
        return str(self.uri_obj)
#end class


class BaseURI(object):
    SUPPORTED_SCHEMES = []
    VALID_STORAGE_ARGS = []

    @classmethod
    def parse_uri(cls, uri, storage_args={}):
        """Returns `None` if this storage system does not support :attr:`uri`."""
        raise NotImplementedError('`parse_uri` is not implemented for {}.'.format(type(cls).__name__))
    #end def

    def __init__(self, storage_args={}):
        self.storage_args = dict((k, v) for k, v in storage_args.items() if k in self.VALID_STORAGE_ARGS)
    #end def

    def get_content(self):
        """Returns the binary content stored in the URI for this object."""
        raise NotImplementedError('`get_content` is not implemented for {}.'.format(type(self).__name__))

    def put_content(self, content):
        """Returns a file-like object that allows writing to this URI."""
        raise NotImplementedError('`put_content` is not implemented for {}.'.format(type(self).__name__))

    def download_file(self, filename):
        """Download the binary content stored in the URI for this object directly to `filename`."""
        raise NotImplementedError('`download_file` is not implemented for {}.'.format(type(self).__name__))

    def upload_file(self, filename):
        """Download the binary content stored in the URI for this object directly to `filename`."""
        raise NotImplementedError('`upload_file` is not implemented for {}.'.format(type(self).__name__))

    def get_metadata(self): return {}

    def exists(self):
        """Check if the URI exists."""
        raise NotImplementedError('`exists` is not implemented for {}.'.format(type(self).__name__))

    def dir_exists(self):
        """Check if the URI exists as a directory."""
        raise NotImplementedError('`dir_exists` is not implemented for {}.'.format(type(self).__name__))

    def make_dir(self):
        raise NotImplementedError('`make_dir` is not implemented for {}.'.format(type(self).__name__))

    def list_dir(self):
        raise NotImplementedError('`list_dir` is not implemented for {}.'.format(type(self).__name__))

    def join(self, path):
        return self.parse_uri(urlparse(os.path.join(str(self), path)), storage_args=self.storage_args)

    def __str__(self):
        """Returns a nicely formed URI for this object."""
        raise NotImplementedError('`__str__` is not implemented for {}.'.format(type(self).__name__))
    #end def

    def __unicode__(self):
        return self.__str__()

    def __repr__(self):
        return '{}({})'.format(type(self).__name__, str(self))
#end class


class FileURI(BaseURI):
    SUPPORTED_SCHEMES = set(['file', ''])

    @classmethod
    def parse_uri(cls, uri, storage_args={}):
        if uri.scheme not in cls.SUPPORTED_SCHEMES: return None
        filepath = os.path.join(uri.netloc, uri.path.lstrip('/')).rstrip('/') if uri.netloc else uri.path
        return FileURI(filepath, storage_args=storage_args)
    #end def

    def __init__(self, filepath, storage_args={}):
        super(FileURI, self).__init__(storage_args=storage_args)
        self.filepath = filepath
    #end def

    def get_content(self):
        with open(self.filepath, 'rb') as f:
            return f.read()
    #end def

    def put_content(self, content):
        with open(self.filepath, 'wb') as f:
            return f.write(content)

    def download_file(self, filename):
        shutil.copyfile(self.filepath, filename)
    #end def

    def upload_file(self, filename):
        shutil.copyfile(filename, self.filepath)

    def exists(self):
        return os.path.exists(self.filepath)

    def dir_exists(self):
        return os.path.isdir(self.filepath)

    def make_dir(self):
        os.makedirs(self.filepath)

    def list_dir(self):
        for fname in os.listdir(self.filepath):
            yield os.path.join(self.filepath, fname)

    def __str__(self):
        return self.filepath
#end class


class S3URI(BaseURI):
    SUPPORTED_SCHEMES = set(['s3'])
    VALID_STORAGE_ARGS = ['CacheControl', 'ContentDisposition', 'ContentEncoding', 'ContentLanguage', 'ContentLength', 'ContentMD5', 'ContentType', 'Expires', 'GrantFullControl', 'GrantRead', 'GrantReadACP', 'GrantWriteACP', 'Metadata', 'ServerSideEncryption', 'StorageClass', 'WebsiteRedirectLocation', 'SSECustomerAlgorithm', 'SSECustomerKey', 'SSEKMSKeyId', 'RequestPayer', 'Tagging']

    s3_resource = None

    @classmethod
    def parse_uri(cls, uri, storage_args={}):
        if uri.scheme not in cls.SUPPORTED_SCHEMES: return None
        if boto3 is None: raise ImportError('You need to install boto3 package to handle {} URIs.'.format(uri.scheme))

        if cls.s3_resource is None: cls.s3_resource = boto3.resource('s3')

        return S3URI(uri.netloc, uri.path.lstrip('/'), storage_args=storage_args)
    #end def

    def __init__(self, bucket, key, storage_args={}):
        super(S3URI, self).__init__(storage_args=storage_args)

        self.s3_object = self.s3_resource.Object(bucket, key)
    #end def

    def get_content(self):
        r = self.s3_object.get(**self.storage_args)
        return r['Body'].read()
    #end def

    def put_content(self, content):
        self.s3_object.put(Body=content, **self.storage_args)

    def download_file(self, filename):
        self.s3_object.download_file(filename, **self.storage_args)

    def upload_file(self, filename):
        self.s3_object.upload_file(filename, ExtraArgs=self.storage_args)

    def get_metadata(self):
        self.s3_object.load()
        return self.s3_object.metadata

    def exists(self):
        try:
            self.s3_object.load()
            return True
        except botocore.exceptions.ClientError: return False
    #end def

    def dir_exists(self): return True

    def make_dir(self): pass

    def list_dir(self):
        bucket = self.s3_object.Bucket()
        prefix = self.s3_object.key
        if not prefix.endswith('/'): prefix += '/'

        for obj in bucket.objects.filter(Delimiter='/', Prefix=prefix):
            yield 's3://{}/{}'.format(obj.bucket_name, obj.key)
    #end def

    def __str__(self):
        return 's3://{}/{}'.format(self.s3_object.bucket_name, self.s3_object.key)
#end class


class GoogleCloudStorageURI(BaseURI):
    SUPPORTED_SCHEMES = set(['gs', 'gcs'])
    VALID_STORAGE_ARGS = ['chunk_size', 'encryption_key']

    gs_client = None

    @classmethod
    def parse_uri(cls, uri, storage_args={}):
        if uri.scheme not in cls.SUPPORTED_SCHEMES: return None
        if gcloud_storage is None: raise ImportError('You need to install google-cloud-storage package to handle {} URIs.'.format(uri.scheme))

        if cls.gs_client is None: cls.gs_client = gcloud_storage.Client()

        return GoogleCloudStorageURI(uri.netloc, uri.path.lstrip('/'), storage_args=storage_args)
    #end def

    def __init__(self, bucket, key, storage_args={}):
        self.content_type = storage_args.get('content_type', 'application/octet-stream')
        self.content_encoding = storage_args.get('content_encoding', None)
        self.metadata = storage_args.get('metadata', {})
        self.metadata.update(storage_args.get('Metadata', {}))

        super(GoogleCloudStorageURI, self).__init__(storage_args=storage_args)

        self.blob = self.gs_client.bucket(bucket).blob(key, **self.storage_args)
    #end def

    def get_content(self):
        return self.blob.download_as_string()

    def put_content(self, content):
        self.blob.content_encoding = self.content_encoding
        self.blob.metadata = self.metadata
        return self.blob.upload_from_string(content, content_type=self.content_type)

    def download_file(self, filename):
        self.blob.download_to_filename(filename)

    def upload_file(self, filename):
        self.blob.content_encoding = self.content_encoding
        self.blob.metadata = self.metadata
        self.blob.upload_from_filename(filename, content_type=self.content_type)

    def get_metadata(self):
        self.blob.reload()
        return self.blob.metadata

    def exists(self):
        try:
            self.blob.reload()
            return True
        except google.cloud.exceptions.NotFound: return False
    #end def

    def dir_exists(self): return True

    def make_dir(self): pass

    def list_dir(self):
        bucket = self.blob.bucket
        prefix = self.blob.name
        if not prefix.endswith('/'): prefix += '/'

        for blob in bucket.list_blobs(prefix=prefix, delimiter='/'):
            yield 'gs://{}/{}'.format(blob.bucket.name, blob.name)
    #end def

    def __str__(self):
        return 'gs://{}/{}'.format(self.blob.bucket.name, self.blob.name)
#end class


class HTTPURI(BaseURI):
    SUPPORTED_SCHEMES = set(['http', 'https'])
    VALID_STORAGE_ARGS = ['params', 'headers', 'cookies', 'auth', 'timeout', 'allow_redirects', 'proxies', 'verify', 'stream', 'cert', 'method']

    @classmethod
    def parse_uri(cls, uri, storage_args={}):
        global requests

        if uri.scheme not in cls.SUPPORTED_SCHEMES: return None
        if requests is None: raise ImportError('You need to install requests package to handle {} URIs.'.format(uri.scheme))

        return HTTPURI(uri.geturl(), storage_args=storage_args)
    #end def

    def __init__(self, url, storage_args={}):
        super(HTTPURI, self).__init__(storage_args=storage_args)
        self.url = url
        self.method = self.storage_args.pop('method', None)
        self.raise_for_status = self.storage_args.pop('raise_for_status', True)
    #end def

    def get_content(self):
        r = requests.request(self.method if self.method else 'GET', self.url, **self.storage_args)
        if self.raise_for_status: r.raise_for_status()
        return r.content
    #end def

    def put_content(self, content):
        r = requests.request(self.method if self.method else 'PUT', self.url, data=content, **self.storage_args)
        if self.raise_for_status: r.raise_for_status()
    #end def

    def download_file(self, filename):
        kwargs = self.storage_args.copy()
        stream = kwargs.pop('stream', True)
        r = requests.request(self.method if self.method else 'GET', self.url, stream=stream, **kwargs)
        if self.raise_for_status: r.raise_for_status()
        with open(filename, 'wb') as f:
            for chunk in r.iter_content(chunk_size=1024):
                f.write(chunk)
    #end def

    def upload_file(self, filename):
        with open(filename, 'rb') as f:
            r = requests.request(self.method if self.method else 'PUT', self.url, data=f, **self.storage_args)
        if self.raise_for_status: r.raise_for_status()
    #end def

    def exists(self):
        try:
            requests.head(self.url).raise_for_status()
            return True
        except requests.HTTPError: return False
    #end def

    def dir_exists(self): return True

    def make_dir(self): pass

    def __str__(self):
        return self.url
#end class


class SNSURI(BaseURI):
    SUPPORTED_SCHEMES = set(['sns'])
    VALID_STORAGE_ARGS = ['Subject', 'MessageAttributes', 'MessageStructure']

    sns_resource = None

    @classmethod
    def parse_uri(cls, uri, storage_args={}):
        if uri.scheme not in cls.SUPPORTED_SCHEMES: return None
        if boto3 is None: raise ImportError('You need to install boto3 package to handle {} URIs.'.format(uri.scheme))

        if cls.sns_resource is None: cls.sns_resource = boto3.resource('sns')

        return SNSURI(uri.netloc, uri.path, storage_args=storage_args)
    #end def

    def __init__(self, topic_name, region, storage_args={}):
        super(SNSURI, self).__init__(storage_args=storage_args)

        region = region.lstrip('/')
        if not region:
            region = boto3.session.Session().region_name

        topic = None

        if topic_name.startswith('arn:'):
            topic = self.sns_resource.Topic(topic_name)
        else:
            account_id = boto3.client('sts').get_caller_identity().get('Account')
            topic = self.sns_resource.Topic('arn:aws:sns:{}:{}:{}'.format(region, account_id, topic_name))
        #end if

        self.topic = topic
    #end def

    def get_content(self):
        raise TypeError('SNSURI does not support reading.')
    #end def

    def put_content(self, content):
        if not isinstance(content, str):
            content = content.decode('utf-8')

        self.topic.publish(Message=content, **self.storage_args)
    #end def

    def download_file(self, filename):
        raise TypeError('SNSURI does not support reading.')
    #end def

    def upload_file(self, filename):
        with open(filename, 'rb') as f:
            self.topic.publish(Message=f.read(), **self.storage_args)
    #end def

    def exists(self):
        return self.topic.arn is not None
    #end def

    def dir_exists(self): return True

    def make_dir(self): pass

    def __str__(self):
        return self.topic.arn
#end class


STORAGES = [FileURI, S3URI, GoogleCloudStorageURI, HTTPURI, SNSURI]
