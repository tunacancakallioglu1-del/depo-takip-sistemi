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
    kayitlar = db.relationship('Kayit', backref='personel', lazy=True)

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
    personel_id = db.Column(db.Integer, db.ForeignKey('personeller.id'), nullable=True)
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
            'personel': self.personel.ad if self.personel else '',
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
            'bedenler': [size.beden for size in sorted(self.sizes, key=lambda item: item.beden)],
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
    grup_baslangic_satiri = db.Column(db.Boolean, default=False, nullable=False)

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
    urun_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=True)
    urun_kodu_ham = db.Column(db.String(120), nullable=True)
    beden = db.Column(db.String(50), nullable=True)
    adet = db.Column(db.Integer, nullable=False, default=1)
    sebebi = db.Column(db.String(255), nullable=True)
    toplama_id = db.Column(db.Integer, db.ForeignKey('toplamalar.id'), nullable=True)
    durum = db.Column(db.String(50), default='BEKLEMEDE', nullable=False)
    hata_sebebi = db.Column(db.Text, nullable=True)
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


class AdetFiltresi(db.Model):
    """Adet Filtresi — Toplama + Ürün + Beden bazında adet aralığı ayırımı"""
    __tablename__ = 'adet_filtreleri'
    __table_args__ = (
        db.Index('ix_adet_filtre_toplama', 'toplama_id'),
        db.Index('ix_adet_filtre_urun', 'urun_kodu'),
    )

    id = db.Column(db.Integer, primary_key=True)
    toplama_id = db.Column(db.Integer, db.ForeignKey('toplamalar.id'), nullable=False)
    urun_kodu = db.Column(db.String(120), nullable=False)
    beden = db.Column(db.String(50), nullable=True)
    min_adet = db.Column(db.Integer, nullable=False)
    max_adet = db.Column(db.Integer, nullable=True)  # NULL = sınırsız
    olusturulma_tarihi = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    toplama = db.relationship('Toplama', backref=db.backref('adet_filtreleri', lazy=True, cascade='all, delete-orphan'))

    def to_dict(self):
        return {
            'id': self.id,
            'toplama_id': self.toplama_id,
            'toplama': self.toplama.ad if self.toplama else None,
            'urun_kodu': self.urun_kodu,
            'beden': self.beden or '',
            'min_adet': self.min_adet,
            'max_adet': self.max_adet,
            'aralik': f"{self.min_adet}-{self.max_adet}" if self.max_adet else f"{self.min_adet}+",
        }


