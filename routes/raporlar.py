# -*- coding: utf-8 -*-
"""Raporlama rotaları"""

import json
import zipfile
from io import BytesIO
from datetime import datetime
import pandas as pd
from flask import Blueprint, render_template, request, jsonify, send_file
from sqlalchemy import func
from database import db, Order, Return, Product, Personel, Toplama, Kayit, ExcelUpload, AuditLog

raporlar_bp = Blueprint('raporlar', __name__, url_prefix='/raporlar')


@raporlar_bp.route('/')
def index():
    return render_template('raporlar.html')


def _safe_json(value):
    if not value:
        return {}
    try:
        return json.loads(value)
    except Exception:
        return {}


def _upload_key(modul, upload_id):
    return f'{modul}:{upload_id}'


def _upload_control_map(keys):
    if not keys:
        return {}

    logs = AuditLog.query.filter(
        AuditLog.tablo == 'excel_upload_controls',
        AuditLog.islem == 'upload_kontrol',
        AuditLog.kayit_id.in_(keys),
    ).order_by(AuditLog.id.desc()).all()

    result = {}
    for log in logs:
        if log.kayit_id in result:
            continue
        payload = _safe_json(log.yeni_deger)
        result[log.kayit_id] = {
            'durum': payload.get('durum', 'Kontrol Edilmedi'),
            'hata_sebebi': payload.get('hata_sebebi', ''),
        }
    return result


def _build_upload_excel(upload):
    out = BytesIO()

    if upload.modul == 'siparis':
        rows = Order.query.filter_by(excel_yukleme_id=upload.id).order_by(Order.id.asc()).all()
        payload = [{
            'Siparis No': r.siparis_no,
            'Tarih': r.tarih.strftime('%Y-%m-%d'),
            'Urun Kodu': r.urun.ana_kod if r.urun else '',
            'Beden': r.beden or '',
            'Adet': r.adet,
            'Kargo Kodu': r.kargo_kodu or '',
            'Termin Tarihi': r.termin_tarihi.strftime('%Y-%m-%d') if r.termin_tarihi else '',
            'Personel': r.personel.ad if r.personel else '',
        } for r in rows]
    elif upload.modul == 'iade':
        rows = Return.query.filter_by(excel_yukleme_id=upload.id).order_by(Return.id.asc()).all()
        payload = [{
            'Siparis No': r.siparis_no,
            'Tarih': r.tarih.strftime('%Y-%m-%d'),
            'Urun Kodu': r.urun.ana_kod if r.urun else '',
            'Beden': r.beden or '',
            'Adet': r.adet,
            'Sebep': r.sebebi or '',
        } for r in rows]
    else:
        payload = []

    with pd.ExcelWriter(out, engine='openpyxl') as writer:
        pd.DataFrame(payload).to_excel(writer, index=False, sheet_name='Yukleme')
    out.seek(0)
    return out


@raporlar_bp.route('/api/yukleme-raporu', methods=['GET'])
def yukleme_raporu():
    modul = str(request.args.get('modul', '')).strip()
    query = ExcelUpload.query
    if modul:
        query = query.filter_by(modul=modul)

    uploads = query.order_by(ExcelUpload.yukleme_tarihi.desc()).all()
    keys = [_upload_key(u.modul, u.id) for u in uploads]
    kontrol_map = _upload_control_map(keys)

    rows = []
    for u in uploads:
        key = _upload_key(u.modul, u.id)
        kontrol = kontrol_map.get(key, {'durum': 'Kontrol Edilmedi', 'hata_sebebi': ''})
        rows.append({
            'id': u.id,
            'modul': u.modul,
            'dosya_adi': u.dosya_adi,
            'yukleme_tarihi': u.yukleme_tarihi.strftime('%Y-%m-%d %H:%M'),
            'toplam_satir': u.toplam_satir,
            'basarili': u.basarili,
            'basarisiz': u.basarisiz,
            'kontrol_durumu': kontrol['durum'],
            'hata_sebebi': kontrol['hata_sebebi'],
        })

    return jsonify({'basarili': True, 'veri': rows})


