"""Scanner réseau en eSCL (AirScan) : découverte Bonjour + scan de la vitre. Aucun pilote."""
import socket
import time
import urllib.error
import urllib.request
from urllib.parse import urljoin
import xml.etree.ElementTree as ET

from zeroconf import ServiceBrowser, Zeroconf

SERVICE = "_uscan._tcp.local."
NS = {"scan": "http://schemas.hp.com/imaging/escl/2011/05/03",
      "pwg": "http://www.pwg.org/schemas/2010/12/sm"}

SETTINGS = """<?xml version="1.0" encoding="UTF-8"?>
<scan:ScanSettings xmlns:scan="http://schemas.hp.com/imaging/escl/2011/05/03"
                   xmlns:pwg="http://www.pwg.org/schemas/2010/12/sm">
  <pwg:Version>2.5</pwg:Version>
  <pwg:ScanRegions><pwg:ScanRegion>
    <pwg:Height>{h}</pwg:Height><pwg:Width>{w}</pwg:Width>
    <pwg:XOffset>0</pwg:XOffset><pwg:YOffset>0</pwg:YOffset>
  </pwg:ScanRegion></pwg:ScanRegions>
  <pwg:InputSource>Platen</pwg:InputSource>
  <scan:ColorMode>RGB24</scan:ColorMode>
  <scan:XResolution>{dpi}</scan:XResolution>
  <scan:YResolution>{dpi}</scan:YResolution>
  <pwg:DocumentFormat>image/jpeg</pwg:DocumentFormat>
</scan:ScanSettings>"""


class ScannerError(Exception):
    """Message lisible par l'utilisatrice."""


def discover(timeout=5.0):
    """Liste [(nom, url_base)] des scanners eSCL du réseau local."""
    found = {}

    class L:
        def add_service(self, zc, typ, name):
            info = zc.get_service_info(typ, name, 3000)
            if not info or not info.addresses:
                return
            ip = socket.inet_ntoa(info.addresses[0])
            rs = (info.properties.get(b"rs") or b"eSCL").decode().strip("/")
            label = name.replace("." + SERVICE, "")
            found[label] = f"http://{ip}:{info.port}/{rs}"

        def update_service(self, *a):
            pass

        def remove_service(self, *a):
            pass

    zc = Zeroconf()
    try:
        ServiceBrowser(zc, SERVICE, L())
        end = time.time() + timeout
        while time.time() < end and not found:
            time.sleep(0.2)
        time.sleep(0.5)
    finally:
        zc.close()
    return sorted(found.items())


def is_alive(base):
    try:
        urllib.request.urlopen(base + "/ScannerStatus", timeout=4).read()
        return True
    except Exception:
        return False


def platen_size(base):
    """Taille max de la vitre en 1/300 de pouce (largeur, hauteur)."""
    x = urllib.request.urlopen(base + "/ScannerCapabilities", timeout=10).read()
    root = ET.fromstring(x)
    caps = root.find(".//scan:Platen/scan:PlatenInputCaps", NS)
    return (int(caps.find("scan:MaxWidth", NS).text),
            int(caps.find("scan:MaxHeight", NS).text))


def scan(base, dpi=600):
    """Scanne toute la vitre, renvoie les octets JPEG."""
    try:
        w, h = platen_size(base)
    except Exception:
        raise ScannerError("Le scanner ne répond pas. Vérifiez qu'il est allumé.")
    body = SETTINGS.format(w=w, h=h, dpi=dpi).encode()
    job = None
    for _ in range(10):  # 409/503 = scanner occupé (copie en cours, réveil…)
        req = urllib.request.Request(base + "/ScanJobs", data=body,
                                     headers={"Content-Type": "text/xml"}, method="POST")
        try:
            job = urllib.request.urlopen(req, timeout=30).headers.get("Location")
            break
        except urllib.error.HTTPError as e:
            if e.code in (409, 503):
                time.sleep(3)
                continue
            raise ScannerError(f"Le scanner a refusé le scan (code {e.code}).")
        except Exception:
            raise ScannerError("Le scanner ne répond pas. Vérifiez qu'il est allumé.")
    if not job:
        raise ScannerError("Le scanner est occupé. Réessayez dans un instant.")
    job = urljoin(base + "/", job)  # Location peut être relative
    for _ in range(180):
        try:
            return urllib.request.urlopen(job.rstrip("/") + "/NextDocument", timeout=300).read()
        except urllib.error.HTTPError as e:
            if e.code in (404, 503):
                time.sleep(1)
                continue
            raise ScannerError(f"Erreur pendant le scan (code {e.code}).")
    raise ScannerError("Le scan n'est jamais arrivé. Éteignez et rallumez le scanner.")
