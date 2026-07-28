# -*- coding: utf-8 -*-
"""Sipariş yönetimi rotaları"""

from flask import Blueprint, render_template, request, jsonify, send_file
from database import db, Order, Personel
from routes.excel_handler import (
    validate_excel_upload,
    match_product_by_code,
    determine_toplama,
    parse_row_date,
)
from utils.excel_utils import build_template
from utils.audit_utils import log_audit

siparisler_bp = Blueprint('siparisler', __name__, url_prefix='/siparisler')


@siparisler_bp.route('/')
def index():
    return render_template('siparisler.html')


@siparisler_bp.route('/api/template')
def download_template():
    headers = ['Siparis No', 'Tarih', 'Urun Kodu', 'Beden', 'Adet', 'Kargo Kodu', 'Termin Tarihi', 'Personel']
    stream = build_template(headers)
    return send_file(stream, as_attachment=True, download_name='siparis_template.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@siparisler_bp.route('/api/excel-yukle', methods=['POST'])
def excel_yukle():
    expected_headers = ['Siparis No', 'Tarih', 'Urun Kodu', 'Beden', 'Adet', 'Kargo Kodu', 'Termin Tarihi', 'Personel']
    required_fields = ['Siparis No', 'Urun Kodu', 'Adet']
    upload, rows, error_response, status = validate_excel_upload(request.files.get('file'), expected_headers, required_fields, 'siparis')
    if error_response:
        return error_response, status

    undefined_products = []
    undefined_sizes = []
    row_errors = []
    basarili = 0
    unique_orders = set()
    order_toplama = {}

    for row_no, row in enumerate(rows, start=2):
        siparis_no = str(row.get('Siparis No', '')).strip()
        urun_kodu = row.get('Urun Kodu')
        beden = str(row.get('Beden', '')).strip() or None

        try:
            product = match_product_by_code(urun_kodu)
            if not product:
                undefined_products.append({'satir': row_no, 'kod': str(urun_kodu)})
                row_errors.append({'satir': row_no, 'hata': 'Tanımsız ürün'})
                continue

            toplama_id, beden_error = determine_toplama(product, beden)
            if beden_error:
                undefined_sizes.append({'satir': row_no, 'kod': product.ana_kod, 'beden': beden})
                row_errors.append({'satir': row_no, 'hata': beden_error})
                continue

            # Kritik kural: sipariş toplama alanı ilk satıra göre sabitlenir
            if siparis_no not in order_toplama:
                order_toplama[siparis_no] = toplama_id
            toplama_id = order_toplama[siparis_no]

            adet = int(float(row.get('Adet') or 0))
            if adet <= 0:
                raise ValueError('Adet 0 veya negatif olamaz')

            personel_adi = str(row.get('Personel', '')).strip()
            personel = Personel.query.filter_by(ad=personel_adi).first() if personel_adi else None

            order = Order(
                siparis_no=siparis_no,
                tarih=parse_row_date(row.get('Tarih')),
                urun_id=product.id,
                beden=beden,
                adet=adet,
                toplama_id=toplama_id,
                personel_id=personel.id if personel else None,
                kargo_kodu=str(row.get('Kargo Kodu', '')).strip() or None,
                termin_tarihi=parse_row_date(row.get('Termin Tarihi')).date() if row.get('Termin Tarihi') else None,
                durum='Yüklendi',
                excel_yukleme_id=upload.id,
            )
            db.session.add(order)
            basarili += 1
            unique_orders.add(siparis_no)
        except Exception:
            row_errors.append({'satir': row_no, 'hata': 'Satır işlenemedi'})

    upload.basarili = basarili
    upload.basarisiz = len(row_errors)

    log_audit('excel_yukleme_tamamlandi', 'orders', upload.id, yeni_deger={
        'toplam_satir': len(rows),
        'basarili': basarili,
        'hatali': len(row_errors),
        'tekil_siparis': len(unique_orders),
    })
    db.session.commit()

    return jsonify({
        'basarili': True,
        'mesaj': 'Sipariş yükleme tamamlandı',
        'ozet': {
            'toplam_satir': len(rows),
            'tekil_siparis': len(unique_orders),
            'islenen_satir': basarili,
            'hatali_satir': len(row_errors),
            'tanimsiz_urun': len(undefined_products),
            'tanimsiz_beden': len(undefined_sizes),
        },
        'tanimsiz_urunler': undefined_products,
        'tanimsiz_bedenler': undefined_sizes,
        'hatalar': row_errors,
    })


@siparisler_bp.route('/api/<int:order_id>', methods=['PUT'])
def api_guncelle(order_id):
    order = Order.query.get_or_404(order_id)
    data = request.json or {}
    eski = {
        'siparis_no': order.siparis_no,
        'beden': order.beden,
        'adet': order.adet,
        'durum': order.durum,
    }

    if 'beden' in data:
        order.beden = str(data['beden'] or '').strip() or None
    if 'adet' in data:
        adet = int(float(data['adet'] or 0))
        if adet <= 0:
            return jsonify({'basarili': False, 'mesaj': 'Adet 0 veya negatif olamaz'}), 400
        order.adet = adet
    if 'durum' in data:
        order.durum = str(data['durum']).strip()

    log_audit('update', 'orders', order_id, eski_deger=eski, yeni_deger={'beden': order.beden, 'adet': order.adet, 'durum': order.durum})
    db.session.commit()
    return jsonify({'basarili': True, 'mesaj': 'Sipariş güncellendi'})


@siparisler_bp.route('/api/<int:order_id>', methods=['DELETE'])
def api_sil(order_id):
    order = Order.query.get_or_404(order_id)
    log_audit('delete', 'orders', order_id, eski_deger={'siparis_no': order.siparis_no})
    db.session.delete(order)
    db.session.commit()
    return jsonify({'basarili': True, 'mesaj': 'Sipariş silindi'})


@siparisler_bp.route('/api/gecmis')
def api_gecmis():
    from database import ExcelUpload
    uploads = ExcelUpload.query.filter_by(modul='siparis').order_by(ExcelUpload.yukleme_tarihi.desc()).all()
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
                'durum': u.durum,
                'kontrol_tarihi': u.kontrol_tarihi.strftime('%Y-%m-%d %H:%M') if u.kontrol_tarihi else None,
            }
            for u in uploads
        ],
    })


