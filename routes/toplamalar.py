# -*- coding: utf-8 -*-
"""
Toplamalar Rotaları
"""

from flask import Blueprint, render_template, request, jsonify
from database import db, Toplama, toplama_ekle, toplama_sil

toplamalar_bp = Blueprint('toplamalar', __name__, url_prefix='/toplamalar')


@toplamalar_bp.route('/')
def lista():
    """Toplamalar listesi"""
    
    toplamalar = Toplama.query.all()
    
    return render_template('toplamalar.html', toplamalar=toplamalar)


@toplamalar_bp.route('/api/list', methods=['GET'])
def api_list():
    """AJAX ile toplamaları getir"""
    
    toplamalar = Toplama.query.all()
    
    return jsonify({
        'basarili': True,
        'toplamalar': [t.to_dict() for t in toplamalar],
        'toplam': len(toplamalar)
    })


@toplamalar_bp.route('/api/ekle', methods=['POST'])
def api_ekle():
    """AJAX ile toplama ekle"""
    
    try:
        veri = request.json
        
        if not veri.get('ad') or veri['ad'].strip() == '':
            return jsonify({'basarili': False, 'mesaj': 'Toplama adı boş olamaz!'}), 400
        
        sonuc = toplama_ekle(veri['ad'].strip())
        
        return jsonify(sonuc)
    
    except Exception as e:
        return jsonify({'basarili': False, 'mesaj': f'Hata: {str(e)}'}), 500


@toplamalar_bp.route('/api/sil/<int:id>', methods=['DELETE'])
def api_sil(id):
    """AJAX ile toplama sil"""
    
    try:
        sonuc = toplama_sil(id)
        return jsonify(sonuc)
    
    except Exception as e:
        return jsonify({'basarili': False, 'mesaj': f'Hata: {str(e)}'}), 500
