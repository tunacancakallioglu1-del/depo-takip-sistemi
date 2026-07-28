# -*- coding: utf-8 -*-
"""İade yönetimi rotaları"""

import json
from datetime import datetime
from io import BytesIO
import pandas as pd
from flask import Blueprint, render_template, request, jsonify, send_file
from database import db, Return, Toplama, Product, AuditLog
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
    toplamalar = Toplama.query.order_by(Toplama.ad.asc()).all()
    return render_template('iadeler.html', toplamalar=toplamalar)


def _iade_kontrol_map(return_ids):
    if not return_ids:
        return {}

    ids = [str(i) for i in return_ids]
    logs = AuditLog.query.filter(
        AuditLog.tablo == 'returns_control',
        AuditLog.islem == 'iade_kontrol',
        AuditLog.kayit_id.in_(ids),
    ).order_by(AuditLog.id.desc()).all()

    durumlar = {}
    for log in logs:
        key = int(log.kayit_id)
        if key in durumlar:
            continue
        try:
            payload = json.loads(log.yeni_deger) if log.yeni_deger else {}
        except Exception:
            payload = {}
        durumlar[key] = {
            'durum': payload.get('durum', 'Kontrol Edilmedi'),
            'hata_sebebi': payload.get('hata_sebebi', ''),
        }
    return durumlar


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

    log_audit('excel_tanimsiz_rapor', 'excel_uploads', f'iade:{upload.id}', yeni_deger={
        'tanimsiz_urunler': undefined_products,
        'tanimsiz_bedenler': undefined_sizes,
    })

    log_audit('excel_yukleme_tamamlandi', 'returns', upload.id, yeni_deger={
        'toplam_satir': len(rows),
        'basarili': basarili,
        'hatali': len(row_errors),
    })
    db.session.commit()

    return jsonify({
        'basarili': True,
        'mesaj': 'İade yükleme tamamlandı',
        'upload_id': upload.id,
        'ozet': {
            'toplam_satir': len(rows),
            'islenen_satir': basarili,
            'hatali_satir': len(row_errors),
            'tanimsiz_urun': len(undefined_products),
            'tanimsiz_beden': len(undefined_sizes),
        },
        'tanimsiz_urunler': undefined_products,
        'tanimsiz_bedenler': undefined_sizes,
        'hatalar': row_errors,
    })


@iadeler_bp.route('/api/manual-ekle', methods=['POST'])
def api_manual_ekle():
    data = request.json or {}

    siparis_no = str(data.get('siparis_no', '')).strip()
    urun_kodu = str(data.get('urun_kodu', '')).strip()
    beden = str(data.get('beden', '')).strip() or None
    adet = int(float(data.get('adet') or 0))

    if not siparis_no or not urun_kodu or adet <= 0:
        return jsonify({'basarili': False, 'mesaj': 'Sipariş no, ürün kodu ve adet zorunludur'}), 400

    product = match_product_by_code(urun_kodu)
    if not product:
        return jsonify({'basarili': False, 'mesaj': 'Tanımsız ürün kodu'}), 400

    toplama_id, beden_error = determine_toplama(product, beden)
    if beden_error:
        return jsonify({'basarili': False, 'mesaj': beden_error}), 400

    tarih_text = str(data.get('tarih', '')).strip()
    if tarih_text:
        try:
            tarih = datetime.strptime(tarih_text, '%Y-%m-%d')
        except ValueError:
            return jsonify({'basarili': False, 'mesaj': 'Tarih formatı hatalı'}), 400
    else:
        tarih = datetime.utcnow()

    ret = Return(
        siparis_no=siparis_no,
        tarih=tarih,
        urun_id=product.id,
        beden=beden,
        adet=adet,
        sebebi=str(data.get('sebebi', '')).strip() or None,
        toplama_id=toplama_id,
        excel_yukleme_id=None,
    )
    db.session.add(ret)
    db.session.commit()

    log_audit('manual_create', 'returns', ret.id, yeni_deger={'siparis_no': ret.siparis_no, 'adet': ret.adet})
    return jsonify({'basarili': True, 'mesaj': 'İade kaydı eklendi'})


