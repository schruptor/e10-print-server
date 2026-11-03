"""Offline tests. No Bluetooth activity, no printed labels."""
import asyncio
import base64
import io
import json
import lzma
from pathlib import Path
import struct
import subprocess
import unittest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from PIL import Image
import e10_server as e

class ProtocolTests(unittest.TestCase):
    def test_command(self):
        f=e.command_frame(0x5c,512,3)
        self.assertEqual(f.hex(),'7e5a0c001001aa5c0600000100020300')

    def test_frames(self):
        stream=bytes(range(256))*3
        frames=list(e.data_frames(stream))
        self.assertEqual(len(frames),2)
        for i,f in enumerate(frames):
            self.assertEqual(len(f),512)
            self.assertEqual(f[10:12],bytes([i,2]))
            self.assertEqual(int.from_bytes(f[8:10],'little'),sum(f[10:])&65535)
        self.assertEqual(frames[1][12+268:],frames[0][12+268:])

    def test_buffers(self):
        for width in (80,331,332,333,800,1600):
            img=Image.new('L',(width,96),255)
            for x in range(7,width,19): img.putpixel((x,48),0)
            buffers,streams,back=e.encode_job(img,4,copies=2)
            self.assertTrue(0<=back<=48)
            self.assertEqual(len(buffers),len(streams))
            for b,s in zip(buffers,streams):
                self.assertEqual(len(b),4000)
                self.assertEqual(lzma.decompress(s,format=lzma.FORMAT_ALONE),b)
                self.assertEqual(int.from_bytes(s[1:5],'little'),8192)
                self.assertEqual(int.from_bytes(s[5:13],'little'),4000)
                n=int.from_bytes(b[4:6],'little')
                check=sum(b[2:14])+sum(b[i*256-1] for i in range(1,(n*12+14)//256+1))
                self.assertEqual(int.from_bytes(b[:2],'little'),check&65535)
            self.assertTrue(buffers[-1][2]&8)
            self.assertFalse(any(b[2]&8 for b in buffers[:-1]))

    def test_preview(self):
        img=e.render(e.PrintSpec(text='ÄÖÜ ß\nE10',length_mm=50))
        self.assertEqual(img.size,(400,96))
        self.assertEqual(img.getextrema(),(0,255))
        self.assertEqual(img.crop((0,0,400,4)).getextrema(),(255,255))
        with self.assertRaises(ValueError): e.render(e.PrintSpec(text='W'*1000,length_mm=10))

    def test_receive_fragmented(self):
        p=e.E10(); f=e.command_frame(0x11)
        p.receive(None,b'noise'+f[:3]);p.receive(None,f[3:7]);p.receive(None,f[7:]+f)
        self.assertEqual(p.replies.get_nowait(),f)
        self.assertEqual(p.replies.get_nowait(),f)
        self.assertTrue(p.replies.empty())

    def test_upstream_decoder(self):
        # Optional: Node is needed only for this development test, never for the server.
        import shutil
        if not shutil.which('node'): self.skipTest('Node not installed')
        image=e.render(e.PrintSpec(text='E10 Test'))
        buffers,streams,_=e.encode_job(image,4)
        script="const L=require('./reference/lzma.js').default;let s='';process.stdin.on('data',c=>s+=c);process.stdin.on('end',()=>{const a=JSON.parse(s);let out=a.map(x=>{let d=L.decompress([...Buffer.from(x,'base64')]);return Buffer.from(typeof d==='string'?Buffer.from(d,'utf8'):d.map(n=>n&255)).toString('base64')});console.log(JSON.stringify(out))})"
        p=subprocess.run(['node','-e',script],input=json.dumps([base64.b64encode(s).decode() for s in streams]),text=True,capture_output=True,cwd=e.ROOT)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual([base64.b64decode(b) for b in json.loads(p.stdout)],buffers)

class WebTests(unittest.TestCase):
    def setUp(self):
        self.settings=e.Settings('127.0.0.1',8080,'http',None,None,None,'test-'+'x'*32,None)
        self.app=e.create_app(self.settings)
        self.client=TestClient(self.app)
        self.headers={'X-E10-Key':self.settings.token}

    def test_auth(self):
        self.assertEqual(self.client.get('/').status_code,200)
        self.assertEqual(self.client.get('/api/status').status_code,401)
        self.assertEqual(self.client.post('/api/print',json={'text':'no'}).status_code,401)
        r=self.client.get('/api/status',headers=self.headers)
        self.assertEqual(r.status_code,200)
        self.assertIn('no-store',r.headers['cache-control'])

    def test_foreign_origin(self):
        r=self.client.post('/api/preview',headers={**self.headers,'Origin':'https://evil.example'},json={'text':'x'})
        self.assertEqual(r.status_code,403)

    def test_preview_and_limits(self):
        r=self.client.post('/api/preview',headers=self.headers,json={'text':'Hallo E10'})
        self.assertEqual(r.status_code,200)
        b=base64.b64decode(r.json()['image'].split(',')[1])
        self.assertEqual(Image.open(io.BytesIO(b)).size,(400,96))
        for data in [{'text':''},{'text':'x','copies':11},{'text':'x','length_mm':201}]:
            self.assertEqual(self.client.post('/api/preview',headers=self.headers,json=data).status_code,422)
        r=self.client.post('/api/preview',headers=self.headers,content=b'x'*17000)
        self.assertEqual(r.status_code,413)
        r=self.client.post('/api/preview',headers=self.headers,json={'text':' '*5})
        self.assertEqual(r.status_code,400)

    def test_print_not_connected(self):
        r=self.client.post('/api/print',headers=self.headers,json={'text':'x'})
        self.assertEqual(r.status_code,409)

    def test_connect_json_validation(self):
        self.assertEqual(self.client.post('/api/connect',headers=self.headers,json={}).status_code,422)
        with patch.object(self.app.state.printer,'connect',new_callable=AsyncMock) as connect:
            r=self.client.post('/api/connect',headers=self.headers,json={'address':'test-id'})
            self.assertEqual(r.status_code,200)
            connect.assert_awaited_once_with('test-id')

    def test_scan_mocked(self):
        from types import SimpleNamespace as S
        devices={'a':(S(address='a',name='T0179-E10'),S(local_name='T0179-E10',service_uuids=[])),
                 'b':(S(address='b',name='Headphones'),S(local_name='Headphones',service_uuids=[]))}
        with patch.object(e.BleakScanner,'discover',new_callable=AsyncMock,return_value=devices):
            r=self.client.post('/api/scan',headers=self.headers,json={})
            self.assertEqual(r.status_code,200)
            self.assertEqual([x['address'] for x in r.json()['devices']],['a'])

class ConfigTests(unittest.TestCase):
    def test_invalid_config(self):
        import os
        for changes in [{'SERVER_PORT':'0'},{'SERVER_SCHEME':'ftp'},{'SERVER_IP':'bad'},
                        {'ACCESS_TOKEN':'short'},{'SERVER_SCHEME':'https','SSL_CERT_FILE':'','SSL_KEY_FILE':''}]:
            with patch.dict(os.environ,changes):
                with self.assertRaises(ValueError): e.Settings.read()

if __name__=='__main__': unittest.main(verbosity=2)
