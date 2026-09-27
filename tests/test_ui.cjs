const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(require('node:path').join(__dirname,'../studio/app.js'),'utf8');
const prefix=source.slice(0,source.indexOf('function render()'));
const validation=source.slice(source.indexOf('function validate(s)'),source.indexOf("\n$('#workflow-upload')"));
const context=vm.createContext({});
vm.runInContext(prefix+'\n'+validation+'\nthis.fixture=initial;this.check=validate;this.resolution=resolution;',context);
let good=context.fixture();assert.equal(context.check(good).nodes.length,9);assert.equal(good.nodes.find(n=>n.type==='output').demo,undefined);
assert.equal(context.resolution('1920x1280'),'2K');assert.equal(context.resolution('1536x1024'),'1K');
for(const mutate of [s=>s.nodes.push({...s.nodes[0]}),s=>s.edges.push(['o1','l1']),s=>s.edges.push(s.edges[0]),s=>s.nodes.find(n=>n.type==='output').images='bad',s=>s.nodes.find(n=>n.type==='generate').count=1.5,s=>s.nodes.find(n=>n.type==='generate').size=null]){const value=context.fixture();mutate(value);assert.throws(()=>context.check(value));}
const old=context.fixture();delete old.nodes.find(n=>n.type==='llm').system;context.check(old);assert.equal(typeof old.nodes.find(n=>n.type==='llm').system,'string');
console.log('9 UI regression scenarios passed');
