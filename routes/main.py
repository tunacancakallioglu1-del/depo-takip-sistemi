# -*- coding: utf-8 -*-
"""
Ana Sayfa Rotaları
"""

from flask import Blueprint, render_template, request, jsonify
from database import db, Personel, Toplama, Kayit, kayit_ekle
from datetime import datetime

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
def index():
    """Ana sayfa"""
    
    personeller = Personel.query.all()
    toplamalar = Toplama.query.all()
    bugün = datetime.now().strftime('%Y-%m-%d')
    
    return render_template('index.html', 
                         personeller=personeller, 
                         toplamalar=toplamalar,
                         bugün=bugün)


@main_bp.route('/api/kayit-ekle', methods=['POST'])
def api_kayit_ekle():
    """AJAX ile kayıt ekle"""
    
    try:
        veri = request.json
        
        # Form verilerini kontrol et
        if not all([veri.get('tarih'), veri.get('personel_id'), veri.get('toplama_id')]):
            return jsonify({'basarili': False, 'mesaj': 'Lütfen tüm zorunlu alanları doldurun!'}), 400
        
        # Tarih formatını dönüştür (YYYY-MM-DD -> DD.MM.YYYY)
        tarih_parts = veri['tarih'].split('-')
        tarih_formatted = f"{tarih_parts[2]}.{tarih_parts[1]}.{tarih_parts[0]}"
        
        # Kayıt ekle
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
