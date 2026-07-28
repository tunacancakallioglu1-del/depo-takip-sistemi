# -*- coding: utf-8 -*-
"""Uygulama Konfigürasyonu"""

import os


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'depo-takip-sistemi-dev-key')
    DEBUG = True

    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///depo.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    BASEDIR = os.path.abspath(os.path.dirname(__file__))
    EXPORT_FOLDER = os.path.join(BASEDIR, 'exports')
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024

    if not os.path.exists(EXPORT_FOLDER):
        os.makedirs(EXPORT_FOLDER)


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
