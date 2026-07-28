# -*- coding: utf-8 -*-
"""
Toplamalar Rotaları
"""

from datetime import datetime
from flask import Blueprint, render_template, request, jsonify, send_file
from database import db, Toplama, Product, Size, Personel, Order, toplama_ekle, toplama_sil
from routes.excel_handler import match_product_by_code
from utils.excel_utils import build_template, load_excel_rows
from utils.audit_utils import log_audit



toplamalar_bp = Blueprint('toplamalar', __name__, url_prefix='/toplamalar')


@toplamalar_bp.route('/')
def lista():
    """Toplamalar listesi"""
    toplamalar = Toplama.query.all()
    return render_template('toplamalar.html', toplamalar=toplamalar)


@toplamalar_bp.route('/api/list', methods=['GET'])
def api_list():
    """AJAX ile toplamaları getir"""
    toplamalar = Toplama.query.all()
    return jsonify({
        'basarili': True,
        'toplamalar': [t.to_dict() for t in toplamalar],
        'toplam': len(toplamalar)
    })


@toplamalar_bp.route('/api/personeller', methods=['GET'])
def api_personeller():
    rows = Personel.query.order_by(Personel.ad.asc()).all()
    return jsonify({'basarili': True, 'personeller': [{'id': p.id, 'ad': p.ad} for p in rows]})


@toplamalar_bp.route('/api/dagitim-list', methods=['GET'])
def api_dagitim_list():
    page = max(int(request.args.get('page', 1)), 1)
    per_page = min(max(int(request.args.get('per_page', 20)), 1), 100)
    toplama_id = request.args.get('toplama_id')
    beden = str(request.args.get('beden', '')).strip()
    adet_tipi = str(request.args.get('adet_tipi', '')).strip()

    query = Order.query

    if toplama_id:
        query = query.filter(Order.toplama_id == int(toplama_id))
    if beden:
        query = query.filter(Order.beden == beden)
    if adet_tipi == 'tek':
        query = query.filter(Order.adet == 1)
    elif adet_tipi == 'cok':
        query = query.filter(Order.adet >= 2)

    pagination = query.order_by(Order.id.desc()).paginate(page=page, per_page=per_page, error_out=False)
    kayitlar = []
    for item in pagination.items:
        kayitlar.append({
            'id': item.id,
            'siparis_no': item.siparis_no,
            'urun_kodu': item.urun.ana_kod if item.urun else None,
            'beden': item.beden,
            'adet': item.adet,
            'toplama': item.toplama.ad if item.toplama else None,
            'toplama_id': item.toplama_id,
            'personel': item.personel.ad if item.personel else None,
            'personel_id': item.personel_id,
            'tarih': item.tarih.strftime('%Y-%m-%d'),
        })

    return jsonify({'basarili': True, 'kayitlar': kayitlar, 'toplam': pagination.total})


@toplamalar_bp.route('/api/dagitim-guncelle/<int:order_id>', methods=['PUT'])
def api_dagitim_guncelle(order_id):
    order = Order.query.get_or_404(order_id)
    data = request.json or {}

    eski = {
        'personel_id': order.personel_id,
        'adet': order.adet,
        'toplama_id': order.toplama_id,
    }

    if 'personel_id' in data:
        personel_id = data.get('personel_id')
        if personel_id in ('', None, 'null'):
            order.personel_id = None
        else:
            personel = Personel.query.get(int(personel_id))
            if not personel:
                return jsonify({'basarili': False, 'mesaj': 'Personel bulunamadı'}), 404
            order.personel_id = personel.id

    if 'adet' in data:
        adet = int(float(data.get('adet') or 0))
        if adet <= 0:
            return jsonify({'basarili': False, 'mesaj': 'Adet 0 veya negatif olamaz'}), 400
        order.adet = adet

    if 'toplama_id' in data:
        toplama = Toplama.query.get(int(data.get('toplama_id')))
        if not toplama:
            return jsonify({'basarili': False, 'mesaj': 'Toplama bulunamadı'}), 404
        order.toplama_id = toplama.id

    log_audit('dagitim_manual_guncelle', 'orders', order.id, eski_deger=eski, yeni_deger={
        'personel_id': order.personel_id,
        'adet': order.adet,
        'toplama_id': order.toplama_id,
    })
    db.session.commit()
    return jsonify({'basarili': True, 'mesaj': 'Dağıtım kaydı güncellendi'})


