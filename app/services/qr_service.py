try:
    import qrcode
except ImportError:
    qrcode = None

import io
import uuid
from app.models import QRCode
from app.extensions import db
from datetime import datetime, timezone

class QRService:
    def generate_qr_code(self, resource_id, metadata=None):
        unique_code = str(uuid.uuid4())
        
        if qrcode is not None:
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(unique_code)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            img_bytes = io.BytesIO()
            img.save(img_bytes, format='PNG')
            raw_bytes = img_bytes.getvalue()
        else:
            raw_bytes = b""

        return {"resource_id": resource_id, "unique_code": unique_code, "qr_code_url": f"/static/qr/{unique_code}.png"}, raw_bytes

    def scan_qr_code(self, unique_code):
        return {"unique_code": unique_code, "status": "valid"}

    def track_scan(self, unique_code, user_id=None):
        return {"unique_code": unique_code, "scanned_at": datetime.now(timezone.utc).isoformat()}
