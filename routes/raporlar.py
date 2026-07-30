# -*- coding: utf-8 -*-
"""Raporlama rotaları"""

from io import BytesIO
from datetime import datetime
import pandas as pd
from flask import Blueprint, render_template, request, jsonify, send_file
from sqlalchemy import func
from database import db, Order, Return, Product, Personel, Toplama, Kayit, KayitAyrinti, IadeHatasi

raporlar_bp = Blueprint('raporlar', __name__, url_prefix='/raporlar')

HATA_TIPLERI = [
    'YANLIŞ ÜRÜN',
    'YANLIŞ BEDEN',
    'HASARLI ÜRÜN',
    'EKSİK ÜRÜN',
    'FAZLA ÜRÜN',
    'AMBALAJ HATASI',
    'DİĞER',
]


def _parse_tarih_dd_mm_yyyy(tarih_str):
    """DD.MM.YYYY veya YYYY-MM-DD formatını date objesine çevir"""
    tarih_str = str(tarih_str or '').strip()
    for fmt in ('%d.%m.%Y', '%Y-%m-%d'):
        try:
            return datetime.strptime(tarih_str, fmt).date()
        except ValueError:
            continue
    return None


def _to_dd_mm_yyyy(date_obj):
    return date_obj.strftime('%d.%m.%Y')


def _filter_kayitlar_by_range(sorgu, baslangic_str, bitis_str):
    """Kayıt.tarih (DD.MM.YYYY string) üzerinde Python seviyesinde tarih filtresi"""
    bas = _parse_tarih_dd_mm_yyyy(baslangic_str) if baslangic_str else None
    bit = _parse_tarih_dd_mm_yyyy(bitis_str) if bitis_str else None
    kayitlar = sorgu.all()
    if not bas and not bit:
        return kayitlar
    result = []
    for k in kayitlar:
        kt = _parse_tarih_dd_mm_yyyy(k.tarih)
        if kt is None:
            continue
        if bas and kt < bas:
            continue
        if bit and kt > bit:
            continue
        result.append(k)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# SAYFA
# ─────────────────────────────────────────────────────────────────────────────

@raporlar_bp.route('/')
def index():
    personeller = Personel.query.order_by(Personel.ad).all()
    toplamalar = Toplama.query.order_by(Toplama.ad).all()
    hata_tipleri = HATA_TIPLERI
    return render_template('raporlar.html',
                           personeller=personeller,
                           toplamalar=toplamalar,
                           hata_tipleri=hata_tipleri)


# ─────────────────────────────────────────────────────────────────────────────
# ÖZET KARTI
# ─────────────────────────────────────────────────────────────────────────────

@raporlar_bp.route('/api/ozet')
def ozet():
    toplam_kayit = Kayit.query.count()
    toplam_personel = Personel.query.count()
    toplam_siparis = db.session.query(func.count(func.distinct(Order.siparis_no))).scalar() or 0
    toplam_iade_hatasi = IadeHatasi.query.count()
    toplam_senkronize = Order.query.filter_by(durum='TAMAMLANDI').count()

    return jsonify({
        'basarili': True,
        'ozet': {
            'toplam_kayit': toplam_kayit,
            'toplam_personel': toplam_personel,
            'toplam_siparis': toplam_siparis,
            'toplam_iade_hatasi': toplam_iade_hatasi,
            'toplam_senkronize': toplam_senkronize,
        }
    })


# ─────────────────────────────────────────────────────────────────────────────
# KAYITLAR RAPORU (filtrelenmiş)
# ─────────────────────────────────────────────────────────────────────────────

