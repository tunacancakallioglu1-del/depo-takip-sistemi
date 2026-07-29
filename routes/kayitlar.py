# -*- coding: utf-8 -*-
"""
Kayıtlar Rotaları
"""

from datetime import datetime
from io import BytesIO
from flask import Blueprint, render_template, request, jsonify, send_file
from database import db, Kayit, Personel, Toplama, Order, AdetFiltresi, KayitAyrinti, kayit_ekle, kayit_guncelle, kayit_sil
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
            personel_id=int(veri['personel_id']) if veri.get('personel_id') else None,
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

            if not tarih_raw or not toplama_adi:
                hatalar.append({'satir': idx, 'hata': 'Tarih veya Toplama boş'})
                continue

            personel_id = None
            if personel_adi:
                personel = Personel.query.filter_by(ad=personel_adi).first()
                if not personel:
                    hatalar.append({'satir': idx, 'hata': f'Personel bulunamadı: {personel_adi}'})
                    continue
                personel_id = personel.id

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
                personel_id=personel_id,
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
    """Seçili tarihin siparişlerini kayıtlara senkronize et.

    Sipariş No bazında gruplama yapar.  Her grubun ilk satırında (grup_baslangic_satiri=True)
    olan siparişin personel_id'si grubun personeli olarak kullanılır.
    AdetFiltresi varsa aynı (urun_kodu, beden) için farklı adet aralıklarına ayrı
    KayitAyrinti satırları oluşturulur.
    """
    try:
        from sqlalchemy import func as sqlfunc
        veri = request.get_json() or {}
        tarih_str = veri.get('tarih')

        if tarih_str:
            tarih_obj = datetime.strptime(tarih_str, '%Y-%m-%d').date()
        else:
            tarih_obj = datetime.utcnow().date()

        tarih_db = tarih_obj.strftime('%d.%m.%Y')

        # Seçili tarihin BEKLEMEDE siparişlerini al
        siparisler = Order.query.filter(
            Order.durum == 'BEKLEMEDE',
            sqlfunc.date(Order.tarih) == tarih_obj.strftime('%Y-%m-%d'),
        ).all()

        if not siparisler:
            return jsonify({
                'basarili': True,
                'mesaj': f'{tarih_db} tarihinde senkronize edilecek BEKLEMEDE sipariş bulunamadı.',
                'yeni': 0,
                'guncellendi': 0,
            })

        # 1. Sipariş No bazında grupla
        siparis_gruplari = {}
        for s in siparisler:
            siparis_gruplari.setdefault(s.siparis_no, []).append(s)

        yeni = 0
        guncellendi = 0
        now = datetime.now()

        for siparis_no, grup_listesi in siparis_gruplari.items():
            # Grup başı personeli: grup_baslangic_satiri=True olan ilk satır
            grup_bas = next((s for s in grup_listesi if s.grup_baslangic_satiri), None)
            # Eğer bayrak hiçbirinde yoksa (eski veri) listedeki ilki kabul edilir
            if grup_bas is None:
                grup_bas = grup_listesi[0]
            grup_personel_id = grup_bas.personel_id  # NULL olabilir

            # 2. Aynı grup içinde toplama bazında grupla
            toplama_gruplari = {}
            for s in grup_listesi:
                if s.toplama_id is None:
                    continue
                toplama_gruplari.setdefault(s.toplama_id, []).append(s)

            for toplama_id, toplama_listesi in toplama_gruplari.items():
                # 3. Her siparis için AdetFiltresi ile kategori belirle
                kategori_gruplari = {}  # key → {urun_kodu, beden, adet_toplam, min_f, max_f, siparisler}

                for s in toplama_listesi:
                    urun_kodu = (s.urun.ana_kod if s.urun else s.urun_kodu_ham) or ''
                    beden = s.beden or ''

                    filtreler = AdetFiltresi.query.filter_by(
                        toplama_id=toplama_id,
                        urun_kodu=urun_kodu,
                        beden=beden or None,
                    ).order_by(AdetFiltresi.min_adet).all()

                    # Eğer beden bazlı filtre bulunamazsa NULL beden ile dene
                    if not filtreler and beden:
                        filtreler = AdetFiltresi.query.filter_by(
                            toplama_id=toplama_id,
                            urun_kodu=urun_kodu,
                            beden=None,
                        ).order_by(AdetFiltresi.min_adet).all()

                    min_f = None
                    max_f = None
                    for filtre in filtreler:
                        ust = filtre.max_adet if filtre.max_adet is not None else float('inf')
                        if filtre.min_adet <= s.adet <= ust:
                            min_f = filtre.min_adet
                            max_f = filtre.max_adet
                            break

                    cat_key = (urun_kodu, beden, min_f, max_f)
                    if cat_key not in kategori_gruplari:
                        kategori_gruplari[cat_key] = {
                            'urun_kodu': urun_kodu,
                            'beden': beden,
                            'adet_toplam': 0,
                            'min_f': min_f,
                            'max_f': max_f,
                            'siparisler': [],
                        }
                    kategori_gruplari[cat_key]['adet_toplam'] += s.adet
                    kategori_gruplari[cat_key]['siparisler'].append(s)

                # 4. Bu toplama + personel için Kayit bul ya da oluştur
                kayit = Kayit.query.filter_by(
                    tarih=tarih_db,
                    toplama_id=toplama_id,
                    personel_id=grup_personel_id,
                ).first()

                if kayit:
                    kayit.senkronizasyon_sayisi = (kayit.senkronizasyon_sayisi or 0) + 1
                    kayit.son_senkronizasyon = now
                    guncellendi += 1
                else:
                    toplam_adet = sum(k['adet_toplam'] for k in kategori_gruplari.values())
                    kayit = Kayit(
                        tarih=tarih_db,
                        personel_id=grup_personel_id,
                        toplama_id=toplama_id,
                        trendyol_siparis=0,
                        trendyol_fatura=0,
                        diger_pazar=0,
                        not_alan='',
                        senkronizasyon_sayisi=1,
                        son_senkronizasyon=now,
                    )
                    db.session.add(kayit)
                    db.session.flush()
                    yeni += 1

                # 5. Her kategori → KayitAyrinti oluştur
                for cat_key, kat in kategori_gruplari.items():
                    ayrinti = KayitAyrinti(
                        kayit_id=kayit.id,
                        urun_kodu=kat['urun_kodu'],
                        beden=kat['beden'] or None,
                        adet=kat['adet_toplam'],
                        min_adet_filtre=kat['min_f'],
                        max_adet_filtre=kat['max_f'],
                        olusturulma_tarihi=now,
                    )
                    db.session.add(ayrinti)

                    for s in kat['siparisler']:
                        s.durum = 'TAMAMLANDI'
                        s.senkronize_edildi = True
                        s.senkronize_tarihi = now

                # Sipariş No = 1 Sipariş (kaç ürün/kategori olursa olsun)
                kayit.trendyol_siparis = (kayit.trendyol_siparis or 0) + 1

        db.session.commit()
        log_audit('senkronizasyon', 'kayitlar', None,
                  yeni_deger={'tarih': tarih_db, 'yeni': yeni, 'guncellendi': guncellendi})

        return jsonify({
            'basarili': True,
            'mesaj': (
                f'{len(siparis_gruplari)} sipariş grubu işlendi. '
                f'{yeni} yeni kayıt oluşturuldu, {guncellendi} kayıt güncellendi.'
            ),
            'yeni': yeni,
            'guncellendi': guncellendi,
        })

    except Exception:
        db.session.rollback()
        import traceback; traceback.print_exc()
        return jsonify({'basarili': False, 'mesaj': 'Senkronizasyon sırasında bir hata oluştu.'}), 500


