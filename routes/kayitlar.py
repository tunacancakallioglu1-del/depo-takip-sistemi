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
        onceki_personel_id = kayit.personel_id

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

        # Kayıt personeli değiştiyse bağlı siparişlere otomatik aktar
        guncel_kayit = Kayit.query.get(id)
        if guncel_kayit and onceki_personel_id != guncel_kayit.personel_id:
            Order.query.filter_by(referans_kayit_id=id).update(
                {'personel_id': guncel_kayit.personel_id},
                synchronize_session=False
            )

        log_audit('update', 'kayitlar', id, eski_deger=eski, yeni_deger=Kayit.query.get(id).to_dict())
        db.session.commit()
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
        download_name='takip_kayit_sablonu.xlsx',
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
    """Seçilen tarihteki siparişleri kayıtlara yeniden senkronize et."""
    try:
        veri = request.get_json() or {}
        tarih_str = veri.get('tarih')
        if not tarih_str:
            return jsonify({'basarili': False, 'mesaj': 'Senkronizasyon için tarih seçimi zorunludur.'}), 400

        tarih_obj = datetime.strptime(tarih_str, '%Y-%m-%d').date()
        sonuc = _senkronize_tarih(tarih_obj)
        log_audit('senkronizasyon', 'kayitlar', None, yeni_deger=sonuc)
        db.session.commit()

        return jsonify({
            'basarili': True,
            'mesaj': f'Senkronizasyon tamamlandı: {sonuc["yeni"]} yeni kayıt, {sonuc["guncellendi"]} kayıt güncellendi.',
            **sonuc,
        })

    except Exception:
        db.session.rollback()
        return jsonify({'basarili': False, 'mesaj': 'Senkronizasyon sırasında bir hata oluştu.'}), 500


def _senkronize_upload(upload_id):
    """Belirli bir upload_id için senkronizasyon yap (route dışından çağrılabilir)"""
    siparisler = Order.query.filter_by(excel_yukleme_id=upload_id).all()
    if not siparisler:
        return {'basarili': True, 'mesaj': 'Senkronize edilecek sipariş bulunamadı.', 'yeni': 0, 'guncellendi': 0}

    tarihler = sorted({s.tarih.date() for s in siparisler if s.tarih})
    toplam_yeni = 0
    toplam_guncellendi = 0
    toplam_islenen = 0

    for tarih_obj in tarihler:
        sonuc = _senkronize_tarih(tarih_obj, upload_id=upload_id)
        toplam_yeni += sonuc['yeni']
        toplam_guncellendi += sonuc['guncellendi']
        toplam_islenen += sonuc['islenen_siparis']

    db.session.commit()
    return {
        'basarili': True,
        'mesaj': f'{toplam_yeni} yeni kayıt oluşturuldu, {toplam_guncellendi} kayıt güncellendi.',
        'yeni': toplam_yeni,
        'guncellendi': toplam_guncellendi,
        'islenen_siparis': toplam_islenen,
    }


def _get_or_create_belirtilmemis_personel():
    personel = Personel.query.filter_by(ad='Belirtilmemiş').first()
    if personel:
        return personel
    personel = Personel(ad='Belirtilmemiş')
    db.session.add(personel)
    db.session.flush()
    return personel


def _senkronize_tarih(tarih_obj, upload_id=None):
    tarih_baslangic = datetime.combine(tarih_obj, datetime.min.time())
    tarih_bitis = datetime.combine(tarih_obj, datetime.max.time())
    tarih_db = tarih_obj.strftime('%d.%m.%Y')

    query = Order.query.filter(
        Order.tarih >= tarih_baslangic,
        Order.tarih <= tarih_bitis,
    )
    if upload_id:
        query = query.filter(Order.excel_yukleme_id == int(upload_id))

    siparisler = query.order_by(Order.id.asc()).all()
    if not siparisler:
        return {'yeni': 0, 'guncellendi': 0, 'islenen_siparis': 0}

    # Tarih + Ürün + Toplama anahtarı
    gruplar = {}
    for s in siparisler:
        key = (s.toplama_id, s.urun_id)
        if key not in gruplar:
            gruplar[key] = {'siparisler': [], 'toplam_adet': 0}
        gruplar[key]['siparisler'].append(s)
        gruplar[key]['toplam_adet'] += int(s.adet or 0)

    yeni = 0
    guncellendi = 0
    now = datetime.now()
    default_personel = _get_or_create_belirtilmemis_personel()
    aktif_anahtarlar = set(gruplar.keys())

    # Seçili tarihte artık siparişi kalmayan senkron kayıtları sıfırla
    eski_kayitlar = Kayit.query.filter_by(tarih=tarih_db).filter(Kayit.urun_id.isnot(None)).all()
    for kayit in eski_kayitlar:
        key = (kayit.toplama_id, kayit.urun_id)
        if key not in aktif_anahtarlar:
            kayit.trendyol_siparis = 0
            kayit.senkronizasyon_sayisi = (kayit.senkronizasyon_sayisi or 0) + 1
            kayit.son_senkronizasyon = now

    for (toplama_id, urun_id), info in gruplar.items():
        siparis_listesi = info['siparisler']
        toplam_adet = info['toplam_adet']

        # Önce aynı anahtarlı kayıt, yoksa aynı tarih+toplama kaydı
        kayit = Kayit.query.filter_by(
            tarih=tarih_db,
            toplama_id=toplama_id,
            urun_id=urun_id,
        ).first()
        if not kayit:
            kayit = Kayit.query.filter_by(
                tarih=tarih_db,
                toplama_id=toplama_id,
                urun_id=None,
            ).first()

        personel_id = kayit.personel_id if kayit and kayit.personel_id else None
        if not personel_id:
            personelli_siparis = next((x for x in siparis_listesi if x.personel_id), None)
            personel_id = personelli_siparis.personel_id if personelli_siparis else default_personel.id

        if kayit:
            kayit.trendyol_siparis = toplam_adet
            kayit.urun_id = urun_id
            kayit.personel_id = personel_id
            kayit.senkronizasyon_sayisi = (kayit.senkronizasyon_sayisi or 0) + 1
            kayit.son_senkronizasyon = now
            guncellendi += 1
        else:
            kayit = Kayit(
                tarih=tarih_db,
                personel_id=personel_id,
                toplama_id=toplama_id,
                urun_id=urun_id,
                trendyol_siparis=toplam_adet,
                trendyol_fatura=0,
                diger_pazar=0,
                not_alan='',
                senkronizasyon_sayisi=1,
                son_senkronizasyon=now,
            )
            db.session.add(kayit)
            db.session.flush()
            yeni += 1

        for s in siparis_listesi:
            s.personel_id = personel_id
            s.senkronize_edildi = True
            s.senkronize_tarihi = now
            s.referans_kayit_id = kayit.id
            s.durum = 'Tamamlandı'

    return {'yeni': yeni, 'guncellendi': guncellendi, 'islenen_siparis': len(siparisler)}
