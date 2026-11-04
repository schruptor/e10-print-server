#!/usr/bin/env python3
"""E10 text print server. Protocol port: reference/SOURCE.txt (MIT).
Single-process/single-event-loop BLE owner; no reload or multiple workers.
Hardware compatibility is experimental until tested on the target E10.
"""
from __future__ import annotations
import asyncio
import base64
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
import io
import ipaddress
import json
import logging
import lzma
import os
from pathlib import Path
import struct
import time

from bleak import BleakClient, BleakScanner
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, Field
import uvicorn

ROOT = Path(__file__).resolve().parent
LOG = logging.getLogger('e10')
SERVICE = '0000e0ff-3c17-d293-8e48-14fe2e4da212'
WRITE = '0000ffe9-0000-1000-8000-00805f9b34fb'
NOTIFY = '0000ffe1-0000-1000-8000-00805f9b34fb'

@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    scheme: str
    cert: str | None
    key: str | None
    key_password: str | None
    font: str | None

    @classmethod
    def read(cls):
        load_dotenv(ROOT / '.env', override=False)
        host = os.getenv('SERVER_IP', '127.0.0.1')
        ipaddress.ip_address(host)
        port = int(os.getenv('SERVER_PORT', '8080'))
        if not 1 <= port <= 65535:
            raise ValueError('SERVER_PORT must be between 1 and 65535')
        scheme = os.getenv('SERVER_SCHEME', 'http').lower()
        if scheme not in ('http', 'https'):
            raise ValueError('SERVER_SCHEME must be http or https')
        def path(name):
            v = os.getenv(name, '').strip()
            if not v:
                return None
            p = Path(v).expanduser()
            if not p.is_absolute():
                p = ROOT / p
            if not p.is_file():
                raise ValueError(f'{name}: file not found: {p}')
            return str(p)
        cert = path('SSL_CERT_FILE') if scheme == 'https' else None
        key = path('SSL_KEY_FILE') if scheme == 'https' else None
        if scheme == 'https' and (not cert or not key):
            raise ValueError('HTTPS requires SSL_CERT_FILE and SSL_KEY_FILE; no HTTP fallback')
        return cls(host, port, scheme, cert, key, os.getenv('SSL_KEY_PASSWORD') or None,
                   path('FONT_PATH'))


def command_frame(cmd, a=0, b=0):
    f = bytearray.fromhex('7e5a0c001001aa000000000100000000')
    f[7] = cmd
    struct.pack_into('<HH', f, 12, a, b)
    struct.pack_into('<H', f, 8, sum(f[10:]) & 65535)
    return bytes(f)


def compress_buffer(data):
    # Known-size LZMA-Alone, 8 KiB dictionary and SDK-compatible lc/lp/pb.
    # liblzma adds an EOS marker; upstream's encoder omits it. The decoded bytes
    # are tested against upstream, but acceptance of this variant needs hardware testing.
    stream = lzma.compress(data, format=lzma.FORMAT_ALONE, filters=[{
        'id': lzma.FILTER_LZMA1, 'dict_size': 8192, 'lc': 3, 'lp': 0, 'pb': 2,
        'mode': lzma.MODE_NORMAL, 'nice_len': 128, 'mf': lzma.MF_BT4}])
    return stream[:5] + struct.pack('<Q', len(data)) + stream[13:]