def _senkronize_upload(upload_id):
    """Belirli bir upload_id için senkronizasyon yap (route dışından çağrılabilir)"""
    now = datetime.now()
    tarih_db = now.strftime('%d.%m.%Y')

    siparisler = Order.query.filter_by(
        excel_yukleme_id=upload_id,
        senkronize_edildi=False,
    ).filter(Order.durum == 'BEKLEMEDE').all()

    if not siparisler:
        return {'basarili': True, 'mesaj': 'Senkronize edilecek BEKLEMEDE sipariş bulunamadı.', 'yeni': 0, 'guncellendi': 0}

    siparis_gruplari = {}
    for s in siparisler:
        siparis_gruplari.setdefault(s.siparis_no, []).append(s)

    yeni = 0
    guncellendi = 0

    for siparis_no, grup_listesi in siparis_gruplari.items():
        grup_bas = next((s for s in grup_listesi if s.grup_baslangic_satiri), None)
        if grup_bas is None:
            grup_bas = grup_listesi[0]
        grup_personel_id = grup_bas.personel_id

        toplama_gruplari = {}
        for s in grup_listesi:
            if s.toplama_id is None:
                continue
            toplama_gruplari.setdefault(s.toplama_id, []).append(s)

        for toplama_id, toplama_listesi in toplama_gruplari.items():
            kategori_gruplari = {}
            for s in toplama_listesi:
                urun_kodu = (s.urun.ana_kod if s.urun else s.urun_kodu_ham) or ''
                beden = s.beden or ''
                filtreler = AdetFiltresi.query.filter_by(
                    toplama_id=toplama_id, urun_kodu=urun_kodu, beden=beden or None,
                ).order_by(AdetFiltresi.min_adet).all()
                if not filtreler and beden:
                    filtreler = AdetFiltresi.query.filter_by(
                        toplama_id=toplama_id, urun_kodu=urun_kodu, beden=None,
                    ).order_by(AdetFiltresi.min_adet).all()
                min_f = max_f = None
                for filtre in filtreler:
                    ust = filtre.max_adet if filtre.max_adet is not None else float('inf')
                    if filtre.min_adet <= s.adet <= ust:
                        min_f, max_f = filtre.min_adet, filtre.max_adet
                        break
                cat_key = (urun_kodu, beden, min_f, max_f)
                if cat_key not in kategori_gruplari:
                    kategori_gruplari[cat_key] = {
                        'urun_kodu': urun_kodu, 'beden': beden,
                        'adet_toplam': 0, 'min_f': min_f, 'max_f': max_f, 'siparisler': [],
                    }
                kategori_gruplari[cat_key]['adet_toplam'] += s.adet
                kategori_gruplari[cat_key]['siparisler'].append(s)

            kayit = Kayit.query.filter_by(
                tarih=tarih_db, toplama_id=toplama_id, personel_id=grup_personel_id,
            ).first()
            if kayit:
                kayit.senkronizasyon_sayisi = (kayit.senkronizasyon_sayisi or 0) + 1
                kayit.son_senkronizasyon = now
                guncellendi += 1
            else:
                kayit = Kayit(
                    tarih=tarih_db, personel_id=grup_personel_id, toplama_id=toplama_id,
                    trendyol_siparis=0, trendyol_fatura=0, diger_pazar=0, not_alan='',
                    senkronizasyon_sayisi=1, son_senkronizasyon=now,
                )
                db.session.add(kayit)
                db.session.flush()
                yeni += 1

            for cat_key, kat in kategori_gruplari.items():
                db.session.add(KayitAyrinti(
                    kayit_id=kayit.id,
                    urun_kodu=kat['urun_kodu'],
                    beden=kat['beden'] or None,
                    adet=kat['adet_toplam'],
                    min_adet_filtre=kat['min_f'],
                    max_adet_filtre=kat['max_f'],
                    olusturulma_tarihi=now,
                ))
                for s in kat['siparisler']:
                    s.durum = 'TAMAMLANDI'
                    s.senkronize_edildi = True
                    s.senkronize_tarihi = now

            # Sipariş No = 1 Sipariş (kaç ürün/kategori olursa olsun)
            kayit.trendyol_siparis = (kayit.trendyol_siparis or 0) + 1

    db.session.commit()
    return {
        'basarili': True,
        'mesaj': f'{yeni} yeni kayıt oluşturuldu, {guncellendi} kayıt güncellendi.',
        'yeni': yeni,
        'guncellendi': guncellendi,
    }
