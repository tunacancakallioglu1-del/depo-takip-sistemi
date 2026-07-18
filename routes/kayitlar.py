# -*- coding: utf-8 -*-
"""
Kayıtlar Rotaları
"""

from flask import Blueprint, render_template, request, jsonify
from database import db, Kayit, Personel, Toplama, kayit_guncelle, kayit_sil

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


@kayitlar_bp.route('/api/sil/<int:id>', methods=['DELETE'])
def api_sil(id):
    """AJAX ile kayıt sil"""
    
    try:
        sonuc = kayit_sil(id)
        return jsonify(sonuc)
    
    except Exception as e:
        return jsonify({'basarili': False, 'mesaj': f'Hata: {str(e)}'}), 500