@raporlar_bp.route('/listele', methods=['POST'])
def listele():
    """Kayıtlardan filtrelenmiş rapor — ürün ayrıntılarıyla"""
    veri = request.get_json() or {}
    personel_id = veri.get('personel_id')
    toplama_id = veri.get('toplama_id')
    baslangic = str(veri.get('tarih_baslangic') or '').strip()
    bitis = str(veri.get('tarih_bitis') or '').strip()
    arama = str(veri.get('arama') or '').strip().lower()

    sorgu = Kayit.query
    if personel_id:
        sorgu = sorgu.filter(Kayit.personel_id == int(personel_id))
    if toplama_id:
        sorgu = sorgu.filter(Kayit.toplama_id == int(toplama_id))

    kayitlar = _filter_kayitlar_by_range(sorgu, baslangic, bitis)
    kayitlar.sort(key=lambda k: (_parse_tarih_dd_mm_yyyy(k.tarih) or datetime.min.date()), reverse=True)

    sonuc = []
    for k in kayitlar:
        personel_adi = k.personel.ad if k.personel else '—'
        toplama_adi = k.toplama.ad if k.toplama else '—'

        if arama and arama not in personel_adi.lower() and arama not in toplama_adi.lower() and arama not in k.tarih:
            continue

        ayrintilari = [
            {
                'urun_kodu': a.urun_kodu,
                'beden': a.beden or '—',
                'adet': a.adet,
            }
            for a in k.ayrintilari
        ]

        sonuc.append({
            'id': k.id,
            'tarih': k.tarih,
            'personel': personel_adi,
            'personel_id': k.personel_id,
            'toplama': toplama_adi,
            'trendyol_siparis': int(k.trendyol_siparis or 0),
            'trendyol_fatura': float(k.trendyol_fatura or 0),
            'diger_pazar': float(k.diger_pazar or 0),
            'toplam': int(k.trendyol_siparis or 0) + float(k.trendyol_fatura or 0) + float(k.diger_pazar or 0),
            'senkronizasyon_sayisi': k.senkronizasyon_sayisi or 0,
            'senkronizasyon_tarihi': k.son_senkronizasyon.strftime('%d.%m.%Y %H:%M') if k.son_senkronizasyon else '—',
            'urun_detaylari': ayrintilari,
            'urun_sayisi': len(ayrintilari),
        })

    return jsonify({'basarili': True, 'kayitlar': sonuc, 'toplam': len(sonuc)})


# ─────────────────────────────────────────────────────────────────────────────
# PERSONEL İŞLEM TARİHÇESİ
# ─────────────────────────────────────────────────────────────────────────────

@raporlar_bp.route('/personel/islem-tarihcesi', methods=['POST'])
def personel_islem_tarihcesi():
    """Personel bazlı işlem tarihçesi — o tarihte ne yaptı?"""
    veri = request.get_json() or {}
    personel_id = veri.get('personel_id')
    baslangic = str(veri.get('tarih_baslangic') or '').strip()
    bitis = str(veri.get('tarih_bitis') or '').strip()

    if not personel_id:
        return jsonify({'basarili': False, 'mesaj': 'Personel seçimi zorunludur!'}), 400

    personel = Personel.query.get(int(personel_id))
    if not personel:
        return jsonify({'basarili': False, 'mesaj': 'Personel bulunamadı!'}), 404

    sorgu = Kayit.query.filter(Kayit.personel_id == int(personel_id))
    kayitlar = _filter_kayitlar_by_range(sorgu, baslangic, bitis)
    kayitlar.sort(key=lambda k: (_parse_tarih_dd_mm_yyyy(k.tarih) or datetime.min.date()), reverse=True)

    tarihce = []
    for k in kayitlar:
        ayrintilari = k.ayrintilari
        toplam_adet = sum(a.adet for a in ayrintilari)
        urun_listesi = [
            {'urun_kodu': a.urun_kodu, 'beden': a.beden or '—', 'adet': a.adet}
            for a in ayrintilari
        ]

        # O tarihte o kişiye bağlı iade hataları
        iade_hatalari = IadeHatasi.query.filter_by(
            personel_id=int(personel_id),
            tarih=k.tarih,
        ).all()

        tarihce.append({
            'tarih': k.tarih,
            'toplama': k.toplama.ad if k.toplama else '—',
            'siparis_sayisi': int(k.trendyol_siparis or 0),
            'urun_cesidi': len(urun_listesi),
            'toplam_adet': toplam_adet,
            'urunler': urun_listesi,
            'iade_hata_sayisi': len(iade_hatalari),
            'iade_hatalari': [ih.to_dict() for ih in iade_hatalari],
            'senkronizasyon_sayisi': k.senkronizasyon_sayisi or 0,
        })

    # Genel özet
    toplam_siparis = sum(t['siparis_sayisi'] for t in tarihce)
    toplam_urun_adet = sum(t['toplam_adet'] for t in tarihce)
    toplam_iade_hata = sum(t['iade_hata_sayisi'] for t in tarihce)

    return jsonify({
        'basarili': True,
        'personel': {'id': personel.id, 'ad': personel.ad},
        'tarihce': tarihce,
        'ozet': {
            'toplam_gun': len(tarihce),
            'toplam_siparis': toplam_siparis,
            'toplam_urun_adet': toplam_urun_adet,
            'toplam_iade_hata': toplam_iade_hata,
        }
    })


