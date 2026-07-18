# -*- coding: utf-8 -*-
"""
Uygulama Konfigürasyonu
"""

import os

class Config:
    """
    Temel Konfigürasyon
    """
    
    # Flask Ayarları
    SECRET_KEY = 'depo-takip-sistemi-2024'
    DEBUG = True
    
    # Veritabanı
    SQLALCHEMY_DATABASE_URI = 'sqlite:///depo.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Çalışma Dizini
    BASEDIR = os.path.abspath(os.path.dirname(__file__))
    
    # Export Dizini
    EXPORT_FOLDER = os.path.join(BASEDIR, 'exports')
    if not os.path.exists(EXPORT_FOLDER):
        os.makedirs(EXPORT_FOLDER)

# Çalışma Modu
class DevelopmentConfig(Config):
    """Geliştirme Modu"""
    DEBUG = True

class ProductionConfig(Config):
    """Üretim Modu"""
    DEBUG = False

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
