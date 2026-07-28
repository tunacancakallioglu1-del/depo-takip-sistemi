# -*- coding: utf-8 -*-
"""Audit log yardımcıları"""

import json
from database import db, AuditLog


def log_audit(islem, tablo, kayit_id=None, eski_deger=None, yeni_deger=None, sonuc='basarili', kullanici_id='system'):
    log = AuditLog(
        kullanici_id=kullanici_id,
        islem=islem,
        tablo=tablo,
        kayit_id=str(kayit_id) if kayit_id is not None else None,
        eski_deger=json.dumps(eski_deger, ensure_ascii=False) if eski_deger is not None else None,
        yeni_deger=json.dumps(yeni_deger, ensure_ascii=False) if yeni_deger is not None else None,
        sonuc=sonuc,
    )
    db.session.add(log)
    db.session.flush()
    return log
