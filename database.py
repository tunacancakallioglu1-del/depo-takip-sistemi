# -*- coding: utf-8 -*-
"""
Veritabanı Modelleri ve İşlemleri
"""

from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from sqlalchemy import text


db = SQLAlchemy()


# ============================================================================
# MEVCUT TABLOLAR (v1.0)
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
    senkronizasyon_sayisi = db.Column(db.Integer, default=0, nullable=False)
    son_senkronizasyon = db.Column(db.DateTime, nullable=True)

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
# YENİ MODÜL TABLOLARI (v2.0)
# ============================================================================

class Product(db.Model):
    __tablename__ = 'products'
    __table_args__ = (
        db.UniqueConstraint('ana_kod', 'marka', name='uq_product_ana_kod_marka'),
        db.Index('ix_product_ana_kod', 'ana_kod'),
        db.Index('ix_product_toplama', 'toplama_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    ana_kod = db.Column(db.String(120), nullable=False)
    aciklama = db.Column(db.String(255), nullable=False)
    marka = db.Column(db.String(120), nullable=False)
    toplama_id = db.Column(db.Integer, db.ForeignKey('toplamalar.id'), nullable=False)
    beden_ayrimi = db.Column(db.Boolean, default=False, nullable=False)
    durum = db.Column(db.Boolean, default=True, nullable=False)
    olusturulma_tarihi = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    son_guncelleme_tarihi = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    guncelleyen_kullanici = db.Column(db.String(120), default='system', nullable=False)

    toplama = db.relationship('Toplama', backref=db.backref('products', lazy=True))
    sizes = db.relationship('Size', backref='product', lazy=True, cascade='all, delete-orphan')
    code_mappings = db.relationship('CodeMapping', backref='product', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'ana_kod': self.ana_kod,
            'aciklama': self.aciklama,
            'marka': self.marka,
            'toplama_id': self.toplama_id,
            'toplama': self.toplama.ad if self.toplama else None,
            'beden_ayrimi': self.beden_ayrimi,
            'durum': self.durum,
        }


class Size(db.Model):
    __tablename__ = 'sizes'
    __table_args__ = (
        db.UniqueConstraint('product_id', 'beden', name='uq_size_product_beden'),
        db.Index('ix_size_product', 'product_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    beden = db.Column(db.String(50), nullable=False)
    toplama_id = db.Column(db.Integer, db.ForeignKey('toplamalar.id'), nullable=False)

    toplama = db.relationship('Toplama', backref=db.backref('sizes', lazy=True))

    def to_dict(self):
        return {
            'id': self.id,
            'product_id': self.product_id,
            'beden': self.beden,
            'toplama_id': self.toplama_id,
            'toplama': self.toplama.ad if self.toplama else None,
        }


class CodeMapping(db.Model):
    __tablename__ = 'code_mappings'
    __table_args__ = (
        db.UniqueConstraint('kaynak_kod', name='uq_code_mapping_kaynak_kod'),
        db.Index('ix_code_mapping_kaynak_kod', 'kaynak_kod'),
    )

    id = db.Column(db.Integer, primary_key=True)
    kaynak_kod = db.Column(db.String(120), nullable=False)
    hedef_urun_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'kaynak_kod': self.kaynak_kod,
            'hedef_urun_id': self.hedef_urun_id,
            'hedef_urun_kod': self.product.ana_kod if self.product else None,
        }


class Order(db.Model):
    __tablename__ = 'orders'
    __table_args__ = (
        db.Index('ix_order_siparis_no', 'siparis_no'),
        db.Index('ix_order_tarih', 'tarih'),
        db.Index('ix_order_toplama', 'toplama_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    siparis_no = db.Column(db.String(120), nullable=False)
    tarih = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    urun_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=True)
    urun_kodu_ham = db.Column(db.String(120), nullable=True)
    beden = db.Column(db.String(50), nullable=True)
    adet = db.Column(db.Integer, nullable=False, default=1)
    toplama_id = db.Column(db.Integer, db.ForeignKey('toplamalar.id'), nullable=True)
    personel_id = db.Column(db.Integer, db.ForeignKey('personeller.id'), nullable=True)
    kargo_kodu = db.Column(db.String(120), nullable=True)
    termin_tarihi = db.Column(db.Date, nullable=True)
    durum = db.Column(db.String(50), default='BEKLEMEDE', nullable=False)
    hata_sebebi = db.Column(db.Text, nullable=True)
    excel_yukleme_id = db.Column(db.Integer, db.ForeignKey('excel_uploads.id'), nullable=True)
    senkronize_edildi = db.Column(db.Boolean, default=False, nullable=False)
    senkronize_tarihi = db.Column(db.DateTime, nullable=True)
    referans_kayit_id = db.Column(db.Integer, nullable=True)

    urun = db.relationship('Product', backref=db.backref('orders', lazy=True))
    toplama = db.relationship('Toplama', backref=db.backref('orders', lazy=True))
    personel = db.relationship('Personel', backref=db.backref('orders', lazy=True))


class Return(db.Model):
    __tablename__ = 'returns'
    __table_args__ = (
        db.Index('ix_return_siparis_no', 'siparis_no'),
        db.Index('ix_return_tarih', 'tarih'),
        db.Index('ix_return_toplama', 'toplama_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    siparis_no = db.Column(db.String(120), nullable=False)
    tarih = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    urun_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    beden = db.Column(db.String(50), nullable=True)
    adet = db.Column(db.Integer, nullable=False, default=1)
    sebebi = db.Column(db.String(255), nullable=True)
    toplama_id = db.Column(db.Integer, db.ForeignKey('toplamalar.id'), nullable=False)
    excel_yukleme_id = db.Column(db.Integer, db.ForeignKey('excel_uploads.id'), nullable=True)

    urun = db.relationship('Product', backref=db.backref('returns', lazy=True))
    toplama = db.relationship('Toplama', backref=db.backref('returns', lazy=True))


class ExcelUpload(db.Model):
    __tablename__ = 'excel_uploads'
    __table_args__ = (
        db.UniqueConstraint('dosya_hash', name='uq_excel_upload_hash'),
        db.Index('ix_excel_upload_tarih', 'yukleme_tarihi'),
    )

    id = db.Column(db.Integer, primary_key=True)
    modul = db.Column(db.String(50), nullable=False)
    dosya_adi = db.Column(db.String(255), nullable=False)
    dosya_hash = db.Column(db.String(128), nullable=False)
    yukleme_tarihi = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    kullanici_id = db.Column(db.String(120), default='system', nullable=False)
    toplam_satir = db.Column(db.Integer, default=0, nullable=False)
    basarili = db.Column(db.Integer, default=0, nullable=False)
    basarisiz = db.Column(db.Integer, default=0, nullable=False)
    durum = db.Column(db.String(50), default='YUKLENDI', nullable=False)
    kontrol_tarihi = db.Column(db.DateTime, nullable=True)

    orders = db.relationship('Order', backref='excel_upload', lazy=True)
    returns = db.relationship('Return', backref='excel_upload', lazy=True)


class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    __table_args__ = (db.Index('ix_audit_tarih', 'tarih'),)

    id = db.Column(db.Integer, primary_key=True)
    kullanici_id = db.Column(db.String(120), default='system', nullable=False)
    islem = db.Column(db.String(120), nullable=False)
    tablo = db.Column(db.String(120), nullable=False)
    kayit_id = db.Column(db.String(120), nullable=True)
    eski_deger = db.Column(db.Text, nullable=True)
    yeni_deger = db.Column(db.Text, nullable=True)
    sonuc = db.Column(db.String(50), default='basarili', nullable=False)
    tarih = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


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


def veritabani_migrasyonu():
    """Mevcut veritabanına yeni sütunlar ekle (var olanları atla)"""
    from sqlalchemy import inspect as sa_inspect

    inspector = sa_inspect(db.engine)
    existing_tables = inspector.get_table_names()

    with db.engine.connect() as conn:
        # orders tablosunu yeniden oluştur (nullable urun_id/toplama_id + yeni sütunlar)
        if 'orders' in existing_tables:
            orders_cols = [c['name'] for c in inspector.get_columns('orders')]
            # Eğer urun_kodu_ham sütunu yoksa tam migration yap
            if 'urun_kodu_ham' not in orders_cols:
                has_senkronize = 'senkronize_edildi' in orders_cols
                has_referans = 'referans_kayit_id' in orders_cols
                has_kargo = 'kargo_kodu' in orders_cols
                has_termin = 'termin_tarihi' in orders_cols

                conn.execute(text('''
                    CREATE TABLE orders_v3_new (
                        id INTEGER NOT NULL PRIMARY KEY,
                        siparis_no VARCHAR(120) NOT NULL,
                        tarih DATETIME NOT NULL,
                        urun_id INTEGER REFERENCES products(id),
                        urun_kodu_ham VARCHAR(120),
                        beden VARCHAR(50),
                        adet INTEGER NOT NULL DEFAULT 1,
                        toplama_id INTEGER REFERENCES toplamalar(id),
                        personel_id INTEGER REFERENCES personeller(id),
                        kargo_kodu VARCHAR(120),
                        termin_tarihi DATE,
                        durum VARCHAR(50) NOT NULL DEFAULT 'BEKLEMEDE',
                        hata_sebebi TEXT,
                        excel_yukleme_id INTEGER REFERENCES excel_uploads(id),
                        senkronize_edildi BOOLEAN NOT NULL DEFAULT 0,
                        senkronize_tarihi DATETIME,
                        referans_kayit_id INTEGER
                    )
                '''))

                kargo_expr = 'kargo_kodu' if has_kargo else 'NULL'
                termin_expr = 'termin_tarihi' if has_termin else 'NULL'
                senkronize_expr = 'senkronize_edildi, senkronize_tarihi' if has_senkronize else '0, NULL'
                referans_expr = 'referans_kayit_id' if has_referans else 'NULL'

                conn.execute(text(f'''
                    INSERT INTO orders_v3_new
                        (id, siparis_no, tarih, urun_id, urun_kodu_ham, beden, adet,
                         toplama_id, personel_id, kargo_kodu, termin_tarihi,
                         durum, hata_sebebi, excel_yukleme_id,
                         senkronize_edildi, senkronize_tarihi, referans_kayit_id)
                    SELECT id, siparis_no, tarih, urun_id, NULL, beden, adet,
                           toplama_id, personel_id, {kargo_expr}, {termin_expr},
                           CASE durum
                               WHEN 'Tamamlandı' THEN 'TAMAMLANDI'
                               WHEN 'Yüklendi' THEN 'BEKLEMEDE'
                               WHEN 'İptal' THEN 'HATALI'
                               ELSE COALESCE(durum, 'BEKLEMEDE')
                           END,
                           NULL, excel_yukleme_id,
                           {senkronize_expr}, {referans_expr}
                    FROM orders
                '''))

                conn.execute(text('DROP TABLE orders'))
                conn.execute(text('ALTER TABLE orders_v3_new RENAME TO orders'))
                conn.execute(text('CREATE INDEX IF NOT EXISTS ix_order_siparis_no ON orders(siparis_no)'))
                conn.execute(text('CREATE INDEX IF NOT EXISTS ix_order_tarih ON orders(tarih)'))
                conn.execute(text('CREATE INDEX IF NOT EXISTS ix_order_toplama ON orders(toplama_id)'))
            elif 'hata_sebebi' not in orders_cols:
                conn.execute(text('ALTER TABLE orders ADD COLUMN hata_sebebi TEXT'))

        # kayitlar tablosuna yeni sütunlar ekle
        if 'kayitlar' in existing_tables:
            kayit_cols = [c['name'] for c in inspector.get_columns('kayitlar')]
            if 'senkronizasyon_sayisi' not in kayit_cols:
                conn.execute(text('ALTER TABLE kayitlar ADD COLUMN senkronizasyon_sayisi INTEGER DEFAULT 0 NOT NULL'))
            if 'son_senkronizasyon' not in kayit_cols:
                conn.execute(text('ALTER TABLE kayitlar ADD COLUMN son_senkronizasyon DATETIME'))

        # excel_uploads tablosuna yeni sütunlar ekle
        if 'excel_uploads' in existing_tables:
            excel_cols = [c['name'] for c in inspector.get_columns('excel_uploads')]
            if 'durum' not in excel_cols:
                conn.execute(text("ALTER TABLE excel_uploads ADD COLUMN durum VARCHAR(50) DEFAULT 'YUKLENDI' NOT NULL"))
            if 'kontrol_tarihi' not in excel_cols:
                conn.execute(text('ALTER TABLE excel_uploads ADD COLUMN kontrol_tarihi DATETIME'))

        conn.commit()
    print("✓ Veritabanı migrasyonu tamamlandı")


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