@iadeler_bp.route('/api/<int:return_id>/kontrol', methods=['PUT'])
def api_kontrol_durumu(return_id):
    Return.query.get_or_404(return_id)
    data = request.json or {}

    durum = str(data.get('durum', 'Kontrol Edilmedi')).strip()
    if durum not in ('Kontrol Edildi', 'Kontrol Edilmedi'):
        return jsonify({'basarili': False, 'mesaj': 'Geçersiz kontrol durumu'}), 400

    hata_sebebi = str(data.get('hata_sebebi', '')).strip()
    log_audit('iade_kontrol', 'returns_control', return_id, yeni_deger={
        'durum': durum,
        'hata_sebebi': hata_sebebi,
    })
    db.session.commit()
    return jsonify({'basarili': True, 'mesaj': 'Kontrol durumu güncellendi'})


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
    from sqlalchemy import func

    urun_iadeleri = db.session.query(
        Product.ana_kod,
        Product.marka,
        func.coalesce(func.sum(Return.adet), 0).label('adet'),
    ).outerjoin(Return, Return.urun_id == Product.id).group_by(Product.id).order_by(func.sum(Return.adet).desc()).limit(10).all()

    nedenler = db.session.query(
        Return.sebebi,
        func.coalesce(func.sum(Return.adet), 0).label('adet'),
    ).group_by(Return.sebebi).all()

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
            }
            for u in uploads
        ],
    })


@iadeler_bp.route('/api/<int:return_id>/yeniden-yukle-excel')
def api_yeniden_yukle_excel(return_id):
    ret = Return.query.get_or_404(return_id)
    row = {
        'Siparis No': ret.siparis_no,
        'Tarih': ret.tarih.strftime('%Y-%m-%d'),
        'Urun Kodu': ret.urun.ana_kod if ret.urun else '',
        'Beden': ret.beden or '',
        'Adet': ret.adet,
        'Sebep': ret.sebebi or '',
    }

    out = BytesIO()
    with pd.ExcelWriter(out, engine='openpyxl') as writer:
        pd.DataFrame([row]).to_excel(writer, index=False, sheet_name='IadeTekrarYukleme')
    out.seek(0)

    return send_file(
        out,
        as_attachment=True,
        download_name=f'iade_{ret.id}_tekrar_yukleme.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )


@iadeler_bp.route('/api/list')
def api_list():
    page = max(int(request.args.get('page', 1)), 1)
    per_page = min(max(int(request.args.get('per_page', 20)), 1), 100)
    beden = str(request.args.get('beden', '')).strip()
    adet_tipi = str(request.args.get('adet_tipi', '')).strip()
    toplama_id = request.args.get('toplama_id')

    query = Return.query
    if beden:
        query = query.filter(Return.beden == beden)
    if toplama_id:
        query = query.filter(Return.toplama_id == int(toplama_id))
    if adet_tipi == 'tek':
        query = query.filter(Return.adet == 1)
    elif adet_tipi == 'cok':
        query = query.filter(Return.adet >= 2)

    pagination = query.order_by(Return.id.desc()).paginate(page=page, per_page=per_page, error_out=False)
    return_ids = [item.id for item in pagination.items]
    kontrol_map = _iade_kontrol_map(return_ids)

    rows = []
    for item in pagination.items:
        kontrol = kontrol_map.get(item.id, {'durum': 'Kontrol Edilmedi', 'hata_sebebi': ''})
        rows.append({
            'id': item.id,
            'siparis_no': item.siparis_no,
            'tarih': item.tarih.strftime('%Y-%m-%d'),
            'urun_kodu': item.urun.ana_kod if item.urun else None,
            'beden': item.beden,
            'adet': item.adet,
            'sebep': item.sebebi,
            'toplama': item.toplama.ad if item.toplama else None,
            'kontrol_durumu': kontrol['durum'],
            'hata_sebebi': kontrol['hata_sebebi'],
        })

    return jsonify({'basarili': True, 'kayitlar': rows, 'toplam': pagination.total})
