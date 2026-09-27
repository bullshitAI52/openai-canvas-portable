const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const src=fs.readFileSync(require('node:path').join(__dirname,'../studio/app.js'),'utf8');
const fn=src.slice(src.indexOf('async function run(n,action)'),src.indexOf('async function runLLM(n)'));
async function scenario(fail=false){
 const llm={id:'l',type:'llm'},g={id:'g',type:'generate',prompt:'p'},out={id:'o',type:'output'};
 const banner={hidden:true,textContent:''},stages=[];let cleared=0,calls=0;
 const ctx=vm.createContext({Date,Math,Error,crypto:{randomUUID:()=> 'id'},busy:new Set(),state:{nodes:[llm,g,out],edges:[['g','o']]},taskTimer:null,
 $:()=>banner,setInterval:()=>123,clearInterval:()=>cleared++,checkImages:()=>{},inbound:()=>[llm],inputs:()=>[],sources:()=>[],render:()=>stages.push(banner.textContent),persist:()=>{},toast:()=>{},failureAdvice:()=> 'advice',
 runLLM:async()=>{if(fail)throw Error('401');},post:async()=>{calls++;return {images:[{filename:'test.png'}]}}});
 vm.runInContext(fn+';this.run=run;',ctx);await ctx.run(g,'chain');
 assert.equal(cleared,1);assert.equal(ctx.busy.size,0);
 assert.ok(stages.some(s=>s.includes('步骤 1/2')));
 if(fail){assert.equal(calls,0);assert.match(llm.error,/401.*\nadvice|401\n处理建议：advice/);assert.match(llm.status,/步骤 1/);}
 else{assert.equal(calls,1);assert.ok(stages.some(s=>s.includes('步骤 2/2')));assert.equal(out.images[0].filename,'test.png');}
}
(async()=>{await scenario();await scenario(true);console.log('Chain stages, failure short-circuit and timer cleanup passed')})().catch(e=>{console.error(e);process.exitCode=1});
