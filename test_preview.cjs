// Offline DOM/fetch simulation of the actual embedded UI script; no printer access.
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync('e10_server.py', 'utf8');
const script = source.match(/<script>([\s\S]*?)<\/script>/)[1];
const elements = {};
for (const id of ['text','length','font','density','copies','image','previewInfo','state','msg','devices','print','scan','connect','disconnect']) {
    elements[id] = {value: '', style: {}, options: [], listeners: {},
        addEventListener(event, fn) { this.listeners[event] = fn; }};
}
Object.assign(elements.text, {value: 'Hallo'});
for (const [id,value] of Object.entries({length:'50',font:'36',density:'4',copies:'1'})) elements[id].value=value;
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
const reply = (index, image) => previews[index].resolve({ok:true,json:async()=>({image})});
(async()=>{
    vm.runInNewContext(script,context);
    assert.equal(previews.length,1,'preview must load immediately');
    reply(0,'initial'); await settle();
    assert.equal(elements.image.src,'initial');
    for (const id of ['text','length','font','density','copies']) {
        assert.equal(typeof elements[id].listeners.input,'function');
        assert.equal(typeof elements[id].listeners.change,'function');
        elements[id].listeners.input();
        assert.equal(typeof timer,'function');
    }
    elements.text.value='Pasted text';
    elements.length.value='80';
    elements.copies.value='3';
    elements.text.listeners.input();
    timer(); await settle();
    assert.equal(previews[1].data.text,'Pasted text');
    assert.equal(previews[1].data.length_mm,80);
    assert.equal(previews[1].data.copies,3);
    // Resolve a newer preview before an older request; older results cannot win.
    elements.text.value='Newest';
    elements.text.listeners.input(); timer(); await settle();
    reply(2,'newest'); await settle();
    reply(1,'outdated'); await settle();
    assert.equal(elements.image.src,'newest');
    assert.match(elements.previewInfo.textContent,/3 Kopie/);
    assert.match(elements.previewInfo.textContent,/5 s/);
    elements.text.value='';
    elements.text.listeners.input(); timer(); await settle();
    assert.equal(previews[3].data.text,'');
    reply(3,'blank'); await settle();
    assert.equal(elements.image.src,'blank');
    assert.equal(elements.image.hidden,undefined);
    console.log('Live preview: initial render, all controls, paste, stale replies, empty text OK');
})().catch(e=>{console.error(e);process.exitCode=1;});