# ─────────────────────────────────────────────────────────────────────────────
# İADE HATA KAYDI + LİSTELEME
# ─────────────────────────────────────────────────────────────────────────────

@raporlar_bp.route('/iade/kayit', methods=['POST'])
def iade_kayit():
    """İade hatası kaydı — tarih+ürün+hata tipi üzerinden personele/kayıda otomatik bağlan"""
    veri = request.get_json() or {}
    tarih_raw = str(veri.get('tarih') or '').strip()
    urun_kodu = str(veri.get('urun_kodu') or '').strip() or None
    beden = str(veri.get('beden') or '').strip() or None
    hata_tipi = str(veri.get('hata_tipi') or '').strip()
    aciklama = str(veri.get('aciklama') or '').strip() or None
    siparis_no = str(veri.get('siparis_no') or '').strip() or None
    toplama_id_raw = veri.get('toplama_id')

    if not tarih_raw or not hata_tipi:
        return jsonify({'basarili': False, 'mesaj': 'Tarih ve Hata Tipi zorunludur!'}), 400

    tarih_obj = _parse_tarih_dd_mm_yyyy(tarih_raw)
    if not tarih_obj:
        return jsonify({'basarili': False, 'mesaj': 'Geçersiz tarih formatı!'}), 400

    tarih_db = _to_dd_mm_yyyy(tarih_obj)
    toplama_id = int(toplama_id_raw) if toplama_id_raw else None

    # O tarihte kayıt olan personeli bul (iade senkronizasyonu)
    kayit_sorgu = Kayit.query.filter_by(tarih=tarih_db)
    if toplama_id:
        kayit_sorgu = kayit_sorgu.filter_by(toplama_id=toplama_id)

    kayit = kayit_sorgu.first()
    personel_id = kayit.personel_id if kayit else None
    kayit_id = kayit.id if kayit else None
    baglanan_toplama_id = kayit.toplama_id if kayit else toplama_id

    iade_hatasi = IadeHatasi(
        tarih=tarih_db,
        urun_kodu=urun_kodu,
        beden=beden,
        hata_tipi=hata_tipi,
        aciklama=aciklama,
        siparis_no=siparis_no,
        personel_id=personel_id,
        kayit_id=kayit_id,
        toplama_id=baglanan_toplama_id,
        olusturulma_tarihi=datetime.now(),
    )
    db.session.add(iade_hatasi)
    db.session.commit()

    personel_adi = iade_hatasi.personel.ad if iade_hatasi.personel else None
    mesaj = f'İade hatası kaydedildi.'
    if personel_adi:
        mesaj += f' {tarih_db} tarihindeki kayda göre {personel_adi} adlı personele otomatik bağlandı.'
    else:
        mesaj += f' {tarih_db} tarihi için kayıt bulunamadı, personel bağlanamadı.'

    return jsonify({'basarili': True, 'mesaj': mesaj, 'kayit': iade_hatasi.to_dict()})


