# -*- coding: utf-8 -*-
"""İade yönetimi rotaları"""

import json
from io import BytesIO
import pandas as pd
from flask import Blueprint, render_template, request, jsonify, send_file
from database import db, Return
from routes.excel_handler import (
    validate_excel_upload,
    match_product_by_code,
    determine_toplama,
    parse_row_date,
)
from utils.excel_utils import build_template
from utils.audit_utils import log_audit

iadeler_bp = Blueprint('iadeler', __name__, url_prefix='/iadeler')


@iadeler_bp.route('/')
def index():
    return render_template('iadeler.html')


@iadeler_bp.route('/api/template')
def download_template():
    headers = ['Siparis No', 'Tarih', 'Urun Kodu', 'Beden', 'Adet', 'Sebep']
    stream = build_template(headers)
    return send_file(stream, as_attachment=True, download_name='iade_template.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@iadeler_bp.route('/api/excel-yukle', methods=['POST'])
def excel_yukle():
    expected_headers = ['Siparis No', 'Tarih', 'Urun Kodu', 'Beden', 'Adet', 'Sebep']
    required_fields = ['Siparis No', 'Urun Kodu', 'Adet']
    upload, rows, error_response, status = validate_excel_upload(request.files.get('file'), expected_headers, required_fields, 'iade')
    if error_response:
        return error_response, status

    row_errors = []
    preview_rows = []
    undefined_products = []
    undefined_sizes = []

    for row_no, row in enumerate(rows, start=2):
        try:
            product = match_product_by_code(row.get('Urun Kodu'))
            if not product:
                undefined_products.append({'satir': row_no, 'kod': str(row.get('Urun Kodu'))})
                row_errors.append({'satir': row_no, 'hata': 'Tanımsız ürün'})
                continue

            beden = str(row.get('Beden', '')).strip() or None
            toplama_id, beden_error = determine_toplama(product, beden)
            if beden_error:
                undefined_sizes.append({'satir': row_no, 'kod': product.ana_kod, 'beden': beden})
                row_errors.append({'satir': row_no, 'hata': beden_error})
                continue

            adet = int(float(row.get('Adet') or 0))
            if adet <= 0:
                raise ValueError('Adet 0 veya negatif olamaz')

            preview_rows.append({
                'siparis_no': str(row.get('Siparis No')).strip(),
                'tarih': parse_row_date(row.get('Tarih')).strftime('%Y-%m-%d'),
                'urun_id': product.id,
                'beden': beden,
                'adet': adet,
                'sebebi': str(row.get('Sebep', '')).strip() or None,
                'toplama_id': toplama_id,
            })
        except Exception:
            row_errors.append({'satir': row_no, 'hata': 'Satır işlenemedi'})

    upload.basarili = len(preview_rows)
    upload.basarisiz = len(row_errors)
    upload.preview_data = json.dumps({
        'valid_rows': preview_rows,
        'row_errors': row_errors,
        'undefined_products': undefined_products,
        'undefined_sizes': undefined_sizes,
    }, ensure_ascii=False)
    upload.status = 'KONTROL_EDILMEDI'
    upload.veri_aktarimi_yapildi = False
    upload.hata_sebebi = '; '.join(sorted({error['hata'] for error in row_errors})) if row_errors else None

    log_audit('excel_yukleme_tamamlandi', 'returns', upload.id, yeni_deger={
        'toplam_satir': len(rows),
        'basarili': len(preview_rows),
        'hatali': len(row_errors),
        'status': upload.status,
    })
    db.session.commit()

    return jsonify({
        'basarili': True,
        'mesaj': 'İade önizlemesi hazır. Kontrol edilmeden veri aktarımı yapılmadı.',
        'upload_id': upload.id,
        'status': upload.status,
        'ozet': {
            'toplam_satir': len(rows),
            'islenen_satir': len(preview_rows),
            'hatali_satir': len(row_errors),
            'tanimsiz_urun': len(undefined_products),
            'tanimsiz_beden': len(undefined_sizes),
        },
        'hatalar': row_errors,
        'tanimsiz_urunler': undefined_products,
        'tanimsiz_bedenler': undefined_sizes,
    })


@iadeler_bp.route('/api/kontrol-et/<int:upload_id>', methods=['POST'])
def kontrol_et(upload_id):
    from database import ExcelUpload
    upload = ExcelUpload.query.get_or_404(upload_id)
    if upload.modul != 'iade':
        return jsonify({'basarili': False, 'mesaj': 'Geçersiz yükleme kaydı'}), 400
    if upload.veri_aktarimi_yapildi:
        return jsonify({'basarili': False, 'mesaj': 'Bu yükleme zaten kontrol edildi.'}), 409

    payload = json.loads(upload.preview_data or '{}')
    valid_rows = payload.get('valid_rows', [])
    for row in valid_rows:
        ret = Return(
            siparis_no=row['siparis_no'],
            tarih=parse_row_date(row.get('tarih')),
            urun_id=row['urun_id'],
            beden=row.get('beden'),
            adet=int(row['adet']),
            sebebi=row.get('sebebi'),
            toplama_id=row['toplama_id'],
            excel_yukleme_id=upload.id,
        )
        db.session.add(ret)

    upload.status = 'KONTROL_EDILDI'
    upload.veri_aktarimi_yapildi = True
    db.session.commit()
    return jsonify({'basarili': True, 'mesaj': f'{len(valid_rows)} iade kaydı aktarıldı.'})


@iadeler_bp.route('/api/hata-raporu/<int:upload_id>')
def hata_raporu(upload_id):
    from database import ExcelUpload
    upload = ExcelUpload.query.get_or_404(upload_id)
    if upload.modul != 'iade':
        return jsonify({'basarili': False, 'mesaj': 'Geçersiz yükleme kaydı'}), 400

    payload = json.loads(upload.preview_data or '{}')
    rows = []
    for item in payload.get('undefined_products', []):
        rows.append({'Satır': item.get('satir'), 'Hata': 'Tanımsız ürün kodu', 'Kod': item.get('kod'), 'Beden': ''})
    for item in payload.get('undefined_sizes', []):
        rows.append({'Satır': item.get('satir'), 'Hata': 'Tanımsız beden', 'Kod': item.get('kod'), 'Beden': item.get('beden')})
    for item in payload.get('row_errors', []):
        rows.append({'Satır': item.get('satir'), 'Hata': item.get('hata'), 'Kod': item.get('kod', ''), 'Beden': item.get('beden', '')})

    df = pd.DataFrame(rows or [{'Satır': '', 'Hata': 'Hata bulunamadı', 'Kod': '', 'Beden': ''}])
    out = BytesIO()
    with pd.ExcelWriter(out, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Hata Raporu')
    out.seek(0)
    return send_file(out, as_attachment=True, download_name=f'iade_hata_raporu_{upload_id}.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@iadeler_bp.route('/api/<int:return_id>', methods=['PUT'])
def api_guncelle(return_id):
    ret = Return.query.get_or_404(return_id)
    data = request.json or {}
    eski = {'siparis_no': ret.siparis_no, 'beden': ret.beden, 'adet': ret.adet, 'sebebi': ret.sebebi}

    if 'beden' in data:
        ret.beden = str(data['beden'] or '').strip() or None
    if 'adet' in data:
        adet = int(float(data['adet'] or 0))
        if adet <= 0:
            return jsonify({'basarili': False, 'mesaj': 'Adet 0 veya negatif olamaz'}), 400
        ret.adet = adet
    if 'sebebi' in data:
        ret.sebebi = str(data['sebebi'] or '').strip() or None

    log_audit('update', 'returns', return_id, eski_deger=eski, yeni_deger={'beden': ret.beden, 'adet': ret.adet, 'sebebi': ret.sebebi})
    db.session.commit()
    return jsonify({'basarili': True, 'mesaj': 'İade güncellendi'})


@iadeler_bp.route('/api/<int:return_id>', methods=['DELETE'])
def api_sil(return_id):
    ret = Return.query.get_or_404(return_id)
    log_audit('delete', 'returns', return_id, eski_deger={'siparis_no': ret.siparis_no})
    db.session.delete(ret)
    db.session.commit()
    return jsonify({'basarili': True, 'mesaj': 'İade silindi'})


@iadeler_bp.route('/api/analizler')
def api_analizler():
    from database import Product, Toplama, Personel
    from sqlalchemy import func

    # En fazla iade edilen ürünler
    urun_iadeleri = db.session.query(
        Product.ana_kod,
        Product.marka,
        func.coalesce(func.sum(Return.adet), 0).label('adet'),
    ).outerjoin(Return, Return.urun_id == Product.id).group_by(Product.id).order_by(func.sum(Return.adet).desc()).limit(10).all()

    # İade nedenleri
    nedenler = db.session.query(
        Return.sebebi,
        func.coalesce(func.sum(Return.adet), 0).label('adet'),
    ).group_by(Return.sebebi).all()

    # Toplama bazlı iadeler
    toplama_iadeleri = db.session.query(
        Toplama.ad.label('toplama'),
        func.coalesce(func.sum(Return.adet), 0).label('adet'),
    ).outerjoin(Return, Return.toplama_id == Toplama.id).group_by(Toplama.id).all()

    return jsonify({
        'basarili': True,
        'urun_iadeleri': [{'kod': r.ana_kod, 'marka': r.marka, 'adet': int(r.adet)} for r in urun_iadeleri],
        'iade_nedenleri': [{'sebep': r.sebebi or 'Belirtilmedi', 'adet': int(r.adet)} for r in nedenler],
        'toplama_iadeleri': [{'toplama': r.toplama, 'adet': int(r.adet)} for r in toplama_iadeleri],
    })


@iadeler_bp.route('/api/gecmis')
def api_gecmis():
    from database import ExcelUpload
    uploads = ExcelUpload.query.filter_by(modul='iade').order_by(ExcelUpload.yukleme_tarihi.desc()).all()
    return jsonify({
        'basarili': True,
        'gecmis': [
            {
                'id': u.id,
                'dosya_adi': u.dosya_adi,
                'yukleme_tarihi': u.yukleme_tarihi.strftime('%Y-%m-%d %H:%M'),
                'toplam_satir': u.toplam_satir,
                'basarili': u.basarili,
                'basarisiz': u.basarisiz,
                'status': u.status,
                'veri_aktarimi_yapildi': u.veri_aktarimi_yapildi,
                'hata_sebebi': u.hata_sebebi,
            }
            for u in uploads
        ],
    })


@iadeler_bp.route('/api/list')
def api_list():
    page = max(int(request.args.get('page', 1)), 1)
    per_page = min(max(int(request.args.get('per_page', 20)), 1), 100)
    pagination = Return.query.order_by(Return.id.desc()).paginate(page=page, per_page=per_page, error_out=False)

    rows = []
    for item in pagination.items:
        rows.append({
            'id': item.id,
            'siparis_no': item.siparis_no,
            'tarih': item.tarih.strftime('%Y-%m-%d'),
            'urun_kodu': item.urun.ana_kod if item.urun else None,
            'beden': item.beden,
            'adet': item.adet,
            'sebep': item.sebebi,
            'toplama': item.toplama.ad if item.toplama else None,
        })

    return jsonify({'basarili': True, 'kayitlar': rows, 'toplam': pagination.total})
