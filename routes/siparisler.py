# -*- coding: utf-8 -*-
"""Sipariş yönetimi rotaları"""

from collections import defaultdict
from flask import Blueprint, render_template, request, jsonify, send_file
from database import db, Order, Personel, Kayit
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


@siparisler_bp.route('/api/personeller')
def api_personeller():
    rows = Personel.query.order_by(Personel.ad.asc()).all()
    return jsonify({
        'basarili': True,
        'personeller': [{'id': p.id, 'ad': p.ad} for p in rows],
    })


@siparisler_bp.route('/api/template')
def download_template():
    headers = ['Siparis No', 'Tarih', 'Urun Kodu', 'Beden', 'Adet', 'Kargo Kodu', 'Termin Tarihi', 'Personel']
    stream = build_template(headers)
    return send_file(stream, as_attachment=True, download_name='siparis_template.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


def _format_kayit_tarih(dt_obj):
    return dt_obj.strftime('%d.%m.%Y')


def _otomatik_kayit_aktar(aktarim_kaynaklari):
    ozet = {'olusturulan': 0, 'guncellenen': 0}
    gruplu = defaultdict(lambda: {'siparis_set': set(), 'adet': 0})

    for kayit in aktarim_kaynaklari:
        tarih = _format_kayit_tarih(kayit['tarih'])
        personel_id = kayit['personel_id']
        toplama_id = kayit['toplama_id']
        if not personel_id or not toplama_id:
            continue

        anahtar = (tarih, personel_id, toplama_id)
        gruplu[anahtar]['siparis_set'].add(kayit['siparis_no'])
        gruplu[anahtar]['adet'] += kayit['adet']

    for (tarih, personel_id, toplama_id), veri in gruplu.items():
        kayit = Kayit.query.filter_by(tarih=tarih, personel_id=personel_id, toplama_id=toplama_id).first()
        siparis_adedi = len(veri['siparis_set'])
        urun_adedi = veri['adet']

        if kayit:
            kayit.trendyol_siparis = float(siparis_adedi)
            kayit.trendyol_fatura = float(urun_adedi)
            ozet['guncellenen'] += 1
        else:
            yeni = Kayit(
                tarih=tarih,
                personel_id=personel_id,
                toplama_id=toplama_id,
                trendyol_siparis=float(siparis_adedi),
                trendyol_fatura=float(urun_adedi),
                diger_pazar=0,
                not_alan='Siparişten otomatik aktarıldı',
            )
            db.session.add(yeni)
            ozet['olusturulan'] += 1

    return ozet


@siparisler_bp.route('/api/excel-yukle', methods=['POST'])
def excel_yukle():
    expected_headers = ['Siparis No', 'Tarih', 'Urun Kodu', 'Beden', 'Adet', 'Kargo Kodu', 'Termin Tarihi', 'Personel']
    required_fields = ['Siparis No', 'Urun Kodu', 'Adet']
    upload, rows, error_response, status = validate_excel_upload(request.files.get('file'), expected_headers, required_fields, 'siparis')
    if error_response:
        return error_response, status

    yukleme_tipi = str(request.form.get('yukleme_tipi', 'sabah')).strip().lower()
    if yukleme_tipi not in ('sabah', 'ogle'):
        yukleme_tipi = 'sabah'

    undefined_products = []
    undefined_sizes = []
    row_errors = []
    basarili = 0
    unique_orders = set()
    order_toplama = {}
    aktarim_kaynaklari = []

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
                durum='Yüklendi' if yukleme_tipi == 'sabah' else 'Öğlen Güncellendi',
                excel_yukleme_id=upload.id,
            )
            db.session.add(order)
            basarili += 1
            unique_orders.add(siparis_no)

            aktarim_kaynaklari.append({
                'tarih': order.tarih,
                'siparis_no': siparis_no,
                'adet': adet,
                'personel_id': order.personel_id,
                'toplama_id': toplama_id,
            })
        except Exception:
            row_errors.append({'satir': row_no, 'hata': 'Satır işlenemedi'})

    upload.basarili = basarili
    upload.basarisiz = len(row_errors)

    aktarim_ozet = _otomatik_kayit_aktar(aktarim_kaynaklari)

    log_audit('excel_tanimsiz_rapor', 'excel_uploads', f'siparis:{upload.id}', yeni_deger={
        'tanimsiz_urunler': undefined_products,
        'tanimsiz_bedenler': undefined_sizes,
    })

    log_audit('excel_yukleme_tamamlandi', 'orders', upload.id, yeni_deger={
        'toplam_satir': len(rows),
        'basarili': basarili,
        'hatali': len(row_errors),
        'tekil_siparis': len(unique_orders),
        'yukleme_tipi': yukleme_tipi,
        'kayit_aktarim': aktarim_ozet,
    })
    db.session.commit()

    return jsonify({
        'basarili': True,
        'mesaj': 'Sipariş yükleme tamamlandı',
        'upload_id': upload.id,
        'ozet': {
            'toplam_satir': len(rows),
            'tekil_siparis': len(unique_orders),
            'islenen_satir': basarili,
            'hatali_satir': len(row_errors),
            'tanimsiz_urun': len(undefined_products),
            'tanimsiz_beden': len(undefined_sizes),
            'otomatik_kayit_olusturulan': aktarim_ozet['olusturulan'],
            'otomatik_kayit_guncellenen': aktarim_ozet['guncellenen'],
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
        'personel_id': order.personel_id,
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
    if 'personel_id' in data:
        personel_id = data.get('personel_id')
        if personel_id in (None, '', 'null'):
            order.personel_id = None
        else:
            personel = Personel.query.get(int(personel_id))
            if not personel:
                return jsonify({'basarili': False, 'mesaj': 'Personel bulunamadı'}), 404
            order.personel_id = personel.id

    log_audit('update', 'orders', order_id, eski_deger=eski, yeni_deger={
        'beden': order.beden,
        'adet': order.adet,
        'durum': order.durum,
        'personel_id': order.personel_id,
    })
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
            }
            for u in uploads
        ],
    })


@siparisler_bp.route('/api/list')
def api_list():
    page = max(int(request.args.get('page', 1)), 1)
    per_page = min(max(int(request.args.get('per_page', 20)), 1), 100)
    siparis_no = str(request.args.get('siparis_no', '')).strip()

    query = Order.query
    if siparis_no:
        query = query.filter(Order.siparis_no.ilike(f'%{siparis_no}%'))

    pagination = query.order_by(Order.id.desc()).paginate(page=page, per_page=per_page, error_out=False)

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
            'personel_id': item.personel_id,
            'durum': item.durum,
        })

    return jsonify({'basarili': True, 'kayitlar': rows, 'toplam': pagination.total})
