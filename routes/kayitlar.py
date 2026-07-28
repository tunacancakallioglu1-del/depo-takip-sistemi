# -*- coding: utf-8 -*-
"""
Kayıtlar Rotaları
"""

from flask import Blueprint, render_template, request, jsonify, send_file
from sqlalchemy import func
from database import db, Kayit, Personel, Toplama, Order, kayit_guncelle, kayit_sil
from utils.excel_utils import build_template, load_excel_rows
from utils.audit_utils import log_audit

kayitlar_bp = Blueprint('kayitlar', __name__, url_prefix='/kayitlar')


def _format_tarih(dt_obj):
    return dt_obj.strftime('%d.%m.%Y')


def siparislerden_kayit_senkronize_et():
    """Siparişlerden Trendyol alanlarını otomatik günceller."""
    gruplar = db.session.query(
        func.strftime('%d.%m.%Y', Order.tarih).label('tarih'),
        Order.personel_id,
        Order.toplama_id,
        func.count(func.distinct(Order.siparis_no)).label('siparis_sayisi'),
        func.coalesce(func.sum(Order.adet), 0).label('urun_sayisi'),
    ).filter(
        Order.personel_id.isnot(None),
        Order.toplama_id.isnot(None),
    ).group_by(
        func.strftime('%d.%m.%Y', Order.tarih),
        Order.personel_id,
        Order.toplama_id,
    ).all()

    olusturulan = 0
    guncellenen = 0

    for row in gruplar:
        kayit = Kayit.query.filter_by(
            tarih=row.tarih,
            personel_id=row.personel_id,
            toplama_id=row.toplama_id,
        ).first()

        if kayit:
            kayit.trendyol_siparis = float(row.siparis_sayisi)
            kayit.trendyol_fatura = float(row.urun_sayisi)
            guncellenen += 1
        else:
            yeni = Kayit(
                tarih=row.tarih,
                personel_id=row.personel_id,
                toplama_id=row.toplama_id,
                trendyol_siparis=float(row.siparis_sayisi),
                trendyol_fatura=float(row.urun_sayisi),
                diger_pazar=0,
                not_alan='Siparişlerden otomatik aktarıldı',
            )
            db.session.add(yeni)
            olusturulan += 1

    if olusturulan or guncellenen:
        log_audit('siparis_otomatik_aktarim', 'kayitlar', None, yeni_deger={
            'olusturulan': olusturulan,
            'guncellenen': guncellenen,
        })
        db.session.commit()

    return {'olusturulan': olusturulan, 'guncellenen': guncellenen}


@kayitlar_bp.route('/')
def lista():
    """Kayıtlar listesi"""
    siparislerden_kayit_senkronize_et()
    kayitlar = Kayit.query.order_by(Kayit.tarih.desc()).all()
    personeller = Personel.query.all()
    toplamalar = Toplama.query.all()

    return render_template('kayitlar.html',
                         kayitlar=kayitlar,
                         personeller=personeller,
                         toplamalar=toplamalar)


@kayitlar_bp.route('/api/otomatik-senkronize', methods=['POST'])
def api_otomatik_senkronize():
    sonuc = siparislerden_kayit_senkronize_et()
    return jsonify({'basarili': True, 'mesaj': 'Senkronizasyon tamamlandı', 'ozet': sonuc})


@kayitlar_bp.route('/api/list', methods=['GET'])
def api_list():
    """AJAX ile kayıtları getir"""
    siparislerden_kayit_senkronize_et()

    personel_id = request.args.get('personel_id')
    toplama_id = request.args.get('toplama_id')
    tarih_baslangic = request.args.get('tarih_baslangic')
    tarih_bitis = request.args.get('tarih_bitis')

    sorgu = Kayit.query

    if personel_id:
        sorgu = sorgu.filter_by(personel_id=int(personel_id))

    if toplama_id:
        sorgu = sorgu.filter_by(toplama_id=int(toplama_id))

    if tarih_baslangic:
        sorgu = sorgu.filter(Kayit.tarih >= tarih_baslangic)

    if tarih_bitis:
        sorgu = sorgu.filter(Kayit.tarih <= tarih_bitis)

    kayitlar = sorgu.order_by(Kayit.tarih.desc()).all()

    return jsonify({
        'basarili': True,
        'kayitlar': [k.to_dict() for k in kayitlar],
        'toplam': len(kayitlar)
    })


@kayitlar_bp.route('/api/guncelle/<int:id>', methods=['PUT'])
def api_guncelle(id):
    """AJAX ile kayıt güncelle"""
    try:
        veri = request.json or {}
        kayit = Kayit.query.get(id)
        if not kayit:
            return jsonify({'basarili': False, 'mesaj': 'Kayıt bulunamadı!'}), 404

        eski = kayit.to_dict()

        tarih_raw = veri.get('tarih', kayit.tarih)
        if '-' in str(tarih_raw) and len(str(tarih_raw)) == 10:
            parts = str(tarih_raw).split('-')
            tarih_formatted = f"{parts[2]}.{parts[1]}.{parts[0]}"
        else:
            tarih_formatted = tarih_raw

        sonuc = kayit_guncelle(
            id=id,
            tarih=tarih_formatted,
            personel_id=int(veri.get('personel_id', kayit.personel_id)),
            toplama_id=int(veri.get('toplama_id', kayit.toplama_id)),
            trendyol_siparis=float(kayit.trendyol_siparis or 0),
            trendyol_fatura=float(kayit.trendyol_fatura or 0),
            diger_pazar=float(veri.get('diger_pazar', kayit.diger_pazar) or 0),
            not_alan=veri.get('not', kayit.not_alan or ''),
        )

        log_audit('update', 'kayitlar', id, eski_deger=eski, yeni_deger=Kayit.query.get(id).to_dict())
        return jsonify(sonuc)

    except Exception:
        return jsonify({'basarili': False, 'mesaj': 'İşlem sırasında bir hata oluştu.'}), 500