@raporlar_bp.route('/iade/listele', methods=['POST'])
def iade_listele():
    """İade hatalarını filtreli listele"""
    veri = request.get_json() or {}
    personel_id = veri.get('personel_id')
    toplama_id = veri.get('toplama_id')
    baslangic = str(veri.get('tarih_baslangic') or '').strip()
    bitis = str(veri.get('tarih_bitis') or '').strip()
    hata_tipi = str(veri.get('hata_tipi') or '').strip()

    sorgu = IadeHatasi.query
    if personel_id:
        sorgu = sorgu.filter(IadeHatasi.personel_id == int(personel_id))
    if toplama_id:
        sorgu = sorgu.filter(IadeHatasi.toplama_id == int(toplama_id))
    if hata_tipi:
        sorgu = sorgu.filter(IadeHatasi.hata_tipi == hata_tipi)

    tum_hatalar = sorgu.order_by(IadeHatasi.id.desc()).all()

    bas = _parse_tarih_dd_mm_yyyy(baslangic) if baslangic else None
    bit = _parse_tarih_dd_mm_yyyy(bitis) if bitis else None

    sonuc = []
    for ih in tum_hatalar:
        if bas or bit:
            kt = _parse_tarih_dd_mm_yyyy(ih.tarih)
            if kt is None:
                continue
            if bas and kt < bas:
                continue
            if bit and kt > bit:
                continue
        sonuc.append(ih.to_dict())

    return jsonify({'basarili': True, 'hatalar': sonuc, 'toplam': len(sonuc)})


@raporlar_bp.route('/iade/sil/<int:iade_id>', methods=['DELETE'])
def iade_sil(iade_id):
    ih = IadeHatasi.query.get_or_404(iade_id)
    db.session.delete(ih)
    db.session.commit()
    return jsonify({'basarili': True, 'mesaj': 'İade hatası silindi.'})


# ─────────────────────────────────────────────────────────────────────────────
# MEVCUT API'LAR (değiştirilmedi)
# ─────────────────────────────────────────────────────────────────────────────

@raporlar_bp.route('/api/personel')
def personel_raporu():
    query = db.session.query(
        Personel.ad.label('personel'),
        func.count(func.distinct(Order.siparis_no)).label('siparis_sayisi'),
        func.coalesce(func.sum(Order.adet), 0).label('urun_sayisi'),
    ).outerjoin(Order, Order.personel_id == Personel.id).group_by(Personel.id)

    rows = [
        {
            'personel': row.personel,
            'siparis_sayisi': int(row.siparis_sayisi),
            'urun_sayisi': int(row.urun_sayisi),
        }
        for row in query.all()
    ]
    return jsonify({'basarili': True, 'veri': rows})


@raporlar_bp.route('/api/gunluk-personel')
def gunluk_personel_raporu():
    """Günlük kayıtlar bazında personel raporu"""
    query = db.session.query(
        Personel.ad.label('personel'),
        Kayit.tarih,
        Toplama.ad.label('toplama'),
        func.coalesce(func.sum(Kayit.trendyol_siparis), 0).label('trendyol_siparis'),
        func.coalesce(func.sum(Kayit.trendyol_fatura), 0).label('trendyol_fatura'),
        func.coalesce(func.sum(Kayit.diger_pazar), 0).label('diger_pazar'),
    ).join(Personel, Kayit.personel_id == Personel.id
    ).join(Toplama, Kayit.toplama_id == Toplama.id
    ).group_by(Personel.id, Kayit.tarih, Toplama.id).order_by(Kayit.tarih.desc())

    rows = [
        {
            'personel': row.personel,
            'tarih': row.tarih,
            'toplama': row.toplama,
            'trendyol_siparis': float(row.trendyol_siparis),
            'trendyol_fatura': float(row.trendyol_fatura),
            'diger_pazar': float(row.diger_pazar),
            'toplam': float(row.trendyol_siparis) + float(row.trendyol_fatura) + float(row.diger_pazar),
        }
        for row in query.all()
    ]
    return jsonify({'basarili': True, 'veri': rows})


