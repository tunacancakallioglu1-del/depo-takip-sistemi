# -*- coding: utf-8 -*-
"""
DEPO PERFORMANS VE İŞ TAKİP SİSTEMİ
Ana Flask Uygulaması
"""

from flask import Flask
from database import db, ilk_toplamalar_olustur
from config import config
import os

def create_app(config_name='development'):
    """Flask uygulamasını oluştur"""
    
    app = Flask(__name__)
    
    # Konfigürasyon yükle
    app.config.from_object(config[config_name])
    
    # Veritabanını başlat
    db.init_app(app)
    
    # Uygulama bağlamında veritabanı oluştur
    with app.app_context():
        db.create_all()
        ilk_toplamalar_olustur()
    
    # Rotaları kayıt et
    register_routes(app)
    
    return app


def register_routes(app):
    """Tüm rotaları kayıt et"""
    
    # Ana sayfa
    from routes.main import main_bp
    app.register_blueprint(main_bp)
    
    # Kayıtlar
    from routes.kayitlar import kayitlar_bp
    app.register_blueprint(kayitlar_bp)
    
    # Personeller
    from routes.personeller import personeller_bp
    app.register_blueprint(personeller_bp)
    
    # Toplamalar
    from routes.toplamalar import toplamalar_bp
    app.register_blueprint(toplamalar_bp)
    
    # Raporlar
    from routes.raporlar import raporlar_bp
    app.register_blueprint(raporlar_bp)


if __name__ == '__main__':
    app = create_app('development')
    
    print("""
    ╔══════════════════════════════════════════════════╗
    ║  DEPO PERFORMANS VE İŞ TAKİP SİSTEMİ            ║
    ╠══════════════════════════════════════════════════╣
    ║  🚀 Server Başlatılıyor...                       ║
    ║  📍 http://0.0.0.0:5000                          ║
    ║  🌐 Yerel Ağdan Erişim: http://SUNUCU_IP:5000   ║
    ╚══════════════════════════════════════════════════╝
    """)
    
    app.run(host='0.0.0.0', port=5000, debug=True)
