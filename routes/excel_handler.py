# -*- coding: utf-8 -*-
"""Excel işleme yardımcıları ve ortak algoritmalar"""

import re
from datetime import datetime
from flask import jsonify
from database import db, Product, Size, CodeMapping, Toplama, ExcelUpload
from utils.excel_utils import calculate_file_hash, load_excel_rows
from utils.validators import validate_headers, validate_required_fields, parse_excel_date
from utils.audit_utils import log_audit


def normalize_code(value):
    return str(value or '').strip().upper()


def match_product_by_code(kod):
    normalized = normalize_code(kod)
    if not normalized:
        return None

    direct = Product.query.filter_by(ana_kod=normalized, durum=True).first()
    if direct:
        return direct

    mapping = CodeMapping.query.filter_by(kaynak_kod=normalized).first()
    if mapping and mapping.product and mapping.product.durum:
        return mapping.product

    if '-' in normalized:
        base_code = normalized.split('-')[0]
        base_match = Product.query.filter_by(ana_kod=base_code, durum=True).first()
        if base_match:
            return base_match

    m = re.match(r'([A-Z]+\d+)', normalized)
    if m:
        candidate = Product.query.filter_by(ana_kod=m.group(1), durum=True).first()
        if candidate:
            return candidate

    return None


def determine_toplama(product, beden):
    if product.beden_ayrimi:
        beden_val = str(beden or '').strip()
        size = Size.query.filter_by(product_id=product.id, beden=beden_val).first()
        if size:
            return size.toplama_id, None
        return None, f"Tanımsız beden: {beden_val}"
    return product.toplama_id, None


def validate_excel_upload(file_storage, expected_headers, required_fields, modul):
    if not file_storage:
        return None, None, jsonify({'basarili': False, 'mesaj': 'Dosya zorunludur!'}), 400

    filename = file_storage.filename or ''
    if not filename.lower().endswith(('.xlsx', '.xlsm', '.xltx', '.xltm')):
        return None, None, jsonify({'basarili': False, 'mesaj': 'Geçersiz dosya formatı!'}), 400

    file_hash = calculate_file_hash(file_storage)
    if ExcelUpload.query.filter_by(dosya_hash=file_hash).first():
        return None, None, jsonify({'basarili': False, 'mesaj': 'Bu Excel dosyası daha önce yüklenmiş!'}), 409

    headers, rows = load_excel_rows(file_storage)

    if not validate_headers(headers, expected_headers):
        return None, None, jsonify({
            'basarili': False,
            'mesaj': 'Excel başlıkları/sırası hatalı!',
            'beklenen': expected_headers,
            'bulunan': headers,
        }), 400

    errors = []
    for i, row in enumerate(rows, start=2):
        missing = validate_required_fields(row, required_fields)
        if missing:
            errors.append({'satir': i, 'hata': f'Zorunlu alan eksik: {", ".join(missing)}'})

    if errors:
        return None, None, jsonify({
            'basarili': False,
            'mesaj': 'Zorunlu alan hataları var',
            'hatalar': errors,
        }), 400

    upload = ExcelUpload(modul=modul, dosya_adi=filename, dosya_hash=file_hash, toplam_satir=len(rows))
    db.session.add(upload)
    db.session.flush()
    log_audit('excel_yukleme_basladi', 'excel_uploads', upload.id, yeni_deger={'modul': modul, 'dosya': filename})
    return upload, rows, None, None


def parse_row_date(row_value):
    parsed = parse_excel_date(row_value)
    return parsed or datetime.utcnow()


def get_toplama_by_value(value):
    if value is None or str(value).strip() == '':
        return None
    text = str(value).strip()
    if text.isdigit():
        return Toplama.query.get(int(text))
    return Toplama.query.filter_by(ad=text).first()