@raporlar_bp.route('/api/toplama')
def toplama_raporu():
    query = db.session.query(
        Toplama.ad.label('toplama'),
        func.count(func.distinct(Order.siparis_no)).label('siparis_sayisi'),
        func.coalesce(func.sum(Order.adet), 0).label('urun_sayisi'),
        func.count(func.distinct(Order.urun_id)).label('farkli_urun_sayisi'),
    ).outerjoin(Order, Order.toplama_id == Toplama.id).group_by(Toplama.id)

    rows = [
        {
            'toplama': row.toplama,
            'siparis_sayisi': int(row.siparis_sayisi),
            'urun_sayisi': int(row.urun_sayisi),
            'farkli_urun_sayisi': int(row.farkli_urun_sayisi),
        }
        for row in query.all()
    ]
    return jsonify({'basarili': True, 'veri': rows})


@raporlar_bp.route('/api/urun')
def urun_raporu():
    query = db.session.query(
        Product.ana_kod,
        Product.marka,
        func.count(func.distinct(Order.siparis_no)).label('siparis_sayisi'),
        func.coalesce(func.sum(Order.adet), 0).label('adet'),
    ).outerjoin(Order, Order.urun_id == Product.id).group_by(Product.id)

    rows = [
        {
            'ana_kod': row.ana_kod,
            'marka': row.marka,
            'siparis_sayisi': int(row.siparis_sayisi),
            'adet': int(row.adet),
        }
        for row in query.all()
    ]
    return jsonify({'basarili': True, 'veri': rows})


@raporlar_bp.route('/api/iade-analiz')
def iade_analiz():
    query = db.session.query(
        Return.sebebi,
        func.coalesce(func.sum(Return.adet), 0).label('adet')
    ).group_by(Return.sebebi).all()

    rows = [{'sebep': row.sebebi or 'Belirtilmedi', 'adet': int(row.adet)} for row in query]
    return jsonify({'basarili': True, 'veri': rows})


@raporlar_bp.route('/api/prim')
def prim_raporu():
    """Personel bazlı prim raporu"""
    prim_siparis = float(request.args.get('prim_siparis', 0))
    prim_urun = float(request.args.get('prim_urun', 0))

    personel_query = db.session.query(
        Personel.id,
        Personel.ad.label('personel'),
        func.count(func.distinct(Order.siparis_no)).label('siparis_sayisi'),
        func.coalesce(func.sum(Order.adet), 0).label('urun_sayisi'),
        func.count(func.distinct(Return.id)).label('iade_sayisi'),
    ).outerjoin(Order, Order.personel_id == Personel.id
    ).outerjoin(Return, Return.siparis_no == Order.siparis_no
    ).group_by(Personel.id)

    rows = []
    for row in personel_query.all():
        siparis = int(row.siparis_sayisi)
        urun = int(row.urun_sayisi)
        iade = int(row.iade_sayisi)
        prim = siparis * prim_siparis + urun * prim_urun
        rows.append({
            'personel': row.personel,
            'siparis_sayisi': siparis,
            'urun_sayisi': urun,
            'iade_sayisi': iade,
            'prim': round(prim, 2),
        })

    return jsonify({'basarili': True, 'veri': rows})


