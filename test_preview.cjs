// Offline DOM/fetch simulation of the actual embedded UI script; no printer access.
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync('e10_server.py', 'utf8');
const script = source.match(/<script>([\s\S]*?)<\/script>/)[1];
const elements = {};
for (const id of ['text','font','density','copies','image','previewInfo','state','msg','toastText','toastClose','devices','print','scan','connect','disconnect']) {
    elements[id] = {value: '', style: {}, dataset: {}, options: [], listeners: {},
        addEventListener(event, fn) { this.listeners[event] = fn; }};
}
Object.assign(elements.text, {value: 'Hallo'});
for (const [id,value] of Object.entries({font:'50',density:'4',copies:'1'})) elements[id].value=value;
const previews = [];
let timer;
const context = {
    document: {getElementById: id => elements[id], querySelectorAll: () => []},
    AbortController, Option: function(){},
    clearTimeout: () => { timer = undefined; },
    setTimeout: fn => { timer = fn; },
    setInterval: () => {},
    fetch: async (url, options) => {
        if (url === '/api/status') return {ok:true,json:async()=>({connected:false,phase:'idle'})};
        return new Promise(resolve => previews.push({data:JSON.parse(options.body),resolve}));
    }
};
const settle = async () => { for(let n=0;n<12;n++) await Promise.resolve(); };
const reply = (index, image) => previews[index].resolve({ok:true,json:async()=>({image,width_px:320,height_px:96,length_mm:40,font_size:50})});
(async()=>{
    vm.runInNewContext(script,context);
    assert.equal(previews.length,1,'preview must load immediately');
    reply(0,'initial'); await settle();
    assert.equal(elements.image.src,'initial');
    for (const id of ['text','font','density','copies']) {
        assert.equal(typeof elements[id].listeners.input,'function');
        assert.equal(typeof elements[id].listeners.change,'function');
        elements[id].listeners.input();
        assert.equal(typeof timer,'function');
    }
    elements.text.value='Pasted text';
    elements.copies.value='3';
    elements.text.listeners.input();
    timer(); await settle();
    assert.equal(previews[1].data.text,'Pasted text');
    assert.equal(previews[1].data.length_mm,undefined);
    assert.equal(previews[1].data.font_size,50);
    assert.equal(previews[1].data.copies,3);
    // Resolve a newer preview before an older request; older results cannot win.
    elements.text.value='Newest';
    elements.text.listeners.input(); timer(); await settle();
    reply(2,'newest'); await settle();
    reply(1,'outdated'); await settle();
    assert.equal(elements.image.src,'newest');
    assert.equal(elements.image.width,320);
    assert.equal(elements.image.height,96);
    assert.match(elements.previewInfo.textContent,/40 mm automatisch/);
    assert.match(elements.previewInfo.textContent,/3 Kopie/);
    assert.match(elements.previewInfo.textContent,/5 s/);
    elements.text.value='';
    elements.text.listeners.input(); timer(); await settle();
    assert.equal(previews[3].data.text,'');
    reply(3,'blank'); await settle();
    assert.equal(elements.image.src,'blank');
    assert.equal(elements.image.hidden,undefined);
    vm.runInNewContext("showToast('<b>Fehler</b>','error',10000)",context);
    assert.equal(elements.msg.hidden,false);
    assert.equal(elements.msg.dataset.tone,'error');
    assert.equal(elements.toastText.textContent,'<b>Fehler</b>','messages must be plain text');
    elements.toastClose.onclick();
    assert.equal(elements.msg.hidden,true);
    vm.runInNewContext("showToast('Fertig.','success',5000)",context);
    timer();
    assert.equal(elements.msg.hidden,true,'toast should auto-dismiss');
    await vm.runInNewContext("run(async()=>{throw Error('Drucker nicht gefunden')})",context);
    assert.equal(elements.msg.dataset.tone,'error');
    assert.equal(elements.toastText.textContent,'Drucker nicht gefunden');
    await vm.runInNewContext("run(async()=>{})",context);
    assert.equal(elements.msg.dataset.tone,'success');
    assert.equal(elements.toastText.textContent,'Fertig.');
    assert.ok(source.includes('#msg{position:fixed;top:'));
    console.log('Live preview and toast messages: OK');
})().catch(e=>{console.error(e);process.exitCode=1;});
