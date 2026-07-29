# -*- coding: utf-8 -*-
"""Ürün yönetimi rotaları"""

from flask import Blueprint, render_template, request, jsonify, send_file
from sqlalchemy import or_

from database import db, Product, Size, CodeMapping, Toplama, Order
from routes.excel_handler import validate_excel_upload, get_toplama_by_value, determine_toplama
from utils.excel_utils import build_template
from utils.audit_utils import log_audit

urunler_bp = Blueprint('urunler', __name__, url_prefix='/urunler')


def _parse_bedenler(raw_bedenler):
    if not raw_bedenler:
        return []
    if isinstance(raw_bedenler, list):
        values = raw_bedenler
    else:
        values = str(raw_bedenler).split(',')

    bedenler = []
    seen = set()
    for value in values:
        beden = str(value or '').strip().upper()
        if beden and beden not in seen:
            bedenler.append(beden)
            seen.add(beden)
    return bedenler


def _sync_sizes(product, bedenler):
    Size.query.filter_by(product_id=product.id).delete(synchronize_session=False)
    for beden in bedenler:
        db.session.add(Size(product_id=product.id, beden=beden, toplama_id=product.toplama_id))


def _check_product_orders(product):
    eslesen_kodlar = [product.ana_kod]
    eslesen_kodlar.extend(
        mapping.kaynak_kod for mapping in product.code_mappings if mapping.kaynak_kod
    )

    hatali_siparisler = Order.query.filter(
        Order.durum == 'HATALI',
        Order.urun_id.is_(None),
        Order.urun_kodu_ham.in_(eslesen_kodlar),
    ).all()

    duzeltilen = 0
    for siparis in hatali_siparisler:
        siparis.urun_id = product.id
        toplama_id, beden_hatasi = determine_toplama(product, siparis.beden)

        errors = []
        if beden_hatasi:
            errors.append(beden_hatasi)
        elif toplama_id:
            siparis.toplama_id = toplama_id

        if not siparis.siparis_no:
            errors.append('Sipariş No boş')
        if not siparis.tarih:
            errors.append('Tarih boş')
        if int(siparis.adet or 0) <= 0:
            errors.append('Adet ≤ 0')
        if not siparis.toplama_id:
            errors.append('Toplama seçilmemiş')

        if errors:
            siparis.durum = 'HATALI'
            siparis.hata_sebebi = '; '.join(errors)
            continue

        siparis.durum = 'BEKLEMEDE'
        siparis.hata_sebebi = None
        duzeltilen += 1

    return duzeltilen


@urunler_bp.route('/')
def index():
    return render_template('urunler.html')


@urunler_bp.route('/api/list')
def api_list():
    page = max(int(request.args.get('page', 1)), 1)
    per_page = min(max(int(request.args.get('per_page', 20)), 1), 100)
    kod = str(request.args.get('kod', '')).strip().upper()
    query = Product.query
    if kod:
        query = query.filter(Product.ana_kod.ilike(f'%{kod}%'))

    pagination = query.order_by(Product.id.desc()).paginate(page=page, per_page=per_page, error_out=False)

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
    toplama = get_toplama_by_value(data.get('toplama_id') or data.get('toplama'))
    bedenler = _parse_bedenler(data.get('bedenler'))

    if not all([ana_kod, marka, aciklama, toplama]):
        return jsonify({'basarili': False, 'mesaj': 'Zorunlu alanlar eksik!'}), 400

    product = Product.query.filter_by(ana_kod=ana_kod).first()
    durum_mesaji = 'Ürün güncellendi'
    duzeltilen = 0

    if product:
        eski = product.to_dict()
        product.marka = marka
        product.aciklama = aciklama
        product.toplama_id = toplama.id
        product.beden_ayrimi = bool(data.get('beden_ayrimi', False))
        product.durum = bool(data.get('durum', True))
        product.guncelleyen_kullanici = 'system'
        log_audit('update', 'products', product.id, eski_deger=eski, yeni_deger=product.to_dict())
    else:
        product = Product(
            ana_kod=ana_kod,
            marka=marka,
            aciklama=aciklama,
            toplama_id=toplama.id,
            beden_ayrimi=bool(data.get('beden_ayrimi', False)),
            durum=bool(data.get('durum', True)),
            guncelleyen_kullanici='system',
        )
        db.session.add(product)
        db.session.flush()
        log_audit('create', 'products', product.id, yeni_deger=product.to_dict())
        durum_mesaji = 'Ürün eklendi'

    if bedenler:
        product.beden_ayrimi = True
    _sync_sizes(product, bedenler)

    for map_code in data.get('kod_eslestirmeleri', []):
        kaynak = str(map_code).strip().upper()
        if kaynak:
            mevcut_map = CodeMapping.query.filter_by(kaynak_kod=kaynak).first()
            if mevcut_map:
                mevcut_map.hedef_urun_id = product.id
            else:
                db.session.add(CodeMapping(kaynak_kod=kaynak, hedef_urun_id=product.id))

    duzeltilen = _check_product_orders(product)
    db.session.commit()
    return jsonify({
        'basarili': True,
        'mesaj': durum_mesaji,
        'id': product.id,
        'hatali_duzeltilen': duzeltilen,
    })


@urunler_bp.route('/api/<int:product_id>', methods=['PUT'])
def api_guncelle(product_id):
    product = Product.query.get_or_404(product_id)
    data = request.json or {}
    eski = product.to_dict()
    bedenler = _parse_bedenler(data.get('bedenler'))
    toplama = None
    if 'toplama_id' in data or 'toplama' in data:
        toplama = get_toplama_by_value(data.get('toplama_id') or data.get('toplama'))

    if 'marka' in data:
        product.marka = str(data.get('marka') or '').strip()
    if 'aciklama' in data:
        product.aciklama = str(data.get('aciklama') or '').strip()
    if toplama:
        product.toplama_id = toplama.id
    if 'beden_ayrimi' in data:
        product.beden_ayrimi = bool(data['beden_ayrimi'])
    if 'durum' in data:
        product.durum = bool(data['durum'])

    if 'bedenler' in data or bedenler:
        if bedenler:
            product.beden_ayrimi = True
        _sync_sizes(product, bedenler)

    product.guncelleyen_kullanici = 'system'
    log_audit('update', 'products', product.id, eski_deger=eski, yeni_deger=product.to_dict())
    duzeltilen = _check_product_orders(product)
    db.session.commit()
    return jsonify({'basarili': True, 'mesaj': 'Ürün güncellendi', 'hatali_duzeltilen': duzeltilen})


@urunler_bp.route('/api/<int:product_id>', methods=['DELETE'])
def api_sil(product_id):
    product = Product.query.get_or_404(product_id)
    siparis_var = Order.query.filter(
        or_(
            Order.urun_id == product.id,
            Order.urun_kodu_ham == product.ana_kod,
        )
    ).first()
    if siparis_var:
        return jsonify({'basarili': False, 'mesaj': 'Bu ürün siparişlerde kullanılıyor, silinemez!'}), 409

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
        except Exception:
            hatalar.append({'satir': idx, 'hata': 'Satır işlenemedi'})

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
