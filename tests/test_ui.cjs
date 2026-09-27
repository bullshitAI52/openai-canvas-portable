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

const legacy=context.fixture();delete legacy.nodes[0].role;assert.equal(context.check(legacy).nodes[0].role,'未指定');
const invalidRole=context.fixture();invalidRole.nodes[0].role='invalid';assert.throws(()=>context.check(invalidRole));
console.log('Role migration and validation passed');
vm.runInContext('this.advice=failureAdvice;this.templates=PROMPT_TEMPLATES;',context);
assert.equal(context.templates.length,4);
assert.match(context.advice('OpenAI API 401'),/密钥/);
assert.match(context.advice('OpenAI API 429 insufficient_quota'),/额度/);
assert.match(context.advice('OpenAI API 429 rate_limit'),/频繁/);
assert.match(context.advice('OpenAI API 404 model_not_found'),/模型/);
assert.match(context.advice('Failed to fetch'),/避免/);
console.log('Template catalog and error guidance passed');

assert.match(context.advice('请先上传已连接的参考图'),/检查输入/);
