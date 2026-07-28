# -*- coding: utf-8 -*-
"""
Kayıtlar Rotaları
"""

from datetime import datetime
from io import BytesIO
from flask import Blueprint, render_template, request, jsonify, send_file
from database import db, Kayit, Personel, Toplama, Order, kayit_ekle, kayit_guncelle, kayit_sil
from utils.excel_utils import build_template, load_excel_rows, calculate_file_hash
from utils.audit_utils import log_audit

kayitlar_bp = Blueprint('kayitlar', __name__, url_prefix='/kayitlar')


@kayitlar_bp.route('/')
def lista():
    """Kayıtlar listesi"""
    
    kayitlar = Kayit.query.order_by(Kayit.tarih.desc()).all()
    personeller = Personel.query.all()
    toplamalar = Toplama.query.all()
    
    return render_template('kayitlar.html',
                         kayitlar=kayitlar,
                         personeller=personeller,
                         toplamalar=toplamalar)


@kayitlar_bp.route('/api/list', methods=['GET'])
def api_list():
    """AJAX ile kayıtları getir"""
    
    # Filtreleri al
    personel_id = request.args.get('personel_id')
    toplama_id = request.args.get('toplama_id')
    tarih_baslangic = request.args.get('tarih_baslangic')
    tarih_bitis = request.args.get('tarih_bitis')
    
    # Sorgu oluştur
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
            trendyol_siparis=float(veri.get('trendyol_siparis', kayit.trendyol_siparis) or 0),
            trendyol_fatura=float(veri.get('trendyol_fatura', kayit.trendyol_fatura) or 0),
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
    headers = ['Tarih', 'Personel', 'Toplama', 'Trendyol Siparis', 'Trendyol Fatura', 'Diger Pazar', 'Not']
    stream = build_template(headers)
    return send_file(
        stream,
        as_attachment=True,
        download_name='gunluk_kayit_sablonu.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )


@kayitlar_bp.route('/api/excel-yukle', methods=['POST'])
def excel_yukle():
    """Excel ile toplu kayıt yükleme"""
    file = request.files.get('file')
    if not file:
        return jsonify({'basarili': False, 'mesaj': 'Dosya zorunludur!'}), 400

    filename = file.filename or ''
    if not filename.lower().endswith(('.xlsx', '.xlsm', '.xltx', '.xltm')):
        return jsonify({'basarili': False, 'mesaj': 'Geçersiz dosya formatı! (.xlsx gerekli)'}), 400

    expected_headers = ['Tarih', 'Personel', 'Toplama', 'Trendyol Siparis', 'Trendyol Fatura', 'Diger Pazar', 'Not']

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

            # Format tarih
            if '-' in tarih_raw and len(tarih_raw) == 10:
                parts = tarih_raw.split('-')
                tarih_formatted = f"{parts[2]}.{parts[1]}.{parts[0]}"
            else:
                tarih_formatted = tarih_raw

            from database import kayit_ekle as _kayit_ekle
            _kayit_ekle(
                tarih=tarih_formatted,
                personel_id=personel.id,
                toplama_id=toplama.id,
                trendyol_siparis=float(row.get('Trendyol Siparis') or 0),
                trendyol_fatura=float(row.get('Trendyol Fatura') or 0),
                diger_pazar=float(row.get('Diger Pazar') or 0),
                not_alan=str(row.get('Not', '') or ''),
            )
            basarili += 1
        except Exception:
            hatalar.append({'satir': idx, 'hata': 'Satır işlenemedi'})

    log_audit('excel_toplu_yukleme', 'kayitlar', None, yeni_deger={'basarili': basarili, 'hatali': len(hatalar)})

    return jsonify({
        'basarili': True,
        'mesaj': f'{basarili} kayıt eklendi, {len(hatalar)} satır atlandı.',
        'ozet': {
            'toplam_satir': len(rows),
            'basarili': basarili,
            'hatali': len(hatalar),
        },
        'hatalar': hatalar,
    })


@kayitlar_bp.route('/api/senkronize', methods=['POST'])
def senkronize_et():
    """Siparişlerden kayıtlara senkronize et.

    Bugünün (veya gönderilen tarihin) senkronize edilmemiş siparişlerini
    personel+toplama bazında gruplar ve kayıtlara Trendyol Sipariş olarak ekler.
    Aynı gün aynı personel+toplama kaydı varsa üzerine ekleme yapar.
    """
    try:
        veri = request.get_json() or {}
        tarih_str = veri.get('tarih')
        upload_id = veri.get('upload_id')

        if tarih_str:
            tarih_obj = datetime.strptime(tarih_str, '%Y-%m-%d').date()
        else:
            tarih_obj = datetime.utcnow().date()

        tarih_db = tarih_obj.strftime('%d.%m.%Y')

        # Senkronize edilmemiş siparişleri filtrele
        query = Order.query.filter_by(senkronize_edildi=False)
        if upload_id:
            query = query.filter_by(excel_yukleme_id=int(upload_id))

        siparisler = query.all()

        if not siparisler:
            return jsonify({'basarili': True, 'mesaj': 'Senkronize edilecek sipariş bulunamadı.', 'yeni': 0, 'guncellendi': 0})

        # Personel+Toplama bazında sayıları topla
        gruplar = {}
        for s in siparisler:
            if not s.personel_id:
                continue
            key = (s.personel_id, s.toplama_id)
            gruplar[key] = gruplar.get(key, 0) + 1

        yeni = 0
        guncellendi = 0

        for (personel_id, toplama_id), siparis_sayisi in gruplar.items():
            kayit = Kayit.query.filter_by(
                tarih=tarih_db,
                personel_id=personel_id,
                toplama_id=toplama_id,
            ).first()

            if kayit:
                kayit.trendyol_siparis = (kayit.trendyol_siparis or 0) + siparis_sayisi
                kayit.senkronizasyon_sayisi = (kayit.senkronizasyon_sayisi or 0) + 1
                kayit.son_senkronizasyon = datetime.now()
                guncellendi += 1
            else:
                kayit = Kayit(
                    tarih=tarih_db,
                    personel_id=personel_id,
                    toplama_id=toplama_id,
                    trendyol_siparis=siparis_sayisi,
                    trendyol_fatura=0,
                    diger_pazar=0,
                    not_alan='',
                    senkronizasyon_sayisi=1,
                    son_senkronizasyon=datetime.now(),
                )
                db.session.add(kayit)
                db.session.flush()
                yeni += 1

        # Siparişleri senkronize edildi olarak işaretle
        now = datetime.now()
        for s in siparisler:
            if s.personel_id:
                s.senkronize_edildi = True
                s.senkronize_tarihi = now

        db.session.commit()
        log_audit('senkronizasyon', 'kayitlar', None, yeni_deger={'yeni': yeni, 'guncellendi': guncellendi})

        return jsonify({
            'basarili': True,
            'mesaj': f'Senkronizasyon tamamlandı: {yeni} yeni kayıt, {guncellendi} kayıt güncellendi.',
            'yeni': yeni,
            'guncellendi': guncellendi,
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'basarili': False, 'mesaj': f'Hata: {str(e)}'}), 500


def _senkronize_upload(upload_id):
    """Belirli bir upload_id için senkronizasyon yap (route dışından çağrılabilir)"""
    tarih_db = datetime.utcnow().strftime('%d.%m.%Y')

    siparisler = Order.query.filter_by(
        excel_yukleme_id=upload_id,
        senkronize_edildi=False,
    ).all()

    if not siparisler:
        return {'basarili': True, 'mesaj': 'Senkronize edilecek sipariş bulunamadı.', 'yeni': 0, 'guncellendi': 0}

    gruplar = {}
    for s in siparisler:
        if not s.personel_id:
            continue
        key = (s.personel_id, s.toplama_id)
        gruplar[key] = gruplar.get(key, 0) + 1

    yeni = 0
    guncellendi = 0

    for (personel_id, toplama_id), siparis_sayisi in gruplar.items():
        kayit = Kayit.query.filter_by(
            tarih=tarih_db,
            personel_id=personel_id,
            toplama_id=toplama_id,
        ).first()

        if kayit:
            kayit.trendyol_siparis = (kayit.trendyol_siparis or 0) + siparis_sayisi
            kayit.senkronizasyon_sayisi = (kayit.senkronizasyon_sayisi or 0) + 1
            kayit.son_senkronizasyon = datetime.now()
            guncellendi += 1
        else:
            kayit = Kayit(
                tarih=tarih_db,
                personel_id=personel_id,
                toplama_id=toplama_id,
                trendyol_siparis=siparis_sayisi,
                trendyol_fatura=0,
                diger_pazar=0,
                not_alan='',
                senkronizasyon_sayisi=1,
                son_senkronizasyon=datetime.now(),
            )
            db.session.add(kayit)
            db.session.flush()
            yeni += 1

    now = datetime.now()
    for s in siparisler:
        if s.personel_id:
            s.senkronize_edildi = True
            s.senkronize_tarihi = now

    db.session.commit()
    return {
        'basarili': True,
        'mesaj': f'{yeni} yeni kayıt oluşturuldu, {guncellendi} kayıt güncellendi.',
        'yeni': yeni,
        'guncellendi': guncellendi,
    }
