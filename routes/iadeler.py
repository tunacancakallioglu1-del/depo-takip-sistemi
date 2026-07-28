# -*- coding: utf-8 -*-
"""İade yönetimi rotaları"""

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
    basarili = 0

    for row_no, row in enumerate(rows, start=2):
        try:
            product = match_product_by_code(row.get('Urun Kodu'))
            if not product:
                row_errors.append({'satir': row_no, 'hata': 'Tanımsız ürün'})
                continue

            beden = str(row.get('Beden', '')).strip() or None
            toplama_id, beden_error = determine_toplama(product, beden)
            if beden_error:
                row_errors.append({'satir': row_no, 'hata': beden_error})
                continue

            adet = int(float(row.get('Adet') or 0))
            if adet <= 0:
                raise ValueError('Adet 0 veya negatif olamaz')

            ret = Return(
                siparis_no=str(row.get('Siparis No')).strip(),
                tarih=parse_row_date(row.get('Tarih')),
                urun_id=product.id,
                beden=beden,
                adet=adet,
                sebebi=str(row.get('Sebep', '')).strip() or None,
                toplama_id=toplama_id,
                excel_yukleme_id=upload.id,
            )
            db.session.add(ret)
            basarili += 1
        except Exception:
            row_errors.append({'satir': row_no, 'hata': 'Satır işlenemedi'})

    upload.basarili = basarili
    upload.basarisiz = len(row_errors)

    log_audit('excel_yukleme_tamamlandi', 'returns', upload.id, yeni_deger={
        'toplam_satir': len(rows),
        'basarili': basarili,
        'hatali': len(row_errors),
    })
    db.session.commit()

    return jsonify({
        'basarili': True,
        'mesaj': 'İade yükleme tamamlandı',
        'ozet': {
            'toplam_satir': len(rows),
            'islenen_satir': basarili,
            'hatali_satir': len(row_errors),
        },
        'hatalar': row_errors,
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
