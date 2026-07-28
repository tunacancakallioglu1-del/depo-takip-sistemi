# -*- coding: utf-8 -*-
"""Ürün yönetimi rotaları"""

from flask import Blueprint, render_template, request, jsonify, send_file
from database import db, Product, Size, CodeMapping, Toplama
from routes.excel_handler import validate_excel_upload, get_toplama_by_value
from utils.excel_utils import build_template
from utils.audit_utils import log_audit

urunler_bp = Blueprint('urunler', __name__, url_prefix='/urunler')


@urunler_bp.route('/')
def index():
    return render_template('urunler.html')


@urunler_bp.route('/api/list')
def api_list():
    page = max(int(request.args.get('page', 1)), 1)
    per_page = min(max(int(request.args.get('per_page', 20)), 1), 100)
    pagination = Product.query.order_by(Product.id.desc()).paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        'basarili': True,
        'urunler': [p.to_dict() for p in pagination.items],
        'toplam': pagination.total,
        'sayfa': page,
        'toplam_sayfa': pagination.pages,
    })


@urunler_bp.route('/api/ekle', methods=['POST'])
def api_ekle():
    data = request.json or {}
    ana_kod = str(data.get('ana_kod', '')).strip().upper()
    marka = str(data.get('marka', '')).strip()
    aciklama = str(data.get('aciklama', '')).strip()
    toplama_id = data.get('toplama_id')

    if not all([ana_kod, marka, aciklama, toplama_id]):
        return jsonify({'basarili': False, 'mesaj': 'Zorunlu alanlar eksik!'}), 400

    if Product.query.filter_by(ana_kod=ana_kod, marka=marka).first():
        return jsonify({'basarili': False, 'mesaj': 'Ürün zaten tanımlı!'}), 409

    product = Product(
        ana_kod=ana_kod,
        marka=marka,
        aciklama=aciklama,
        toplama_id=int(toplama_id),
        beden_ayrimi=bool(data.get('beden_ayrimi', False)),
        durum=bool(data.get('durum', True)),
        guncelleyen_kullanici='system',
    )
    db.session.add(product)
    db.session.flush()

    for size_row in data.get('bedenler', []):
        beden = str(size_row.get('beden', '')).strip()
        size_toplama_id = size_row.get('toplama_id')
        if beden and size_toplama_id:
            db.session.add(Size(product_id=product.id, beden=beden, toplama_id=int(size_toplama_id)))

    for map_code in data.get('kod_eslestirmeleri', []):
        kaynak = str(map_code).strip().upper()
        if kaynak:
            db.session.add(CodeMapping(kaynak_kod=kaynak, hedef_urun_id=product.id))

    log_audit('create', 'products', product.id, yeni_deger=product.to_dict())
    db.session.commit()
    return jsonify({'basarili': True, 'mesaj': 'Ürün eklendi', 'id': product.id})


@urunler_bp.route('/api/<int:product_id>', methods=['PUT'])
def api_guncelle(product_id):
    product = Product.query.get_or_404(product_id)
    data = request.json or {}
    eski = product.to_dict()

    if 'aciklama' in data:
        product.aciklama = str(data.get('aciklama') or '').strip()
    if 'toplama_id' in data and data.get('toplama_id'):
        product.toplama_id = int(data['toplama_id'])
    if 'beden_ayrimi' in data:
        product.beden_ayrimi = bool(data['beden_ayrimi'])
    if 'durum' in data:
        product.durum = bool(data['durum'])

    product.guncelleyen_kullanici = 'system'
    log_audit('update', 'products', product.id, eski_deger=eski, yeni_deger=product.to_dict())
    db.session.commit()
    return jsonify({'basarili': True, 'mesaj': 'Ürün güncellendi'})


@urunler_bp.route('/api/<int:product_id>', methods=['DELETE'])
def api_sil(product_id):
    product = Product.query.get_or_404(product_id)
    eski = product.to_dict()
    db.session.delete(product)
    log_audit('delete', 'products', product_id, eski_deger=eski)
    db.session.commit()
    return jsonify({'basarili': True, 'mesaj': 'Ürün silindi'})


@urunler_bp.route('/api/template')
def download_template():
    headers = ['Ana Kod', 'Marka', 'Aciklama', 'Toplama', 'Beden Ayrimi', 'Durum']
    stream = build_template(headers)
    return send_file(stream, as_attachment=True, download_name='urun_template.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@urunler_bp.route('/api/excel-yukle', methods=['POST'])
def excel_yukle():
    expected_headers = ['Ana Kod', 'Marka', 'Aciklama', 'Toplama', 'Beden Ayrimi', 'Durum']
    required_fields = ['Ana Kod', 'Marka', 'Aciklama', 'Toplama']
    upload, rows, error_response, status = validate_excel_upload(request.files.get('file'), expected_headers, required_fields, 'urun')
    if error_response:
        return error_response, status

    basarili = 0
    hatalar = []

    for idx, row in enumerate(rows, start=2):
        try:
            ana_kod = str(row['Ana Kod']).strip().upper()
            marka = str(row['Marka']).strip()
            aciklama = str(row['Aciklama']).strip()
            toplama = get_toplama_by_value(row['Toplama'])

            if not toplama:
                raise ValueError('Toplama bulunamadı')

            existing = Product.query.filter_by(ana_kod=ana_kod, marka=marka).first()
            if existing:
                continue

            beden_ayrimi = str(row.get('Beden Ayrimi', '0')).strip().lower() in ('1', 'true', 'evet')
            durum = str(row.get('Durum', '1')).strip().lower() not in ('0', 'false', 'pasif')

            product = Product(
                ana_kod=ana_kod,
                marka=marka,
                aciklama=aciklama,
                toplama_id=toplama.id,
                beden_ayrimi=beden_ayrimi,
                durum=durum,
                guncelleyen_kullanici='excel',
            )
            db.session.add(product)
            basarili += 1
        except Exception as exc:
            hatalar.append({'satir': idx, 'hata': str(exc)})

    upload.basarili = basarili
    upload.basarisiz = len(hatalar)
    log_audit('excel_yukleme_tamamlandi', 'excel_uploads', upload.id, yeni_deger={'basarili': basarili, 'basarisiz': len(hatalar)})
    db.session.commit()

    return jsonify({
        'basarili': True,
        'mesaj': 'Yükleme tamamlandı',
        'ozet': {'toplam_satir': len(rows), 'basarili': basarili, 'hatali': len(hatalar)},
        'hatalar': hatalar,
    })
