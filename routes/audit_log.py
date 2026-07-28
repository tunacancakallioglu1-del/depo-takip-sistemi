# -*- coding: utf-8 -*-
"""Audit log rotaları"""

from flask import Blueprint, render_template, request, jsonify
from database import AuditLog

audit_log_bp = Blueprint('audit_log', __name__, url_prefix='/audit-log')


@audit_log_bp.route('/')
def index():
    return render_template('audit_log.html')


@audit_log_bp.route('/api/list')
def api_list():
    page = max(int(request.args.get('page', 1)), 1)
    per_page = min(max(int(request.args.get('per_page', 30)), 1), 100)
    pagination = AuditLog.query.order_by(AuditLog.tarih.desc()).paginate(page=page, per_page=per_page, error_out=False)

    logs = []
    for log in pagination.items:
        logs.append({
            'id': log.id,
            'kullanici_id': log.kullanici_id,
            'islem': log.islem,
            'tablo': log.tablo,
            'kayit_id': log.kayit_id,
            'sonuc': log.sonuc,
            'tarih': log.tarih.strftime('%Y-%m-%d %H:%M:%S'),
        })

    return jsonify({
        'basarili': True,
        'kayitlar': logs,
        'toplam': pagination.total,
        'sayfa': page,
        'toplam_sayfa': pagination.pages,
    })