def encode_job(image, density, die_cut=False, gap=3, copies=1):
    """96 rows; column bytes LSB-first. Return (raw buffers, streams, backFrames)."""
    if image.height != 96 or image.width < 1:
        raise ValueError('Expected a non-empty, 96-row raster')
    pixels = image.convert('L').load()
    cols = image.width
    columns = []
    for x in range(cols):
        c = bytearray(12)
        for y in range(96):
            if pixels[x, y] < 128:
                c[y // 8] |= 1 << (y % 8)
        columns.append(c)
    buf = bytearray(4000)
    buffers, streams, back = [], [], 0
    for label in range(copies):
        last = label == copies - 1
        current = 0
        first = True
        while current < cols:
            skip = 0
            if first and label == 0:
                limit = int((6.5 - gap) * 8) if die_cut else 48
                if limit < 1:
                    raise ValueError('Unsupported material gap')
                ink = 0
                while ink < limit and (ink >= cols or not any(columns[ink])):
                    ink += 1
                skip = min(max(0, ink - 1), limit - 1)
                back = 0 if skip >= limit - 1 else limit - skip
                skip = min(skip, cols - 1)
                current = skip
            count = min(332, cols - current)
            end = current + count == cols
            cut = 1 if last else 0
            buf[2] = (2 if first else 0) | (4 if end else 0) | (8 if end and last else 0) | (cut << 4)
            buf[3] = ((density << 2) | 16) & 255
            struct.pack_into('<H', buf, 4, count)
            buf[6] = 12
            buf[8:14] = bytes([1, 0, 1, 0, skip, 0])
            buf[14:14 + count * 12] = b''.join(columns[current:current + count])
            length = count * 12 + 14
            checksum = sum(buf[2:14]) + sum(buf[k * 256 - 1] for k in range(1, length // 256 + 1))
            struct.pack_into('<H', buf, 0, checksum & 65535)
            stream = compress_buffer(buf)
            # iOS avoids accidental AA-command markers at BLE write boundaries.
            hits = [i for i in (0x7a, 0xfa, 0x17a) if len(stream) > i + 1
                    and stream[i] == 0xaa and stream[i + 1] in (0xbb, 6, 0xc7, 7)]
            for i in hits:
                buf[i] = (buf[i] + 1) & 255
            if hits:
                stream = compress_buffer(buf)
                if any(len(stream) > i + 1 and stream[i] == 0xaa and stream[i+1] in (0xbb, 6, 0xc7, 7)
                       for i in (0x7a, 0xfa, 0x17a)):
                    raise ValueError('Unsafe compressed frame marker; change the text slightly')
            buffers.append(bytes(buf))
            streams.append(stream)
            current += count
            first = False
    return buffers, streams, back


def data_frames(stream):
    count = (len(stream) + 499) // 500
    if not 1 <= count <= 255:
        raise ValueError('Invalid frame count')
    inner = bytearray(506)
    inner[:2] = b'\xaa\xbb'
    for index in range(count):
        inner[4:6] = bytes([index, count])
        piece = stream[index * 500:(index + 1) * 500]
        inner[6:6 + len(piece)] = piece
        struct.pack_into('<H', inner, 2, sum(inner[4:]) & 65535)
        yield bytes.fromhex('7e5afc011002') + bytes(inner)


class DeviceChoice(BaseModel):
    address: str = Field(min_length=1, max_length=128)


class PrintSpec(BaseModel):
    text: str = Field(max_length=1000)
    length_mm: int = Field(default=50, ge=10, le=200)
    font_size: int = Field(default=36, ge=10, le=80)
    density: int = Field(default=4, ge=1, le=7)
    copies: int = Field(default=1, ge=1, le=10)


def render(spec, font_path=None):
    if not spec.text.strip() or any(ord(c) < 32 and c not in '\n\t\r' for c in spec.text):
        raise ValueError('Bitte sichtbaren Text ohne Steuerzeichen eingeben')
    paths = [font_path] if font_path else [
        '/System/Library/Fonts/Supplemental/Arial.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        str(Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts' / 'arial.ttf')]
    image = Image.new('L', (spec.length_mm * 8, 96), 255)
    draw = ImageDraw.Draw(image)
    text = spec.text.replace('\t', '    ').replace('\r\n', '\n')
    for size in range(spec.font_size, 9, -1):
        font = None
        for path in paths:
            try:
                font = ImageFont.truetype(path, size)
                break
            except OSError:
                pass
        if font is None:
            font = ImageFont.load_default(size=size)
        box = draw.multiline_textbbox((0, 0), text, font=font, spacing=2, align='center')
        w, h = box[2] - box[0], box[3] - box[1]
        if w <= image.width - 16 and h <= 88:
            draw.multiline_text(((image.width-w)//2-box[0], (96-h)//2-box[1]), text,
                                font=font, spacing=2, align='center', fill=0)
            return image.point(lambda p: 0 if p < 128 else 255)
    raise ValueError('Text passt nicht auf das Etikett. Text kürzen oder Etikett verlängern.')


class E10:
    def __init__(self):
        self.client = None
        self.write_char = None
        self.pending = bytearray()
        self.replies = asyncio.Queue(maxsize=128)
        self.arrived = asyncio.Event()
        self.received = 0
        self.devices = {}
        self.selected = None
        self.phase = 'Nicht verbunden'
        self.material = None
        self.lock = asyncio.Lock()
        with suppress(OSError, ValueError):
            self.selected = json.loads((ROOT / 'printer.json').read_text('utf-8'))

    @property
    def connected(self):
        return self.client is not None and self.client.is_connected

    def receive(self, sender, data):
        self.received += len(data)
        self.arrived.set()
        self.pending.extend(data)
        while len(self.pending) >= 4:
            pos = self.pending.find(b'\x7e\x5a')
            if pos < 0:
                self.pending[:] = self.pending[-1:] if self.pending[-1:] == b'\x7e' else b''
                return
            if pos:
                del self.pending[:pos]
            if len(self.pending) < 4:
                return
            n = int.from_bytes(self.pending[2:4], 'little') + 4
            if not 8 <= n <= 2048:
                del self.pending[0]
                continue
            if len(self.pending) < n:
                return
            frame = bytes(self.pending[:n])
            del self.pending[:n]
            if self.replies.full():
                self.replies.get_nowait()
            self.replies.put_nowait(frame)

    def clear(self):
        self.pending.clear()
        while not self.replies.empty():
            self.replies.get_nowait()
        self.arrived.clear()

    async def write(self, data):
        if not self.connected:
            raise RuntimeError('Drucker nicht verbunden')
        # Preserve the E10's 128-byte BLE packet boundaries, not arbitrary 20-byte chunks.
        await self.client.write_gatt_char(self.write_char, data, response=False)

    async def command(self, cmd, a=0, b=0, timeout=4):
        for attempt in range(2 if cmd == 0x11 else 1):
            self.clear()
            await self.write(command_frame(cmd, a, b))
            deadline = time.monotonic() + timeout
            try:
                while True:
                    f = await asyncio.wait_for(self.replies.get(), max(.001, deadline-time.monotonic()))
                    if f[7] == cmd:
                        return f
            except asyncio.TimeoutError:
                if cmd != 0x11 or attempt:
                    raise RuntimeError(f'Keine Druckerantwort auf 0x{cmd:02x}; nicht automatisch erneut drucken')

    async def status(self):
        f = await self.command(0x11)
        if len(f) < 20:
            raise RuntimeError('Unvollständige E10-Statusantwort')
        b = f[14:20]
        errors = []
        for test, message in [
            (b[2]&8, 'Abdeckung offen'), (b[3]&1 or b[0]&2, 'Kein Etikett erkannt'),
            (b[0]&4, 'Etiketten verbraucht'), (b[0]&16, 'Etikettenband nicht eingelegt'),
            (b[1]&8, 'Druckkopf zu heiß'), (b[0]&64, 'Akku laden')]:
            if test:
                errors.append(message)
        return {'busy': bool(b[1]&4), 'printing': bool(b[2]&64),
                'buffer_full': bool(b[0]&1), 'errors': errors,
                'pages': b[4] | b[5]<<8}

    async def disconnect(self):
        if self.client:
            await self.client.disconnect()
        self.client = None
        self.material = None
        self.phase = 'Nicht verbunden'

    async def connect(self, address):
        await self.disconnect()
        devices = await BleakScanner.discover(timeout=6)
        device = next((d for d in devices if d.address == address), None)
        if device is None:
            raise RuntimeError('Drucker nicht gefunden. E10 einschalten und iPhone-Verbindung trennen.')
        self.client = BleakClient(device, timeout=20)
        try:
            await self.client.connect()
            service = self.client.services.get_service(SERVICE)
            if not service:
                raise RuntimeError('Kein unterstützter E10-Service. Dieser Treiber ist nur für E10/T15-BLE.')
            self.write_char = service.get_characteristic(WRITE)
            notify = service.get_characteristic(NOTIFY)
            if not self.write_char or not notify:
                raise RuntimeError('E10-Schreib-/Antwortkanal fehlt')
            if 'write-without-response' not in self.write_char.properties:
                raise RuntimeError('E10 unterstützt keine BLE-Schreibvorgänge ohne Antwort')
            for _ in range(40):
                if self.write_char.max_write_without_response_size >= 128:
                    break
                await asyncio.sleep(.1)
            if self.write_char.max_write_without_response_size < 128:
                raise RuntimeError('BLE-Paketgröße unter 128 Bytes. Betriebssystem/Adapter prüfen; nichts gedruckt.')
            self.clear()
            await self.client.start_notify(notify, self.receive)
            for attempt in range(6):
                try:
                    await self.status()
                    break
                except RuntimeError:
                    if attempt == 5:
                        raise
                    await asyncio.sleep(.3)
            self.selected = {'address': device.address, 'name': device.name or 'E10'}
            temp = ROOT / 'printer.json.tmp'
            temp.write_text(json.dumps(self.selected), 'utf-8')
            temp.replace(ROOT / 'printer.json')
            self.phase = 'Verbunden'
        except BaseException:
            with suppress(Exception):
                await self.disconnect()
            raise

    async def read_material(self):
        f = await self.command(0x30)
        if len(f) < 43:
            raise RuntimeError('Material nicht zuverlässig lesbar; kein Druck gestartet')
        gap = f[42] if f[42] <= 8 else 3
        self.material = {'die_cut': f[39] in (1, 129), 'gap': gap,
                         'width_mm': f[40], 'length_mm': f[41]}
        with suppress(RuntimeError):
            await self.command(0x18, timeout=1)
        return self.material

    async def wait_status(self, predicate, seconds, running=False):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            s = await self.status()
            if s['errors']:
                raise RuntimeError('; '.join(s['errors']))
            if running and not s['printing'] and not s['busy']:
                raise RuntimeError('Druck am Gerät gestoppt')
            if predicate(s):
                return s
            await asyncio.sleep(.2)
        raise RuntimeError('Zeitüberschreitung beim Druckstatus')

    async def print_copies(self, image, spec):
        """Finish each individual label before allowing time for manual cutting."""
        single = spec.model_copy(update={'copies': 1})
        try:
            for copy in range(spec.copies):
                await self.print_text(image, single)
                if copy + 1 < spec.copies:
                    for remaining in range(5, 0, -1):
                        self.phase = (f'Kopie {copy + 1}/{spec.copies} fertig – '
                                      f'jetzt schneiden! Weiter in {remaining} s')
                        await asyncio.sleep(1)
            self.phase = f'Alle {spec.copies} Kopie(n) abgeschlossen'
        except BaseException:
            self.phase = 'Kopienauftrag abgebrochen; Gerät prüfen, nicht blind erneut drucken'
            raise

    async def print_text(self, image, spec):
        self.phase = 'Prüfe Drucker und Material'
        await self.wait_status(lambda s: not s['busy'] and not s['printing'], 10)
        media = await self.read_material()
        if media['die_cut'] and media['length_mm'] and abs(media['length_mm'] - spec.length_mm) > 1:
            raise RuntimeError(f"Etikettenlänge passt nicht: Material meldet {media['length_mm']} mm")
        _, streams, back = encode_job(image, spec.density, media['die_cut'], media['gap'], spec.copies)
        with suppress(RuntimeError):
            await self.command(0xc9, spec.density * 10 + 70)
        try:
            await self.command(0x13)
            await self.wait_status(lambda s: s['printing'], 8)
            with suppress(RuntimeError):
                await self.command(0xba, back)
            for i, stream in enumerate(streams):
                self.phase = f'Übertrage Puffer {i+1}/{len(streams)}'
                await self.wait_status(lambda s: not s['buffer_full'], 30, running=True)
                frames = list(data_frames(stream))
                await self.command(0x5c, 512, len(frames))
                for frame in frames:
                    self.clear()
                    received = self.received
                    for offset in range(0, 512, 128):
                        await self.write(frame[offset:offset+128])
                        await asyncio.sleep(.01)
                    end = time.monotonic() + 2
                    while self.received <= received:
                        remaining = end - time.monotonic()
                        if remaining <= 0:
                            raise RuntimeError('Keine Datenbestätigung; Druck abgebrochen')
                        self.arrived.clear()
                        await asyncio.wait_for(self.arrived.wait(), remaining)
                await asyncio.sleep(.05)
                await self.command(0x10)
            self.phase = 'Warte auf Druckabschluss'
            await self.wait_status(lambda s: not s['printing'] and not s['busy'], 120)
            self.phase = 'Druck abgeschlossen'
        except BaseException:
            # Do not retry START or print data: a timeout may already have printed a label.
            with suppress(Exception):
                await self.command(0x14, timeout=2)
            self.phase = 'Druck fehlgeschlagen; Gerät prüfen, nicht blind erneut drucken'
            raise


HTML = r'''<!doctype html><html lang="de"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>E10 Textdruck</title>
<style>body{font:16px system-ui;background:#10151c;color:#eee;margin:auto;padding:24px;max-width:760px}section{background:#1c2530;border-radius:14px;padding:20px;margin:18px 0}input,select,textarea,button{font:inherit;padding:10px;border-radius:7px;border:1px solid #617183;box-sizing:border-box}textarea{width:100%;min-height:110px}button{background:#81dcbb;color:#10211c;cursor:pointer;margin:8px 4px 8px 0}button:disabled{opacity:.4}label{display:inline-block;margin:8px 12px 8px 0}input[type=number]{width:100px}img{max-width:100%;height:auto;background:white;image-rendering:pixelated;border:8px solid white}#msg{white-space:pre-wrap}small{color:#bbc8d5}</style>
<h1>E10 · Textdruck</h1><small>Experimenteller Treiber · Erst mit einem einzelnen kurzen Etikett testen.</small>
<section><h2>1. Drucker auswählen</h2><button id="scan">Drucker suchen</button><select id="devices" aria-label="Bluetooth-Drucker"></select><button id="connect">Verbinden</button><button id="disconnect">Trennen</button><p id="state">Nicht verbunden</p><small>Der E10 kann einen Namen wie T0179… haben. Die Suche läuft auf dem Server, nicht auf dem iPhone.</small></section>
<section><h2>2. Text gestalten</h2><textarea id="text" maxlength="1000" placeholder="Dein Etikettentext">Hallo E10!</textarea><label>Länge (mm)<br><input id="length" type="number" min="10" max="200" value="50"></label><label>Schriftgröße (max.)<br><input id="font" type="number" min="10" max="80" value="36"></label><label>Dichte<br><input id="density" type="number" min="1" max="7" value="4"></label><label>Kopien<br><input id="copies" type="number" min="1" max="10" value="1"></label><p><small>96 Druckpunkte hoch, Text mittig in 88 Punkten. Schrift wird bei Bedarf verkleinert; kein stilles Abschneiden. Emojis benötigen eine passende Schrift.</small></p><button id="print">Drucken</button><h3>Live-Vorschau</h3><p><img id="image" alt="Etikettenvorschau" width="400" height="96" src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"></p><p id="previewInfo" role="status" aria-live="polite"></p><small>Vorschau eines Etiketts. Dichte steuert die Druckwärme, nicht die Bildschirmdarstellung. Zwischen Kopien: 5 Sekunden Zeit zum Schneiden.</small></section><p id="msg" role="status"></p>
<script>
const $=id=>document.getElementById(id);let busy=false,connected=false;
const spec=()=>({text:$('text').value,length_mm:Number($('length').value),font_size:Number($('font').value),density:Number($('density').value),copies:Number($('copies').value)});
async function api(path,data,signal){const r=await fetch('/api/'+path,{method:data===undefined?'GET':'POST',headers:{'Content-Type':'application/json'},body:data===undefined?undefined:JSON.stringify(data),signal});let v=await r.json();if(!r.ok)throw Error(typeof v.detail==='string'?v.detail:JSON.stringify(v.detail));return v}
async function status(){const s=await api('status');connected=s.connected;$('state').textContent=(connected?'Verbunden: ':'Nicht verbunden: ')+(s.selected?.name||'kein Drucker ausgewählt')+' · '+s.phase;if(s.selected&&!$('devices').options.length){const o=new Option(s.selected.name+' (gespeichert)',s.selected.address);$('devices').add(o)}}
async function run(fn){if(busy)return;busy=true;document.querySelectorAll('button').forEach(b=>b.disabled=true);$('msg').textContent='Bitte warten …';try{await fn();$('msg').textContent='Fertig.'}catch(e){$('msg').textContent=e.message}finally{busy=false;document.querySelectorAll('button').forEach(b=>b.disabled=false);try{await status()}catch{}}}
$('scan').onclick=()=>run(async()=>{const d=await api('scan',{});$('devices').replaceChildren();for(const x of d.devices)$('devices').add(new Option(x.name+' · '+x.address,x.address));if(!d.devices.length)throw Error('Keine passenden Geräte gefunden. E10 einschalten und iPhone-App trennen.')});
$('connect').onclick=()=>run(async()=>{if(!$('devices').value)throw Error('Erst Drucker auswählen');await api('connect',{address:$('devices').value})});
$('disconnect').onclick=()=>run(()=>api('disconnect',{}));
let previewTimer,previewRequest,previewRevision=0;
async function updatePreview(revision=++previewRevision){
    previewRequest?.abort();
    const request=new AbortController();previewRequest=request;
    const data=spec();
    try{
        const p=await api('preview',data,request.signal);
        if(revision!==previewRevision)return;
        $('image').src=p.image;
        $('image').width=data.length_mm*8;$('image').height=96;
        $('image').style.opacity='1';
        $('previewInfo').textContent=data.length_mm+' mm · Dichte '+data.density+' · '+data.copies+' Kopie(n)'+(data.copies>1?' · 5 s Schneidepause zwischen Kopien':'');
    }catch(e){
        if(revision!==previewRevision||e.name==='AbortError')return;
        $('image').style.opacity='.35';
        $('previewInfo').textContent='Vorschau nicht aktuell: '+e.message;
    }
}
function schedulePreview(){
    clearTimeout(previewTimer);previewRequest?.abort();
    const revision=++previewRevision;
    $('image').style.opacity='.5';
    $('previewInfo').textContent='Vorschau wird aktualisiert …';
    previewTimer=setTimeout(()=>updatePreview(revision),200);
}
for(const id of ['text','length','font','density','copies']){
    $(id).addEventListener('input',schedulePreview);
    $(id).addEventListener('change',schedulePreview);
}
updatePreview();
$('print').onclick=()=>run(async()=>{if(!connected)throw Error('Bitte zuerst den E10 verbinden');await api('print',spec())});
status().catch(e=>$('msg').textContent=e.message);
setInterval(()=>status().catch(()=>{}),2000);
</script></html>'''


def create_app(settings):
    printer = E10()
    @asynccontextmanager
    async def lifespan(app):
        yield
        with suppress(Exception):
            await printer.disconnect()
    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.printer = printer

    @app.middleware('http')
    async def guard(request: Request, call_next):
        if request.url.path.startswith('/api/'):
            origin = request.headers.get('origin')
            if origin and origin != f'{request.url.scheme}://{request.url.netloc}':
                return JSONResponse({'detail': 'Fremder Origin abgelehnt'}, status_code=403)
            # Stream limit, including chunked bodies; replay the bounded body for FastAPI.
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 16384:
                    return JSONResponse({'detail': 'Anfrage zu groß'}, status_code=413)
            request._body = bytes(body)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        return response

    @asynccontextmanager
    async def exclusive():
        if printer.lock.locked():
            raise HTTPException(409, 'Drucker wird gerade verwendet')
        async with printer.lock:
            try:
                yield
            except HTTPException:
                raise
            except Exception as exc:
                LOG.exception('E10 operation failed')
                raise HTTPException(400, str(exc)) from exc

    @app.get('/', response_class=HTMLResponse)
    async def home():
        return HTML

    @app.get('/api/status')
    async def current_status():
        return {'connected': printer.connected, 'selected': printer.selected,
                'phase': printer.phase, 'busy': printer.lock.locked(), 'material': printer.material}

    @app.post('/api/scan')
    async def scan():
        async with exclusive():
            if printer.connected:
                raise HTTPException(409, 'Vor neuer Suche die Verbindung trennen')
            found = await BleakScanner.discover(timeout=6, return_adv=True)
            devices = []
            for device, adv in found.values():
                name = adv.local_name or device.name or ''
                if name.startswith('T0') or 'E10' in name.upper() or SERVICE in [u.lower() for u in adv.service_uuids]:
                    devices.append({'address': device.address, 'name': name or 'E10-Kandidat'})
            return {'devices': sorted(devices, key=lambda d: d['name'])}

    @app.post('/api/connect')
    async def connect(choice: DeviceChoice):
        async with exclusive():
            await printer.connect(choice.address)
            return {'connected': True, 'selected': printer.selected}

    @app.post('/api/disconnect')
    async def disconnect():
        async with exclusive():
            await printer.disconnect()
            return {'connected': False}

    @app.post('/api/preview')
    async def preview(spec: PrintSpec):
        try:
            image = (render(spec, settings.font) if spec.text.strip() else
                     Image.new('L', (spec.length_mm * 8, 96), 255))
        except (ValueError, UnicodeError) as exc:
            raise HTTPException(400, str(exc)) from exc
        b = io.BytesIO()
        image.save(b, format='PNG')
        return {'image': 'data:image/png;base64,' + base64.b64encode(b.getvalue()).decode()}

    @app.post('/api/print')
    async def print_label(spec: PrintSpec):
        async with exclusive():
            if not printer.connected:
                raise HTTPException(409, 'Zuerst Drucker verbinden')
            image = render(spec, settings.font)
            await printer.print_copies(image, spec)
            return {'message': 'Drucker meldet Druckabschluss', 'copies': spec.copies}
    return app


def main():
    settings = Settings.read()
    if settings.host not in ('127.0.0.1', '::1'):
        LOG.warning('LAN-Bindung aktiv. Nur vertrauenswürdiges Netz; HTTPS empfohlen. Keine Internetfreigabe.')
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port,
                ssl_certfile=settings.cert, ssl_keyfile=settings.key,
                ssl_keyfile_password=settings.key_password,
                workers=1, loop='asyncio', proxy_headers=False, access_log=False,
                timeout_graceful_shutdown=10)

if __name__ == '__main__':
    main()
