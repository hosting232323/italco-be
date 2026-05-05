from io import BytesIO

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

MAX_EDGE = 2400


def enhance_delivery_photo_for_scan(img_bytes: bytes) -> tuple[bytes, str]:
  img = Image.open(BytesIO(img_bytes))
  img = ImageOps.exif_transpose(img)
  img = img.convert('RGB')
  w, h = img.size
  if max(w, h) > MAX_EDGE:
    scale = MAX_EDGE / max(w, h)
    img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
  img = ImageOps.autocontrast(img, cutoff=1)
  gray = img.convert('L')
  img = Image.merge('RGB', (gray, gray, gray))
  img = ImageEnhance.Contrast(img).enhance(1.15)
  img = img.filter(ImageFilter.UnsharpMask(radius=1, percent=115, threshold=3))
  out = BytesIO()
  img.save(out, format='JPEG', quality=88, optimize=True)
  return out.getvalue(), 'image/jpeg'