@kayitlar_bp.route('/api/sil/<int:id>', methods=['DELETE'])
def api_sil(id):
    """AJAX ile kayıt sil"""
    try:
        kayit = Kayit.query.get(id)
        if kayit:
            log_audit('delete', 'kayitlar', id, eski_deger=kayit.to_dict())
        sonuc = kayit_sil(id)
        return jsonify(sonuc)
    except Exception as e:
        return jsonify({'basarili': False, 'mesaj': f'Hata: {str(e)}'}), 500


@kayitlar_bp.route('/api/template')
def download_template():
    """Günlük kayıt Excel şablonu indir"""
    headers = ['Tarih', 'Personel', 'Toplama', 'Diger Pazar', 'Not']
    stream = build_template(headers)
    return send_file(
        stream,
        as_attachment=True,
        download_name='gunluk_kayit_sablonu.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )


@kayitlar_bp.route('/api/excel-yukle', methods=['POST'])
def excel_yukle():
    """Excel ile toplu kayıt yükleme (yalnız Diğer Pazar)"""
    file = request.files.get('file')
    if not file:
        return jsonify({'basarili': False, 'mesaj': 'Dosya zorunludur!'}), 400

    filename = file.filename or ''
    if not filename.lower().endswith(('.xlsx', '.xlsm', '.xltx', '.xltm')):
        return jsonify({'basarili': False, 'mesaj': 'Geçersiz dosya formatı! (.xlsx gerekli)'}), 400

    expected_headers = ['Tarih', 'Personel', 'Toplama', 'Diger Pazar', 'Not']

    try:
        headers, rows = load_excel_rows(file)
    except Exception:
        return jsonify({'basarili': False, 'mesaj': 'Excel okunamadı. Dosya formatını kontrol edin.'}), 400

    if headers != expected_headers:
        return jsonify({
            'basarili': False,
            'mesaj': 'Excel başlıkları hatalı!',
            'beklenen': expected_headers,
            'bulunan': headers,
        }), 400

    siparislerden_kayit_senkronize_et()

    basarili = 0
    hatalar = []

    for idx, row in enumerate(rows, start=2):
        try:
            tarih_raw = str(row.get('Tarih', '')).strip()
            personel_adi = str(row.get('Personel', '')).strip()
            toplama_adi = str(row.get('Toplama', '')).strip()

            if not tarih_raw or not personel_adi or not toplama_adi:
                hatalar.append({'satir': idx, 'hata': 'Tarih, Personel veya Toplama boş'})
                continue

            personel = Personel.query.filter_by(ad=personel_adi).first()
            if not personel:
                hatalar.append({'satir': idx, 'hata': f'Personel bulunamadı: {personel_adi}'})
                continue

            toplama = Toplama.query.filter_by(ad=toplama_adi).first()
            if not toplama:
                hatalar.append({'satir': idx, 'hata': f'Toplama bulunamadı: {toplama_adi}'})
                continue

            if '-' in tarih_raw and len(tarih_raw) == 10:
                parts = tarih_raw.split('-')
                tarih_formatted = f"{parts[2]}.{parts[1]}.{parts[0]}"
            else:
                tarih_formatted = tarih_raw

            kayit = Kayit.query.filter_by(
                tarih=tarih_formatted,
                personel_id=personel.id,
                toplama_id=toplama.id,
            ).first()

            if kayit:
                kayit.diger_pazar = float(row.get('Diger Pazar') or 0)
                kayit.not_alan = str(row.get('Not', '') or '')
            else:
                kayit = Kayit(
                    tarih=tarih_formatted,
                    personel_id=personel.id,
                    toplama_id=toplama.id,
                    trendyol_siparis=0,
                    trendyol_fatura=0,
                    diger_pazar=float(row.get('Diger Pazar') or 0),
                    not_alan=str(row.get('Not', '') or ''),
                )
                db.session.add(kayit)

            basarili += 1
        except Exception:
            hatalar.append({'satir': idx, 'hata': 'Satır işlenemedi'})

    db.session.commit()
    log_audit('excel_toplu_yukleme', 'kayitlar', None, yeni_deger={'basarili': basarili, 'hatali': len(hatalar)})

    return jsonify({
        'basarili': True,
        'mesaj': f'{basarili} kayıt işlendi, {len(hatalar)} satır atlandı.',
        'ozet': {
            'toplam_satir': len(rows),
            'basarili': basarili,
            'hatali': len(hatalar),
        },
        'hatalar': hatalar,
    })
