from PIL import Image
import urllib3
import pytesseract
from io import BytesIO
http = urllib3.PoolManager()

def main(evt, ctx):
    url = evt["body"]
    response = http.request('GET', url)
    img = Image.open(BytesIO(response.data))
    txt = pytesseract.image_to_string(img, lang="deu")
    return {"statusCode": 200, "body": txt}

