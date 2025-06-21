from Crypto.PublicKey import ECC

# 產生私鑰
key = ECC.generate(curve='P-256')
with open('ecdsa_private.pem', 'wt') as f:
    f.write(key.export_key(format='PEM'))

# 匯出公鑰
with open('ecdsa_public.pem', 'wt') as f:
    f.write(key.public_key().export_key(format='PEM'))