# -*- coding: utf-8 -*-
"""
Veritabanı Modelleri ve İşlemleri
"""

from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

# ============================================================================
# PERSONELLER TABLOSU
# ============================================================================

class Personel(db.Model):
    """Personel Modeli"""
    __tablename__ = 'personeller'
    
    id = db.Column(db.Integer, primary_key=True)
    ad = db.Column(db.String(100), nullable=False, unique=True)
    eklenme_tarihi = db.Column(db.DateTime, default=datetime.now)
    
    # İlişkiler
    kayitlar = db.relationship('Kayit', backref='personel', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Personel {self.ad}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'ad': self.ad,
            'eklenme_tarihi': self.eklenme_tarihi.strftime('%d.%m.%Y')
        }


# ============================================================================
# TOPLAMALAR TABLOSU
# ============================================================================

class Toplama(db.Model):
    """Toplama Modeli"""
    __tablename__ = 'toplamalar'
    
    id = db.Column(db.Integer, primary_key=True)
    ad = db.Column(db.String(100), nullable=False, unique=True)
    eklenme_tarihi = db.Column(db.DateTime, default=datetime.now)
    
    # İlişkiler
    kayitlar = db.relationship('Kayit', backref='toplama', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Toplama {self.ad}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'ad': self.ad,
            'eklenme_tarihi': self.eklenme_tarihi.strftime('%d.%m.%Y')
        }


# ============================================================================
# KAYITLAR TABLOSU
# ============================================================================

class Kayit(db.Model):
    """Kayıt Modeli"""
    __tablename__ = 'kayitlar'
    
    id = db.Column(db.Integer, primary_key=True)
    tarih = db.Column(db.String(10), nullable=False)
    personel_id = db.Column(db.Integer, db.ForeignKey('personeller.id'), nullable=False)
    toplama_id = db.Column(db.Integer, db.ForeignKey('toplamalar.id'), nullable=False)
    trendyol_siparis = db.Column(db.Float, default=0)
    trendyol_fatura = db.Column(db.Float, default=0)
    diger_pazar = db.Column(db.Float, default=0)
    not_alan = db.Column(db.Text, default='')
    eklenme_tarihi = db.Column(db.DateTime, default=datetime.now)
    
    def __repr__(self):
        return f'<Kayit {self.tarih}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'tarih': self.tarih,
            'personel': self.personel.ad,
            'personel_id': self.personel_id,
            'toplama': self.toplama.ad,
            'toplama_id': self.toplama_id,
            'trendyol_siparis': self.trendyol_siparis,
            'trendyol_fatura': self.trendyol_fatura,
            'diger_pazar': self.diger_pazar,
            'not': self.not_alan
        }


# ============================================================================
# VERİTABANI İŞLEMLERİ
# ============================================================================

def ilk_toplamalar_olustur():
    """İlk açılışta Toplama 1-11 oluştur"""
    
    if Toplama.query.first() is None:
        for i in range(1, 12):
            toplama = Toplama(ad=f'Toplama {i}')
            db.session.add(toplama)
        
        db.session.commit()
        print("✓ Otomatik Toplamalar (1-11) oluşturuldu")


def personel_ekle(ad):
    """Yeni personel ekle"""
    
    if Personel.query.filter_by(ad=ad).first():
        return {'basarili': False, 'mesaj': 'Bu personel zaten var!'}
    
    personel = Personel(ad=ad)
    db.session.add(personel)
    db.session.commit()
    
    return {'basarili': True, 'mesaj': 'Personel başarıyla eklendi!', 'id': personel.id}


def personel_sil(id):
    """Personel sil"""
    
    personel = Personel.query.get(id)
    if not personel:
        return {'basarili': False, 'mesaj': 'Personel bulunamadı!'}
    
    db.session.delete(personel)
    db.session.commit()
    
    return {'basarili': True, 'mesaj': 'Personel silindi!'}


def toplama_ekle(ad):
    """Yeni toplama ekle"""
    
    if Toplama.query.filter_by(ad=ad).first():
        return {'basarili': False, 'mesaj': 'Bu toplama zaten var!'}
    
    toplama = Toplama(ad=ad)
    db.session.add(toplama)
    db.session.commit()
    
    return {'basarili': True, 'mesaj': 'Toplama başarıyla eklendi!', 'id': toplama.id}


def toplama_sil(id):
    """Toplama sil"""
    
    toplama = Toplama.query.get(id)
    if not toplama:
        return {'basarili': False, 'mesaj': 'Toplama bulunamadı!'}
    
    db.session.delete(toplama)
    db.session.commit()
    
    return {'basarili': True, 'mesaj': 'Toplama silindi!'}


def kayit_ekle(tarih, personel_id, toplama_id, trendyol_siparis=0, 
               trendyol_fatura=0, diger_pazar=0, not_alan=''):
    """Yeni kayıt ekle"""
    
    kayit = Kayit(
        tarih=tarih,
        personel_id=personel_id,
        toplama_id=toplama_id,
        trendyol_siparis=trendyol_siparis,
        trendyol_fatura=trendyol_fatura,
        diger_pazar=diger_pazar,
        not_alan=not_alan
    )
    
    db.session.add(kayit)
    db.session.commit()
    
    return {'basarili': True, 'mesaj': 'Kayıt başarıyla eklendi!', 'id': kayit.id}


def kayit_guncelle(id, tarih, personel_id, toplama_id, trendyol_siparis=0,
                   trendyol_fatura=0, diger_pazar=0, not_alan=''):
    """Kayıt güncelle"""
    
    kayit = Kayit.query.get(id)
    if not kayit:
        return {'basarili': False, 'mesaj': 'Kayıt bulunamadı!'}
    
    kayit.tarih = tarih
    kayit.personel_id = personel_id
    kayit.toplama_id = toplama_id
    kayit.trendyol_siparis = trendyol_siparis
    kayit.trendyol_fatura = trendyol_fatura
    kayit.diger_pazar = diger_pazar
    kayit.not_alan = not_alan
    
    db.session.commit()
    
    return {'basarili': True, 'mesaj': 'Kayıt başarıyla güncellendi!'}


def kayit_sil(id):
    """Kayıt sil"""
    
    kayit = Kayit.query.get(id)
    if not kayit:
        return {'basarili': False, 'mesaj': 'Kayıt bulunamadı!'}
    
    db.session.delete(kayit)
    db.session.commit()
    
    return {'basarili': True, 'mesaj': 'Kayıt silindi!'}
