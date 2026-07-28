# -*- coding: utf-8 -*-
"""Ana Sayfa ve Dashboard Rotaları"""

from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, jsonify
from sqlalchemy import func
from database import (
    db,
    Personel,
    Toplama,
    Kayit,
    Order,
    Product,
    Size,
    Return,
    kayit_ekle,
)

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
def index():
    """Dashboard"""
    today = datetime.utcnow().date()
    today_start = datetime.combine(today, datetime.min.time())

    daily_orders = db.session.query(func.count(func.distinct(Order.siparis_no))).filter(Order.tarih >= today_start).scalar() or 0
    daily_items = db.session.query(func.coalesce(func.sum(Order.adet), 0)).filter(Order.tarih >= today_start).scalar() or 0

    active_personnel = db.session.query(func.count(func.distinct(Order.personel_id))).filter(
        Order.tarih >= today_start,
        Order.personel_id.isnot(None)
    ).scalar() or 0

    last_7_days = []
    for offset in range(6, -1, -1):
        day = today - timedelta(days=offset)
        day_start = datetime.combine(day, datetime.min.time())
        day_end = day_start + timedelta(days=1)
        order_count = db.session.query(func.count(func.distinct(Order.siparis_no))).filter(
            Order.tarih >= day_start,
            Order.tarih < day_end
        ).scalar() or 0
        last_7_days.append({'date': day.strftime('%d.%m'), 'orders': order_count})

    metrics = {
        'daily_orders': daily_orders,
        'daily_items': int(daily_items),
        'active_personnel': active_personnel,
        'return_rate': _calculate_return_rate(),
    }

    # Hızlı erişim için veriler
    toplamalar = Toplama.query.order_by(Toplama.id).all()
    personeller = Personel.query.order_by(Personel.ad).all()
    urunler = Product.query.filter_by(durum=True).order_by(Product.ana_kod).all()
    bedenler = db.session.query(Size.beden).distinct().order_by(Size.beden).all()
    bedenler = [b[0] for b in bedenler]

    return render_template(
        'dashboard.html',
        metrics=metrics,
        last_7_days=last_7_days,
        toplamalar=toplamalar,
        personeller=personeller,
        urunler=urunler,
        bedenler=bedenler,
    )


def _calculate_return_rate():
    order_total = db.session.query(func.coalesce(func.sum(Order.adet), 0)).scalar() or 0
    return_total = db.session.query(func.coalesce(func.sum(Return.adet), 0)).scalar() or 0
    if order_total == 0:
        return 0
    return round((return_total / order_total) * 100, 2)


@main_bp.route('/api/dashboard-metrics')
def dashboard_metrics():
    today = datetime.utcnow().date()
    today_start = datetime.combine(today, datetime.min.time())
    return jsonify({
        'daily_orders': db.session.query(func.count(func.distinct(Order.siparis_no))).filter(Order.tarih >= today_start).scalar() or 0,
        'daily_items': int(db.session.query(func.coalesce(func.sum(Order.adet), 0)).filter(Order.tarih >= today_start).scalar() or 0),
        'active_personnel': db.session.query(func.count(func.distinct(Order.personel_id))).filter(
            Order.tarih >= today_start,
            Order.personel_id.isnot(None)
        ).scalar() or 0,
        'return_rate': _calculate_return_rate(),
    })


@main_bp.route('/api/kayit-ekle', methods=['POST'])
def api_kayit_ekle():
    """v1.0 uyumluluk için AJAX ile kayıt ekle"""

    try:
        veri = request.json

        if not all([veri.get('tarih'), veri.get('personel_id'), veri.get('toplama_id')]):
            return jsonify({'basarili': False, 'mesaj': 'Lütfen tüm zorunlu alanları doldurun!'}), 400

        tarih_parts = veri['tarih'].split('-')
        tarih_formatted = f"{tarih_parts[2]}.{tarih_parts[1]}.{tarih_parts[0]}"

        sonuc = kayit_ekle(
            tarih=tarih_formatted,
            personel_id=int(veri['personel_id']),
            toplama_id=int(veri['toplama_id']),
            trendyol_siparis=float(veri.get('trendyol_siparis', 0)) or 0,
            trendyol_fatura=float(veri.get('trendyol_fatura', 0)) or 0,
            diger_pazar=float(veri.get('diger_pazar', 0)) or 0,
            not_alan=veri.get('not', '')
        )

        return jsonify(sonuc)

    except Exception as e:
        return jsonify({'basarili': False, 'mesaj': f'Hata: {str(e)}'}), 500
