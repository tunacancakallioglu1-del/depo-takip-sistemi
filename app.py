# -*- coding: utf-8 -*-
"""
DEPO PERFORMANS VE İŞ TAKİP SİSTEMİ
Ana Flask Uygulaması
"""

from flask import Flask
from database import db, ilk_toplamalar_olustur
from config import config


def create_app(config_name='development'):
    """Flask uygulamasını oluştur"""

    app = Flask(__name__)
    app.config.from_object(config[config_name])

    db.init_app(app)

    with app.app_context():
        db.create_all()
        ilk_toplamalar_olustur()

    register_routes(app)
    return app


def register_routes(app):
    """Tüm rotaları kayıt et"""

    from routes.main import main_bp
    app.register_blueprint(main_bp)

    # v1.0 modülleri
    from routes.kayitlar import kayitlar_bp
    from routes.personeller import personeller_bp
    from routes.toplamalar import toplamalar_bp
    app.register_blueprint(kayitlar_bp)
    app.register_blueprint(personeller_bp)
    app.register_blueprint(toplamalar_bp)

    # v2.0 modülleri
    from routes.urunler import urunler_bp
    from routes.siparisler import siparisler_bp
    from routes.iadeler import iadeler_bp
    from routes.raporlar import raporlar_bp
    from routes.audit_log import audit_log_bp

    app.register_blueprint(urunler_bp)
    app.register_blueprint(siparisler_bp)
    app.register_blueprint(iadeler_bp)
    app.register_blueprint(raporlar_bp)
    app.register_blueprint(audit_log_bp)


if __name__ == '__main__':
    app = create_app('development')

    print("""
    ╔══════════════════════════════════════════════════╗
    ║  DEPO OPERASYON YÖNETİM SİSTEMİ                 ║
    ╠══════════════════════════════════════════════════╣
    ║  🚀 Server Başlatılıyor...                       ║
    ║  📍 http://0.0.0.0:5000                          ║
    ╚══════════════════════════════════════════════════╝
    """)

    app.run(host='0.0.0.0', port=5000, debug=True)
