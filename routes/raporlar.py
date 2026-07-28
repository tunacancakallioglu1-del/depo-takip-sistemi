# -*- coding: utf-8 -*-
"""Raporlama rotaları"""

from io import BytesIO
from datetime import datetime
import pandas as pd
from flask import Blueprint, render_template, request, jsonify, send_file
from sqlalchemy import func
from database import db, Order, Return, Product, Personel, Toplama

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


@raporlar_bp.route('/api/export')
def export_report():
    rapor_tipi = request.args.get('tip', 'personel')
    endpoint_map = {
        'personel': personel_raporu,
        'toplama': toplama_raporu,
        'urun': urun_raporu,
        'iade': iade_analiz,
    }

    if rapor_tipi not in endpoint_map:
        return jsonify({'basarili': False, 'mesaj': 'Geçersiz rapor tipi'}), 400

    payload = endpoint_map[rapor_tipi]().json.get('veri', [])
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