@raporlar_bp.route('/api/yukleme-raporu/<modul>/<int:upload_id>/kontrol', methods=['PUT'])
def yukleme_kontrol(modul, upload_id):
    upload = ExcelUpload.query.filter_by(id=upload_id, modul=modul).first_or_404()
    data = request.json or {}

    durum = str(data.get('durum', 'Kontrol Edilmedi')).strip()
    if durum not in ('Kontrol Edildi', 'Kontrol Edilmedi'):
        return jsonify({'basarili': False, 'mesaj': 'Geçersiz durum'}), 400

    hata_sebebi = str(data.get('hata_sebebi', '')).strip()
    key = _upload_key(modul, upload.id)

    log = AuditLog(
        kullanici_id='system',
        islem='upload_kontrol',
        tablo='excel_upload_controls',
        kayit_id=key,
        yeni_deger=json.dumps({'durum': durum, 'hata_sebebi': hata_sebebi}, ensure_ascii=False),
        sonuc='basarili',
    )
    db.session.add(log)
    db.session.commit()
    return jsonify({'basarili': True, 'mesaj': 'Kontrol durumu güncellendi'})


@raporlar_bp.route('/api/tanimsiz-rapor-excel', methods=['GET'])
def tanimsiz_rapor_excel():
    modul = str(request.args.get('modul', '')).strip()
    upload_id = request.args.get('upload_id')
    if not modul or not upload_id:
        return jsonify({'basarili': False, 'mesaj': 'modul ve upload_id zorunludur'}), 400

    key = _upload_key(modul, int(upload_id))
    log = AuditLog.query.filter_by(
        tablo='excel_uploads',
        islem='excel_tanimsiz_rapor',
        kayit_id=key,
    ).order_by(AuditLog.id.desc()).first()

    payload = _safe_json(log.yeni_deger if log else None)
    urunler = payload.get('tanimsiz_urunler', []) or []
    bedenler = payload.get('tanimsiz_bedenler', []) or []

    if not urunler and not bedenler:
        return jsonify({'basarili': False, 'mesaj': 'Tanımsız kayıt bulunamadı'}), 404

    out = BytesIO()
    with pd.ExcelWriter(out, engine='openpyxl') as writer:
        if urunler:
            df_urun = pd.DataFrame(urunler)
            if 'kod' in df_urun.columns:
                df_urun.rename(columns={'kod': 'urun_kodu'}, inplace=True)
            df_urun['hata_sebebi'] = ''
            df_urun.to_excel(writer, index=False, sheet_name='TanimsizUrun')

        if bedenler:
            df_beden = pd.DataFrame(bedenler)
            if 'kod' in df_beden.columns:
                df_beden.rename(columns={'kod': 'urun_kodu'}, inplace=True)
            df_beden['hata_sebebi'] = ''
            df_beden.to_excel(writer, index=False, sheet_name='TanimsizBeden')

    out.seek(0)
    return send_file(
        out,
        as_attachment=True,
        download_name=f'tanimsiz_rapor_{modul}_{upload_id}.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )


@raporlar_bp.route('/api/yukleme-excel-indir/<modul>/<int:upload_id>', methods=['GET'])
def yukleme_excel_indir(modul, upload_id):
    upload = ExcelUpload.query.filter_by(modul=modul, id=upload_id).first_or_404()
    out = _build_upload_excel(upload)
    base_name = upload.dosya_adi.rsplit('.', 1)[0]
    return send_file(
        out,
        as_attachment=True,
        download_name=f'{base_name}_yeniden_yukleme.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )


@raporlar_bp.route('/api/tum-excel-indir', methods=['GET'])
def tum_excel_indir():
    modul = str(request.args.get('modul', '')).strip()
    query = ExcelUpload.query
    if modul:
        query = query.filter_by(modul=modul)

    uploads = query.order_by(ExcelUpload.yukleme_tarihi.desc()).all()
    if not uploads:
        return jsonify({'basarili': False, 'mesaj': 'Yükleme geçmişi bulunamadı'}), 404

    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for upload in uploads:
            if upload.modul not in ('siparis', 'iade'):
                continue
            excel_stream = _build_upload_excel(upload)
            dosya_adi = f"{upload.modul}_{upload.id}_{upload.yukleme_tarihi.strftime('%Y%m%d_%H%M')}.xlsx"
            zf.writestr(dosya_adi, excel_stream.getvalue())

    zip_buffer.seek(0)
    return send_file(
        zip_buffer,
        as_attachment=True,
        download_name='tum_excel_yukleme_gecmisi.zip',
        mimetype='application/zip',
    )


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
