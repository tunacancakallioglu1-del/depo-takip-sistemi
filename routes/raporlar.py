# -*- coding: utf-8 -*-
"""Raporlama rotaları"""

from io import BytesIO
from datetime import datetime
import pandas as pd
from flask import Blueprint, render_template, request, jsonify, send_file
from sqlalchemy import func
from database import db, Order, Return, Product, Personel, Toplama, Kayit

raporlar_bp = Blueprint('raporlar', __name__, url_prefix='/raporlar')


def _date_filters(query, column):
    baslangic = request.args.get('baslangic')
    bitis = request.args.get('bitis')
    if baslangic:
        query = query.filter(column >= datetime.strptime(baslangic, '%Y-%m-%d'))
    if bitis:
        query = query.filter(column <= datetime.strptime(bitis, '%Y-%m-%d'))
    return query


@raporlar_bp.route('/')
def index():
    return render_template('raporlar.html')


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
    """Ürünler raporu — kayıt ayıntıları üzerinden personel filtreli"""
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