@siparisler_bp.route('/api/kontrol-edildi/<int:upload_id>', methods=['POST'])
def kontrol_edildi(upload_id):
    """Yüklemeyi kontrol edildi olarak işaretle ve senkronizasyonu tetikle"""
    from database import ExcelUpload, Kayit, Order
    from datetime import datetime

    upload = ExcelUpload.query.get_or_404(upload_id)

    if upload.durum == 'KONTROL_EDILDI':
        return jsonify({'basarili': False, 'mesaj': 'Bu yükleme zaten kontrol edildi!'})

    if upload.modul != 'siparis':
        return jsonify({'basarili': False, 'mesaj': 'Geçersiz modül!'})

    try:
        # Kontrol edildi olarak işaretle
        upload.durum = 'KONTROL_EDILDI'
        upload.kontrol_tarihi = datetime.now()
        db.session.commit()

        # Senkronizasyonu başlat
        from routes.kayitlar import _senkronize_upload
        sonuc = _senkronize_upload(upload_id)

        log_audit('kontrol_edildi', 'excel_uploads', upload_id, yeni_deger={'durum': 'KONTROL_EDILDI', 'senkronizasyon': sonuc})

        return jsonify({
            'basarili': True,
            'mesaj': f'Kontrol edildi. {sonuc["mesaj"]}',
            'senkronizasyon': sonuc,
        })

    except Exception:
        db.session.rollback()
        return jsonify({'basarili': False, 'mesaj': 'İşlem sırasında bir hata oluştu.'}), 500


@siparisler_bp.route('/api/list')
def api_list():
    page = max(int(request.args.get('page', 1)), 1)
    per_page = min(max(int(request.args.get('per_page', 20)), 1), 100)
    pagination = Order.query.order_by(Order.id.desc()).paginate(page=page, per_page=per_page, error_out=False)

    rows = []
    for item in pagination.items:
        rows.append({
            'id': item.id,
            'siparis_no': item.siparis_no,
            'tarih': item.tarih.strftime('%Y-%m-%d'),
            'urun_kodu': item.urun.ana_kod if item.urun else None,
            'beden': item.beden,
            'adet': item.adet,
            'toplama': item.toplama.ad if item.toplama else None,
            'personel': item.personel.ad if item.personel else None,
        })

    return jsonify({'basarili': True, 'kayitlar': rows, 'toplam': pagination.total})
