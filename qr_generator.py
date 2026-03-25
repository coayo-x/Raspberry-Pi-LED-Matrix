from pathlib import Path

QR_CACHE_PATH = Path("qr_cache.png")


def generate_qr_if_missing(url: str) -> str:
    if QR_CACHE_PATH.exists():
        return str(QR_CACHE_PATH)

    try:
        import qrcode
    except ImportError:
        return str(QR_CACHE_PATH)

    qr = qrcode.QRCode(border=1)
    qr.add_data(url)
    qr.make(fit=True)
    image = qr.make_image(fill_color="white", back_color="black")
    image = image.get_image() if hasattr(image, "get_image") else image
    image.convert("RGBA").save(QR_CACHE_PATH)
    return str(QR_CACHE_PATH)