@raporlar_bp.route('/api/export')
def export_report():
    rapor_tipi = request.args.get('tip', 'personel')

    payload_map = {
        'personel': lambda: personel_raporu().get_json().get('veri', []),
        'toplama': lambda: toplama_raporu().get_json().get('veri', []),
        'urun': lambda: urun_raporu().get_json().get('veri', []),
        'iade': lambda: iade_analiz().get_json().get('veri', []),
        'gunluk_personel': lambda: gunluk_personel_raporu().get_json().get('veri', []),
        'prim': lambda: prim_raporu().get_json().get('veri', []),
    }

    if rapor_tipi not in payload_map:
        return jsonify({'basarili': False, 'mesaj': 'Geçersiz rapor tipi'}), 400

    payload = payload_map[rapor_tipi]()
    df = pd.DataFrame(payload)
    out = BytesIO()
    with pd.ExcelWriter(out, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Rapor')
    out.seek(0)

    return send_file(
        out,
        as_attachment=True,
        download_name=f'{rapor_tipi}_raporu.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


@raporlar_bp.route('/api/baglanti/siparisler', methods=['POST'])
def baglanti_siparisler():
    """Siparişler raporu — personel filtreli"""
    from database import Order as Siparis
    veri = request.get_json() or {}
    personel_id = veri.get('personel_id')

    sorgu = Siparis.query
    if personel_id:
        sorgu = sorgu.filter(Siparis.personel_id == int(personel_id))

    siparisler = sorgu.order_by(Siparis.tarih.desc()).all()

    liste = []
    for s in siparisler:
        liste.append({
            'tarih': s.tarih.strftime('%d.%m.%Y') if s.tarih else '—',
            'personel': s.personel.ad if s.personel else '—',
            'toplama': s.toplama.ad if s.toplama else '—',
            'siparis_no': s.siparis_no,
            'urun_kodu': (s.urun.ana_kod if s.urun else s.urun_kodu_ham) or '—',
            'beden': s.beden or '—',
            'durum': s.durum,
        })
    return jsonify({'basarili': True, 'siparisler': liste})


@raporlar_bp.route('/api/baglanti/urunler', methods=['POST'])
def baglanti_urunler():
    """Ürünler raporu — kayıt ayrıntıları üzerinden personel filtreli"""
    from database import KayitAyrinti, Kayit as KayitModel
    veri = request.get_json() or {}
    personel_id = veri.get('personel_id')

    sorgu = KayitAyrinti.query.join(KayitModel, KayitAyrinti.kayit_id == KayitModel.id)
    if personel_id:
        sorgu = sorgu.filter(KayitModel.personel_id == int(personel_id))

    ayrintilari = sorgu.order_by(KayitModel.tarih.desc()).all()

    liste = []
    for a in ayrintilari:
        k = a.kayit
        liste.append({
            'tarih': k.tarih,
            'personel': k.personel.ad if k.personel else '—',
            'urun_kodu': a.urun_kodu,
            'toplama': k.toplama.ad if k.toplama else '—',
            'beden': a.beden or '—',
            'adet': a.adet,
        })
    return jsonify({'basarili': True, 'urunler': liste})


@raporlar_bp.route('/api/baglanti/kayitlar', methods=['POST'])
def baglanti_kayitlar():
    """Kayıtlar raporu — personel filtreli"""
    from database import Kayit as KayitModel
    veri = request.get_json() or {}
    personel_id = veri.get('personel_id')

    sorgu = KayitModel.query
    if personel_id:
        sorgu = sorgu.filter(KayitModel.personel_id == int(personel_id))

    kayitlar = sorgu.all()
    kayitlar.sort(key=lambda k: (
        datetime.strptime(k.tarih, '%d.%m.%Y') if '.' in k.tarih else datetime.min
    ), reverse=True)

    liste = []
    for k in kayitlar:
        liste.append({
            'id': k.id,
            'tarih': k.tarih,
            'personel': k.personel.ad if k.personel else '—',
            'toplama': k.toplama.ad if k.toplama else '—',
            'siparis_sayisi': int(k.trendyol_siparis or 0),
            'senkronizasyon_sayisi': k.senkronizasyon_sayisi or 0,
            'senkronizasyon_tarihi': k.son_senkronizasyon.strftime('%d.%m.%Y %H:%M') if k.son_senkronizasyon else '—',
        })
    return jsonify({'basarili': True, 'kayitlar': liste})