class IadeHatasi(db.Model):
    """İade Hatası — Tarih + Ürün + Hata Tipi bazında personele/kayıda otomatik bağlanan hata kaydı"""
    __tablename__ = 'iade_hatalari'
    __table_args__ = (
        db.Index('ix_iade_hatasi_tarih', 'tarih'),
        db.Index('ix_iade_hatasi_personel', 'personel_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    tarih = db.Column(db.String(10), nullable=False)  # DD.MM.YYYY
    urun_kodu = db.Column(db.String(120), nullable=True)
    beden = db.Column(db.String(50), nullable=True)
    hata_tipi = db.Column(db.String(120), nullable=False)
    aciklama = db.Column(db.Text, nullable=True)
    siparis_no = db.Column(db.String(120), nullable=True)
    # Otomatik bağlanan alanlar
    personel_id = db.Column(db.Integer, db.ForeignKey('personeller.id'), nullable=True)
    kayit_id = db.Column(db.Integer, db.ForeignKey('kayitlar.id'), nullable=True)
    toplama_id = db.Column(db.Integer, db.ForeignKey('toplamalar.id'), nullable=True)
    olusturulma_tarihi = db.Column(db.DateTime, default=datetime.now, nullable=False)

    personel = db.relationship('Personel', backref=db.backref('iade_hatalari', lazy=True))
    kayit = db.relationship('Kayit', backref=db.backref('iade_hatalari', lazy=True))
    toplama = db.relationship('Toplama', backref=db.backref('iade_hatalari', lazy=True))

    def to_dict(self):
        return {
            'id': self.id,
            'tarih': self.tarih,
            'urun_kodu': self.urun_kodu or '',
            'beden': self.beden or '',
            'hata_tipi': self.hata_tipi,
            'aciklama': self.aciklama or '',
            'siparis_no': self.siparis_no or '',
            'personel': self.personel.ad if self.personel else '—',
            'personel_id': self.personel_id,
            'kayit_id': self.kayit_id,
            'toplama': self.toplama.ad if self.toplama else '—',
            'olusturulma_tarihi': self.olusturulma_tarihi.strftime('%d.%m.%Y %H:%M'),
        }


class KayitAyrinti(db.Model):
    """Kayıt Ayrıntısı — Kayıt'ın ürün/beden/adet detayları"""
    __tablename__ = 'kayit_ayrintilari'
    __table_args__ = (
        db.Index('ix_kayit_ayrinti_kayit', 'kayit_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    kayit_id = db.Column(db.Integer, db.ForeignKey('kayitlar.id'), nullable=False)
    urun_kodu = db.Column(db.String(120), nullable=False)
    beden = db.Column(db.String(50), nullable=True)
    adet = db.Column(db.Integer, nullable=False)
    min_adet_filtre = db.Column(db.Integer, nullable=True)   # AdetFiltresi min (NULL = filtresiz)
    max_adet_filtre = db.Column(db.Integer, nullable=True)   # AdetFiltresi max (NULL = filtresiz)
    olusturulma_tarihi = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    kayit = db.relationship('Kayit', backref=db.backref('ayrintilari', lazy=True, cascade='all, delete-orphan'))

    def to_dict(self):
        return {
            'id': self.id,
            'kayit_id': self.kayit_id,
            'urun_kodu': self.urun_kodu,
            'beden': self.beden or '',
            'adet': self.adet,
            'min_adet_filtre': self.min_adet_filtre,
            'max_adet_filtre': self.max_adet_filtre,
            'aralik': (
                f"{self.min_adet_filtre}-{self.max_adet_filtre}" if self.max_adet_filtre
                else (f"{self.min_adet_filtre}+" if self.min_adet_filtre else 'Tümü')
            ),
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
                        referans_kayit_id INTEGER,
                        grup_baslangic_satiri BOOLEAN NOT NULL DEFAULT 0
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
                         senkronize_edildi, senkronize_tarihi, referans_kayit_id,
                         grup_baslangic_satiri)
                    SELECT id, siparis_no, tarih, urun_id, NULL, beden, adet,
                           toplama_id, personel_id, {kargo_expr}, {termin_expr},
                           CASE durum
                               WHEN 'Tamamlandı' THEN 'TAMAMLANDI'
                               WHEN 'Yüklendi' THEN 'BEKLEMEDE'
                               WHEN 'İptal' THEN 'HATALI'
                               ELSE COALESCE(durum, 'BEKLEMEDE')
                           END,
                           NULL, excel_yukleme_id,
                           {senkronize_expr}, {referans_expr},
                           0
                    FROM orders
                '''))

                conn.execute(text('DROP TABLE orders'))
                conn.execute(text('ALTER TABLE orders_v3_new RENAME TO orders'))
                conn.execute(text('CREATE INDEX IF NOT EXISTS ix_order_siparis_no ON orders(siparis_no)'))
                conn.execute(text('CREATE INDEX IF NOT EXISTS ix_order_tarih ON orders(tarih)'))
                conn.execute(text('CREATE INDEX IF NOT EXISTS ix_order_toplama ON orders(toplama_id)'))
            else:
                if 'hata_sebebi' not in orders_cols:
                    conn.execute(text('ALTER TABLE orders ADD COLUMN hata_sebebi TEXT'))
                if 'grup_baslangic_satiri' not in orders_cols:
                    conn.execute(text('ALTER TABLE orders ADD COLUMN grup_baslangic_satiri BOOLEAN NOT NULL DEFAULT 0'))

        # kayitlar tablosuna yeni sütunlar ekle + personel_id nullable yap
        if 'kayitlar' in existing_tables:
            kayit_cols = [c['name'] for c in inspector.get_columns('kayitlar')]
            if 'senkronizasyon_sayisi' not in kayit_cols:
                conn.execute(text('ALTER TABLE kayitlar ADD COLUMN senkronizasyon_sayisi INTEGER DEFAULT 0 NOT NULL'))
            if 'son_senkronizasyon' not in kayit_cols:
                conn.execute(text('ALTER TABLE kayitlar ADD COLUMN son_senkronizasyon DATETIME'))
            # Personel_id'yi nullable hale getir (SQLite'da tablo yeniden oluşturularak yapılır)
            # Mevcut sütunun nullable olup olmadığını kontrol et
            kayit_col_defs = {c['name']: c for c in inspector.get_columns('kayitlar')}
            personel_col = kayit_col_defs.get('personel_id', {})
            if personel_col.get('nullable') is False:
                has_senk = 'senkronizasyon_sayisi' in kayit_cols
                has_son = 'son_senkronizasyon' in kayit_cols
                conn.execute(text('''
                    CREATE TABLE kayitlar_new (
                        id INTEGER NOT NULL PRIMARY KEY,
                        tarih VARCHAR(10) NOT NULL,
                        personel_id INTEGER REFERENCES personeller(id),
                        toplama_id INTEGER NOT NULL REFERENCES toplamalar(id),
                        trendyol_siparis FLOAT DEFAULT 0,
                        trendyol_fatura FLOAT DEFAULT 0,
                        diger_pazar FLOAT DEFAULT 0,
                        not_alan TEXT DEFAULT '',
                        eklenme_tarihi DATETIME,
                        senkronizasyon_sayisi INTEGER NOT NULL DEFAULT 0,
                        son_senkronizasyon DATETIME
                    )
                '''))
                senk_col = 'senkronizasyon_sayisi' if has_senk else '0'
                son_col = 'son_senkronizasyon' if has_son else 'NULL'
                conn.execute(text(f'''
                    INSERT INTO kayitlar_new
                        (id, tarih, personel_id, toplama_id, trendyol_siparis,
                         trendyol_fatura, diger_pazar, not_alan, eklenme_tarihi,
                         senkronizasyon_sayisi, son_senkronizasyon)
                    SELECT id, tarih, personel_id, toplama_id, trendyol_siparis,
                           trendyol_fatura, diger_pazar, not_alan, eklenme_tarihi,
                           {senk_col}, {son_col}
                    FROM kayitlar
                '''))
                conn.execute(text('DROP TABLE kayitlar'))
                conn.execute(text('ALTER TABLE kayitlar_new RENAME TO kayitlar'))

        # excel_uploads tablosuna yeni sütunlar ekle
        if 'excel_uploads' in existing_tables:
            excel_cols = [c['name'] for c in inspector.get_columns('excel_uploads')]
            if 'durum' not in excel_cols:
                conn.execute(text("ALTER TABLE excel_uploads ADD COLUMN durum VARCHAR(50) DEFAULT 'YUKLENDI' NOT NULL"))
            if 'kontrol_tarihi' not in excel_cols:
                conn.execute(text('ALTER TABLE excel_uploads ADD COLUMN kontrol_tarihi DATETIME'))

        # returns tablosuna yeni sütunlar ekle (durum, hata_sebebi, urun_kodu_ham; urun_id/toplama_id nullable)
        if 'returns' in existing_tables:
            ret_cols = [c['name'] for c in inspector.get_columns('returns')]
            needs_rebuild = 'urun_kodu_ham' not in ret_cols or 'durum' not in ret_cols or 'hata_sebebi' not in ret_cols
            if needs_rebuild:
                conn.execute(text('''
                    CREATE TABLE returns_v2_new (
                        id INTEGER NOT NULL PRIMARY KEY,
                        siparis_no VARCHAR(120) NOT NULL,
                        tarih DATETIME NOT NULL,
                        urun_id INTEGER REFERENCES products(id),
                        urun_kodu_ham VARCHAR(120),
                        beden VARCHAR(50),
                        adet INTEGER NOT NULL DEFAULT 1,
                        sebebi VARCHAR(255),
                        toplama_id INTEGER REFERENCES toplamalar(id),
                        durum VARCHAR(50) NOT NULL DEFAULT 'BEKLEMEDE',
                        hata_sebebi TEXT,
                        excel_yukleme_id INTEGER REFERENCES excel_uploads(id)
                    )
                '''))
                conn.execute(text('''
                    INSERT INTO returns_v2_new
                        (id, siparis_no, tarih, urun_id, urun_kodu_ham, beden, adet,
                         sebebi, toplama_id, durum, hata_sebebi, excel_yukleme_id)
                    SELECT id, siparis_no, tarih, urun_id, NULL, beden, adet,
                           sebebi, toplama_id, 'BEKLEMEDE', NULL, excel_yukleme_id
                    FROM returns
                '''))
                conn.execute(text('DROP TABLE returns'))
                conn.execute(text('ALTER TABLE returns_v2_new RENAME TO returns'))
                conn.execute(text('CREATE INDEX IF NOT EXISTS ix_return_siparis_no ON returns(siparis_no)'))
                conn.execute(text('CREATE INDEX IF NOT EXISTS ix_return_tarih ON returns(tarih)'))
                conn.execute(text('CREATE INDEX IF NOT EXISTS ix_return_toplama ON returns(toplama_id)'))
            else:
                if 'urun_kodu_ham' not in ret_cols:
                    conn.execute(text('ALTER TABLE returns ADD COLUMN urun_kodu_ham VARCHAR(120)'))
                if 'durum' not in ret_cols:
                    conn.execute(text("ALTER TABLE returns ADD COLUMN durum VARCHAR(50) NOT NULL DEFAULT 'BEKLEMEDE'"))
                if 'hata_sebebi' not in ret_cols:
                    conn.execute(text('ALTER TABLE returns ADD COLUMN hata_sebebi TEXT'))

        # Yeni tablolar: adet_filtreleri ve kayit_ayrintilari
        if 'adet_filtreleri' not in existing_tables:
            conn.execute(text('''
                CREATE TABLE adet_filtreleri (
                    id INTEGER NOT NULL PRIMARY KEY,
                    toplama_id INTEGER NOT NULL REFERENCES toplamalar(id),
                    urun_kodu VARCHAR(120) NOT NULL,
                    beden VARCHAR(50),
                    min_adet INTEGER NOT NULL,
                    max_adet INTEGER,
                    olusturulma_tarihi DATETIME
                )
            '''))
            conn.execute(text('CREATE INDEX IF NOT EXISTS ix_adet_filtre_toplama ON adet_filtreleri(toplama_id)'))
            conn.execute(text('CREATE INDEX IF NOT EXISTS ix_adet_filtre_urun ON adet_filtreleri(urun_kodu)'))

        if 'kayit_ayrintilari' not in existing_tables:
            conn.execute(text('''
                CREATE TABLE kayit_ayrintilari (
                    id INTEGER NOT NULL PRIMARY KEY,
                    kayit_id INTEGER NOT NULL REFERENCES kayitlar(id),
                    urun_kodu VARCHAR(120) NOT NULL,
                    beden VARCHAR(50),
                    adet INTEGER NOT NULL,
                    min_adet_filtre INTEGER,
                    max_adet_filtre INTEGER,
                    olusturulma_tarihi DATETIME
                )
            '''))
            conn.execute(text('CREATE INDEX IF NOT EXISTS ix_kayit_ayrinti_kayit ON kayit_ayrintilari(kayit_id)'))

        if 'iade_hatalari' not in existing_tables:
            conn.execute(text('''
                CREATE TABLE iade_hatalari (
                    id INTEGER NOT NULL PRIMARY KEY,
                    tarih VARCHAR(10) NOT NULL,
                    urun_kodu VARCHAR(120),
                    beden VARCHAR(50),
                    hata_tipi VARCHAR(120) NOT NULL,
                    aciklama TEXT,
                    siparis_no VARCHAR(120),
                    personel_id INTEGER REFERENCES personeller(id),
                    kayit_id INTEGER REFERENCES kayitlar(id),
                    toplama_id INTEGER REFERENCES toplamalar(id),
                    olusturulma_tarihi DATETIME
                )
            '''))
            conn.execute(text('CREATE INDEX IF NOT EXISTS ix_iade_hatasi_tarih ON iade_hatalari(tarih)'))
            conn.execute(text('CREATE INDEX IF NOT EXISTS ix_iade_hatasi_personel ON iade_hatalari(personel_id)'))

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


def kayit_ekle(tarih, toplama_id, personel_id=None, trendyol_siparis=0,
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


def kayit_guncelle(id, tarih, toplama_id, personel_id=None, trendyol_siparis=0,
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
    """Kayıt sil — ilgili TAMAMLANDI siparişleri BEKLEMEDE'ye döndür"""
    from datetime import datetime as _dt, time as _time

    kayit = Kayit.query.get(id)
    if not kayit:
        return {'basarili': False, 'mesaj': 'Kayıt bulunamadı!'}

    # İlgili TAMAMLANDI siparişleri BEKLEMEDE'ye döndür
    geri_donen = 0
    try:
        tarih_obj = _dt.strptime(kayit.tarih, '%d.%m.%Y').date()
        tarih_start = _dt.combine(tarih_obj, _time.min)
        tarih_end = _dt.combine(tarih_obj, _time.max)

        siparisler = Order.query.filter(
            Order.durum == 'TAMAMLANDI',
            Order.toplama_id == kayit.toplama_id,
            Order.tarih >= tarih_start,
            Order.tarih <= tarih_end,
        ).all()

        for s in siparisler:
            s.durum = 'BEKLEMEDE'
            s.senkronize_edildi = False
            s.senkronize_tarihi = None
        geri_donen = len(siparisler)
    except (ValueError, AttributeError):
        pass

    db.session.delete(kayit)
    db.session.commit()

    if geri_donen:
        return {'basarili': True, 'mesaj': f'Kayıt silindi! {geri_donen} sipariş BEKLEMEDE durumuna döndürüldü.'}
    return {'basarili': True, 'mesaj': 'Kayıt silindi!'}
