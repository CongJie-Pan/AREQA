const { chromium, webkit } = require('../../../frontend/node_modules/playwright');
const fs = require('node:fs');
const path = require('node:path');
const output = path.resolve(__dirname, '../../../.audit/initial-render-research');
fs.mkdirSync(output, {recursive:true});

async function run(browserType, label, viewport, theme, language = 'en') {
  const browser = await browserType.launch({headless:true});
  const context = await browser.newContext({viewport, isMobile:viewport.width<769, deviceScaleFactor:1});
  const page = await context.newPage();
  const errors=[];
  page.on('pageerror', error => errors.push(error.message.slice(0,1200)));
  let release;
  const gate = new Promise(resolve => {release=resolve;});
  await page.route(/\/_next\/.*\.js(?:\?|$)/,async route => {await gate;await route.continue();});
  await page.addInitScript(({theme,language}) => {
    localStorage.setItem('areqa:interface-theme',theme);
    localStorage.setItem('areqa:interface-language',language);
    window.__renderSamples=[];
    const measure=()=>{
      const selectors={input:'.areqa-chat-input-shell',textarea:'.areqa-chat-input-textarea',sidebar:'.areqa-chat-sidebar-toggle',floating:'.areqa-chat-sidebar-floating-action'};
      const sample={theme:document.documentElement.dataset.interfaceTheme||null};
      for(const [key,selector] of Object.entries(selectors)) {
        const el=document.querySelector(selector);
        if(!el) continue;
        const style=getComputedStyle(el),rect=el.getBoundingClientRect();
        sample[key]={x:Math.round(rect.x*10)/10,y:Math.round(rect.y*10)/10,w:Math.round(rect.width*10)/10,h:Math.round(rect.height*10)/10,padding:style.padding,radius:style.borderRadius,font:style.fontSize,lineHeight:style.lineHeight,background:style.backgroundColor,overflow:style.overflowY,clientHeight:el.clientHeight,scrollHeight:el.scrollHeight,scrollWidth:el.scrollWidth,clientWidth:el.clientWidth,inlineHeight:el.style.height,scrollbarColor:style.scrollbarColor,display:style.display};
        if(key==='floating') sample[key].open=el.dataset.sidebarOpen;
      }
      const serialized=JSON.stringify(sample);
      if(serialized!==window.__lastRenderSample){window.__renderSamples.push({ms:Math.round(performance.now()),...sample});window.__lastRenderSample=serialized;}
      requestAnimationFrame(measure);
    };
    requestAnimationFrame(measure);
  },{theme,language});
  try {
    await page.goto('http://localhost:3005',{waitUntil:'commit',timeout:60000});
    await page.locator('.areqa-chat-input-textarea').waitFor({state:'visible'});
    await page.waitForTimeout(300);
    await page.screenshot({path:path.join(output,label+'-server.png')});
    release();
    await page.waitForLoadState('domcontentloaded');
    await page.waitForFunction(()=>document.documentElement.dataset.interfaceTheme);
    await page.waitForTimeout(2200);
    const overlay=await page.locator('nextjs-portal').evaluateAll(els=>els.map(el=>el.shadowRoot?.innerText||el.shadowRoot?.querySelector('[data-nextjs-dialog]')?.textContent||'').filter(Boolean));
    await page.locator('nextjs-portal').evaluateAll(els=>els.forEach(el=>el.style.display='none'));
    await page.screenshot({path:path.join(output,label+'-client.png')});
    const samples=await page.evaluate(()=>window.__renderSamples);
    const result={label,viewport,theme,language,errors,overlay,samples};
    fs.writeFileSync(path.join(output,label+'.json'),JSON.stringify(result,null,2));
    console.log(JSON.stringify({label,errors:errors.map(e=>e.split('\n')[0]),samples:samples.length,first:samples.find(s=>s.textarea),last:samples.at(-1)}));
  } finally {release();await browser.close();}
}
module.exports = { run };
if (require.main === module) (async()=>{
  for(const [label,viewport,theme] of [
    ['mobile-dark',{width:390,height:844},'dark'],
    ['mobile-light',{width:390,height:844},'light'],
    ['desktop-dark',{width:1280,height:900},'dark'],
    ['desktop-light',{width:1280,height:900},'light'],
  ]) await run(chromium,label,viewport,theme);
  await run(webkit,'webkit-mobile-dark',{width:390,height:844},'dark');
})().catch(error=>{console.error(error);process.exit(1)});
