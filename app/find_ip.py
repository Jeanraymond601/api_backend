# find_supabase_ip.py
import socket
import subprocess
import re

hostname = "db.oxxuwesviinerhmuusxz.supabase.co"

print("🔍 Recherche des adresses IP pour Supabase...")

# Méthode 1: socket
try:
    addrinfo = socket.getaddrinfo(hostname, 5432)
    print("Adresses trouvées via socket:")
    for addr in addrinfo:
        ip = addr[4][0]
        family = "IPv4" if addr[0] == socket.AF_INET else "IPv6"
        print(f"  - {ip} ({family})")
except Exception as e:
    print(f"Erreur socket: {e}")

# Méthode 2: nslookup
print("\n📡 Résultat nslookup:")
try:
    result = subprocess.run(
        ['nslookup', hostname],
        capture_output=True,
        text=True,
        shell=True
    )
    print(result.stdout)
    
    # Extraire IPv4
    ipv4_pattern = r'Address:\s+(\d+\.\d+\.\d+\.\d+)'
    ipv4_matches = re.findall(ipv4_pattern, result.stdout)
    
    if ipv4_matches:
        print(f"\n✅ Adresse IPv4 trouvée: {ipv4_matches[0]}")
        print(f"\n📝 URL à utiliser:")
        print(f"postgresql://postgres:b4iU4WJOAikxBqqO@{ipv4_matches[0]}:5432/postgres?sslmode=require")
        
except Exception as e:
    print(f"Erreur nslookup: {e}")

# Méthode 3: ping pour tester
print("\n🏓 Test de connectivité:")
try:
    result = subprocess.run(
        ['ping', '-n', '2', hostname],
        capture_output=True,
        text=True,
        shell=True
    )
    if "TTL=" in result.stdout:
        print("✅ Ping réussi")
    else:
        print("❌ Ping échoué")
        print(result.stdout)
except:
    print("Ping non disponible")