# -*- coding: utf-8 -*-
"""
Personeller Rotaları
"""

from flask import Blueprint, render_template, request, jsonify
from database import db, Personel, personel_ekle, personel_sil

personeller_bp = Blueprint('personeller', __name__, url_prefix='/personeller')


@personeller_bp.route('/')
def lista():
    """Personeller listesi"""
    
    personeller = Personel.query.all()
    
    return render_template('personeller.html', personeller=personeller)


@personeller_bp.route('/api/list', methods=['GET'])
def api_list():
    """AJAX ile personelleri getir"""
    
    personeller = Personel.query.all()
    
    return jsonify({
        'basarili': True,
        'personeller': [p.to_dict() for p in personeller],
        'toplam': len(personeller)
    })


@personeller_bp.route('/api/ekle', methods=['POST'])
def api_ekle():
    """AJAX ile personel ekle"""
    
    try:
        veri = request.json
        
        if not veri.get('ad') or veri['ad'].strip() == '':
            return jsonify({'basarili': False, 'mesaj': 'Personel adı boş olamaz!'}), 400
        
        sonuc = personel_ekle(veri['ad'].strip())
        
        return jsonify(sonuc)
    
    except Exception as e:
        return jsonify({'basarili': False, 'mesaj': f'Hata: {str(e)}'}), 500


@personeller_bp.route('/api/guncelle/<int:id>', methods=['PUT'])
def api_guncelle(id):
    """AJAX ile personel adı güncelle"""
    try:
        veri = request.json or {}
        ad = str(veri.get('ad', '')).strip()
        if not ad:
            return jsonify({'basarili': False, 'mesaj': 'Ad boş olamaz!'}), 400

        personel = Personel.query.get(id)
        if not personel:
            return jsonify({'basarili': False, 'mesaj': 'Personel bulunamadı!'}), 404

        if Personel.query.filter(Personel.ad == ad, Personel.id != id).first():
            return jsonify({'basarili': False, 'mesaj': 'Bu isimde başka bir personel var!'}), 409

        personel.ad = ad
        db.session.commit()
        return jsonify({'basarili': True, 'mesaj': 'Personel güncellendi!'})
    except Exception:
        return jsonify({'basarili': False, 'mesaj': 'İşlem sırasında bir hata oluştu.'}), 500


@personeller_bp.route('/api/ara', methods=['GET'])
def api_ara():
    """İsim ile personel ara (autocomplete)"""
    q = request.args.get('q', '').strip()
    if len(q) < 1:
        return jsonify({'personeller': []})
    personeller = Personel.query.filter(Personel.ad.ilike(f'%{q}%')).order_by(Personel.ad).all()
    return jsonify({'personeller': [{'id': p.id, 'ad': p.ad} for p in personeller]})


@personeller_bp.route('/api/sil/<int:id>', methods=['DELETE'])
def api_sil(id):
    """AJAX ile personel sil"""
    
    try:
        sonuc = personel_sil(id)
        return jsonify(sonuc)
    
    except Exception as e:
        return jsonify({'basarili': False, 'mesaj': f'Hata: {str(e)}'}), 500