@toplamalar_bp.route('/api/ogle-template')
def ogle_template():
    headers = ['Siparis No', 'Urun Kodu', 'Beden', 'Adet', 'Personel', 'Toplama']
    stream = build_template(headers)
    return send_file(stream, as_attachment=True, download_name='ogle_toplama_dagitim_template.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@toplamalar_bp.route('/api/ogle-yukle', methods=['POST'])
def ogle_yukle():
    file = request.files.get('file')
    if not file:
        return jsonify({'basarili': False, 'mesaj': 'Dosya zorunludur!'}), 400

    if not (file.filename or '').lower().endswith(('.xlsx', '.xlsm', '.xltx', '.xltm')):
        return jsonify({'basarili': False, 'mesaj': 'Geçersiz dosya formatı!'}), 400

    expected = ['Siparis No', 'Urun Kodu', 'Beden', 'Adet', 'Personel', 'Toplama']

    try:
        headers, rows = load_excel_rows(file)
    except Exception:
        return jsonify({'basarili': False, 'mesaj': 'Excel okunamadı. Dosya formatını kontrol edin.'}), 400

    if headers != expected:
        return jsonify({
            'basarili': False,
            'mesaj': 'Başlıklar hatalı!',
            'beklenen': expected,
            'bulunan': headers,
        }), 400

    basarili = 0
    hatalar = []

    for idx, row in enumerate(rows, start=2):
        try:
            siparis_no = str(row.get('Siparis No', '')).strip()
            urun_kodu = row.get('Urun Kodu')
            beden = str(row.get('Beden', '')).strip() or None
            adet = int(float(row.get('Adet') or 0))

            if not siparis_no or not urun_kodu or adet <= 0:
                hatalar.append({'satir': idx, 'hata': 'Sipariş no, ürün kodu ve adet zorunludur'})
                continue

            product = match_product_by_code(urun_kodu)
            if not product:
                hatalar.append({'satir': idx, 'hata': f'Tanımsız ürün kodu: {urun_kodu}'})
                continue

            toplama_text = str(row.get('Toplama', '')).strip()
            toplama = Toplama.query.filter_by(ad=toplama_text).first() if toplama_text else product.toplama
            if not toplama:
                hatalar.append({'satir': idx, 'hata': f'Toplama bulunamadı: {toplama_text}'})
                continue

            personel_text = str(row.get('Personel', '')).strip()
            personel = Personel.query.filter_by(ad=personel_text).first() if personel_text else None

            order = Order.query.filter_by(
                siparis_no=siparis_no,
                urun_id=product.id,
                beden=beden,
            ).order_by(Order.id.desc()).first()

            if order:
                order.toplama_id = toplama.id
                order.personel_id = personel.id if personel else order.personel_id
                order.adet = adet
                order.durum = 'Öğlen Manuel Dağıtım'
            else:
                order = Order(
                    siparis_no=siparis_no,
                    tarih=datetime.utcnow(),
                    urun_id=product.id,
                    beden=beden,
                    adet=adet,
                    toplama_id=toplama.id,
                    personel_id=personel.id if personel else None,
                    durum='Öğlen Manuel Dağıtım',
                    excel_yukleme_id=None,
                )
                db.session.add(order)

            basarili += 1
        except Exception:
            hatalar.append({'satir': idx, 'hata': 'Satır işlenemedi'})

    log_audit('ogle_manual_dagitim', 'orders', None, yeni_deger={'basarili': basarili, 'hatali': len(hatalar)})
    db.session.commit()

    return jsonify({
        'basarili': True,
        'mesaj': 'Öğlen dağıtım yüklemesi tamamlandı',
        'ozet': {'toplam_satir': len(rows), 'basarili': basarili, 'hatali': len(hatalar)},
        'hatalar': hatalar,
    })


@toplamalar_bp.route('/api/ekle', methods=['POST'])
def api_ekle():
    """AJAX ile toplama ekle"""
    try:
        veri = request.json
        if not veri.get('ad') or veri['ad'].strip() == '':
            return jsonify({'basarili': False, 'mesaj': 'Toplama adı boş olamaz!'}), 400
        sonuc = toplama_ekle(veri['ad'].strip())
        return jsonify(sonuc)
    except Exception as e:
        return jsonify({'basarili': False, 'mesaj': f'Hata: {str(e)}'}), 500


@toplamalar_bp.route('/api/sil/<int:id>', methods=['DELETE'])
def api_sil(id):
    """AJAX ile toplama sil"""
    try:
        sonuc = toplama_sil(id)
        return jsonify(sonuc)
    except Exception as e:
        return jsonify({'basarili': False, 'mesaj': f'Hata: {str(e)}'}), 500


# ── Ürün Yönetimi (Toplama bazında) ─────────────────────────────────────────

@toplamalar_bp.route('/api/<int:toplama_id>/urunler')
def toplama_urunler(toplama_id):
    """Bir toplamanın ürünlerini getir"""
    products = Product.query.filter_by(toplama_id=toplama_id).order_by(Product.ana_kod).all()
    return jsonify({
        'basarili': True,
        'urunler': [p.to_dict() for p in products],
        'toplam': len(products),
    })


@toplamalar_bp.route('/api/<int:toplama_id>/urun-ekle', methods=['POST'])
def toplama_urun_ekle(toplama_id):
    """Toplamaya ürün ekle"""
    Toplama.query.get_or_404(toplama_id)
    data = request.json or {}

    ana_kod = str(data.get('ana_kod', '')).strip().upper()
    marka = str(data.get('marka', '')).strip()
    aciklama = str(data.get('aciklama', '')).strip()

    if not all([ana_kod, marka, aciklama]):
        return jsonify({'basarili': False, 'mesaj': 'Zorunlu alanlar eksik!'}), 400

    if Product.query.filter_by(ana_kod=ana_kod, marka=marka).first():
        return jsonify({'basarili': False, 'mesaj': 'Bu ürün zaten tanımlı!'}), 409

    product = Product(
        ana_kod=ana_kod,
        marka=marka,
        aciklama=aciklama,
        toplama_id=toplama_id,
        beden_ayrimi=bool(data.get('beden_ayrimi', False)),
        durum=True,
        guncelleyen_kullanici='system',
    )
    db.session.add(product)
    db.session.flush()

    for beden_str in data.get('bedenler', []):
        b = str(beden_str).strip()
        if b:
            db.session.add(Size(product_id=product.id, beden=b, toplama_id=toplama_id))

    log_audit('create', 'products', product.id, yeni_deger=product.to_dict())
    db.session.commit()
    return jsonify({'basarili': True, 'mesaj': 'Ürün eklendi', 'id': product.id})


@toplamalar_bp.route('/api/urun/<int:product_id>', methods=['PUT'])
def toplama_urun_guncelle(product_id):
    """Ürün güncelle"""
    product = Product.query.get_or_404(product_id)
    data = request.json or {}
    eski = product.to_dict()

    if 'aciklama' in data:
        product.aciklama = str(data['aciklama'] or '').strip()
    if 'marka' in data:
        product.marka = str(data['marka'] or '').strip()
    if 'beden_ayrimi' in data:
        product.beden_ayrimi = bool(data['beden_ayrimi'])
    if 'durum' in data:
        product.durum = bool(data['durum'])

    product.guncelleyen_kullanici = 'system'
    log_audit('update', 'products', product.id, eski_deger=eski, yeni_deger=product.to_dict())
    db.session.commit()
    return jsonify({'basarili': True, 'mesaj': 'Ürün güncellendi'})


@toplamalar_bp.route('/api/urun/<int:product_id>', methods=['DELETE'])
def toplama_urun_sil(product_id):
    """Ürün sil"""
    product = Product.query.get_or_404(product_id)
    eski = product.to_dict()
    db.session.delete(product)
    log_audit('delete', 'products', product_id, eski_deger=eski)
    db.session.commit()
    return jsonify({'basarili': True, 'mesaj': 'Ürün silindi'})


@toplamalar_bp.route('/api/<int:toplama_id>/template')
def toplama_template(toplama_id):
    """Toplama ürün şablonunu indir"""
    headers = ['Urun Kodu', 'Marka', 'Aciklama', 'Beden Ayrimi', 'Bedenler']
    stream = build_template(headers)
    return send_file(
        stream,
        as_attachment=True,
        download_name=f'toplama_{toplama_id}_urun_sablonu.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )


@toplamalar_bp.route('/api/<int:toplama_id>/excel-yukle', methods=['POST'])
def toplama_excel_yukle(toplama_id):
    """Toplamaya Excel ile toplu ürün yükle"""
    Toplama.query.get_or_404(toplama_id)
    file = request.files.get('file')
    if not file:
        return jsonify({'basarili': False, 'mesaj': 'Dosya zorunludur!'}), 400

    if not (file.filename or '').lower().endswith(('.xlsx', '.xlsm', '.xltx', '.xltm')):
        return jsonify({'basarili': False, 'mesaj': 'Geçersiz dosya formatı!'}), 400

    try:
        headers, rows = load_excel_rows(file)
    except Exception:
        return jsonify({'basarili': False, 'mesaj': 'Excel okunamadı. Dosya formatını kontrol edin.'}), 400

    expected = ['Urun Kodu', 'Marka', 'Aciklama', 'Beden Ayrimi', 'Bedenler']
    if headers != expected:
        return jsonify({
            'basarili': False,
            'mesaj': 'Başlıklar hatalı!',
            'beklenen': expected,
            'bulunan': headers,
        }), 400

    basarili = 0
    hatalar = []

    for idx, row in enumerate(rows, start=2):
        try:
            ana_kod = str(row.get('Urun Kodu', '')).strip().upper()
            marka = str(row.get('Marka', '')).strip()
            aciklama = str(row.get('Aciklama', '')).strip()

            if not all([ana_kod, marka, aciklama]):
                hatalar.append({'satir': idx, 'hata': 'Zorunlu alan eksik'})
                continue

            if Product.query.filter_by(ana_kod=ana_kod, marka=marka).first():
                continue

            beden_ayrimi = str(row.get('Beden Ayrimi', '0')).strip().lower() in ('1', 'true', 'evet')
            bedenler_raw = str(row.get('Bedenler', '') or '').strip()
            bedenler = [b.strip() for b in bedenler_raw.split(',') if b.strip()] if bedenler_raw else []

            product = Product(
                ana_kod=ana_kod,
                marka=marka,
                aciklama=aciklama,
                toplama_id=toplama_id,
                beden_ayrimi=beden_ayrimi,
                durum=True,
                guncelleyen_kullanici='excel',
            )
            db.session.add(product)
            db.session.flush()

            for b in bedenler:
                db.session.add(Size(product_id=product.id, beden=b, toplama_id=toplama_id))

            basarili += 1
        except Exception:
            hatalar.append({'satir': idx, 'hata': 'Satır işlenemedi'})

    log_audit('excel_toplu_yukleme', 'products', None, yeni_deger={'toplama_id': toplama_id, 'basarili': basarili})
    db.session.commit()

    return jsonify({
        'basarili': True,
        'mesaj': f'{basarili} ürün eklendi, {len(hatalar)} satır atlandı.',
        'ozet': {'toplam_satir': len(rows), 'basarili': basarili, 'hatali': len(hatalar)},
        'hatalar': hatalar,
    })
